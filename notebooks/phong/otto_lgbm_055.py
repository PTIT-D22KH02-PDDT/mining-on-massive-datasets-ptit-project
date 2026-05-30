"""
OTTO Recommender System — Co-visitation Matrix + LGBMRanker Pipeline

Phương pháp: Candidate ReRank (2 giai đoạn)
  1. Candidate Generation: Co-visitation matrices (clicks, cart_order, buy2buy) + history + popular items
  2. Re-ranking: LGBMRanker (3 models riêng cho clicks/carts/orders)

Data: /kaggle/input/datasets/trungnguyen2710t/otto-ptit-filter/
  - train.parquet   (toàn bộ events để train)
  - val.parquet     (validation events)
  - test.parquet    (test events)

Môi trường: Kaggle Notebook (GPU T4)
"""

# ══════════════════════════════════════════════════════════════════════════════
# CELL 1: Imports & Setup
# ══════════════════════════════════════════════════════════════════════════════

import os
import gc
import glob
import time
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import polars as pl
import lightgbm as lgb
from tqdm import tqdm

warnings.filterwarnings("ignore")

# GPU engine cho Polars (Kaggle có RAPIDS)
try:
    import cudf_polars
    print("cudf_polars loaded — Polars sẽ chạy trên GPU!")
    GPU_ENGINE = True
except ImportError:
    print("cudf_polars không có — Polars chạy trên CPU.")
    GPU_ENGINE = False


def _collect(lazy_frame: pl.LazyFrame) -> pl.DataFrame:
    """Collect LazyFrame, dùng GPU engine nếu có."""
    if GPU_ENGINE:
        try:
            return lazy_frame.collect(engine="gpu")
        except Exception:
            return lazy_frame.collect()
    return lazy_frame.collect()


# ══════════════════════════════════════════════════════════════════════════════
# CELL 2: Configuration
# ══════════════════════════════════════════════════════════════════════════════

LOCAL_VAL_DIR = Path("/kaggle/input/datasets/radek1/otto-train-and-test-data-for-local-validation")
TRAIN_PARQUET = LOCAL_VAL_DIR / "train.parquet"
LOCAL_TEST_PARQUET = LOCAL_VAL_DIR / "test.parquet"
LOCAL_TEST_LABELS = LOCAL_VAL_DIR / "test_labels.parquet"

KAGGLE_TEST_PARQUET = Path("/kaggle/input/datasets/radek1/otto-full-optimized-memory-footprint/test.parquet")

WORKING_DIR = Path("/kaggle/working")
WORKING_DIR.mkdir(exist_ok=True)

# --- Hyperparameters ---
TYPE_LABELS = {"clicks": 0, "carts": 1, "orders": 2}
TYPE_WEIGHTS_CART_ORDER = {0: 1, 1: 6, 2: 3}  # Trọng số cho cart-order matrix

# Co-visitation matrix params
COVISIT_CONFIG = {
    "clicks": {
        "top_k": 20,
        "valid_time_hours": 24,     # Cặp hợp lệ trong 24h
        "last_n_events": 30,        # Chỉ giữ 30 event gần nhất mỗi session
    },
    "cart_order": {
        "top_k": 15,
        "valid_time_hours": 24,
        "last_n_events": 30,
    },
    "buy2buy": {
        "top_k": 15,
        "valid_time_hours": 24 * 14,  # 14 ngày
        "last_n_events": 30,
    },
}

# LGBMRanker params
LGBM_PARAMS = {
    "objective": "lambdarank",
    "metric": "map",
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}

# Negative sampling params
NEG_POS_RATIO = 20        # 20 negative per 1 positive
POPULAR_NEG_FRAC = 0.5    # 50% negative = popular (hard negatives)

# Candidate generation
TOP_POPULAR_CLICKS = 20   # Top popular items for clicks
TOP_POPULAR_CARTS  = 20   # Top popular items for carts  
TOP_POPULAR_ORDERS = 20   # Top popular items for orders
CANDIDATE_CHUNK_SIZE = 50_000  # Sessions per chunk

# Recall metric weights (giống Kaggle)
RECALL_WEIGHTS = {"clicks": 0.10, "carts": 0.30, "orders": 0.60}

print(f"Train             : {TRAIN_PARQUET}")
print(f"Local Test (Input): {LOCAL_TEST_PARQUET}")
print(f"Local Test Labels : {LOCAL_TEST_LABELS}")


# ══════════════════════════════════════════════════════════════════════════════
# CELL 3: Load & Preprocess Raw Data
# ══════════════════════════════════════════════════════════════════════════════

def load_raw_data(parquet_path: Path) -> pl.DataFrame:
    """
    Load parquet và chuẩn hóa: 
    - type: string → int8 (clicks=0, carts=1, orders=2)
    - ts: milliseconds → seconds (int32)  
    - Tự detect xem type là string hay đã là int
    - Tự detect xem ts đã chia 1000 chưa
    """
    print(f"Loading {parquet_path.name}...")
    
    # Load raw trước để kiểm tra schema
    df = _collect(
        pl.scan_parquet(str(parquet_path))
        .select(["session", "aid", "ts", "type"])
    )
    
    # --- Xử lý cột type ---
    # Nếu type là string ("clicks", "carts", "orders") → map sang int
    # Nếu type đã là int (0, 1, 2) → giữ nguyên
    if df["type"].dtype == pl.String or df["type"].dtype == pl.Utf8:
        df = df.with_columns(
            pl.col("type").replace_strict(TYPE_LABELS).cast(pl.Int8)
        )
        print("  [type] string → int8 mapping applied")
    elif df["type"].dtype not in (pl.Int8, pl.Int16, pl.Int32):
        df = df.with_columns(pl.col("type").cast(pl.Int8))
    
    # --- Xử lý cột ts ---
    # Nếu ts > 10^12 → đang ở milliseconds, cần chia 1000
    ts_max = df["ts"].max()
    if ts_max > 1e12:
        df = df.with_columns(
            (pl.col("ts") / 1000).cast(pl.Int32)
        )
        print("  [ts] milliseconds → seconds conversion applied")
    else:
        df = df.with_columns(pl.col("ts").cast(pl.Int32))
    
    print(f"  → {df.height:,} events | "
          f"{df['session'].n_unique():,} sessions | "
          f"{df['aid'].n_unique():,} unique aids")
    return df


def build_ground_truth(val_df: pl.DataFrame) -> pd.DataFrame:
    """
    Build ground truth từ val.parquet.
    
    Dataset structure (otto-ptit-filter):
    - train.parquet = history events (tuần 1-3)
    - val.parquet   = future events cần predict (tuần 4)
    - val_aids.csv  = chỉ chứa danh sách AIDs, KHÔNG phải ground truth
    
    Logic: Group val.parquet theo (session, type) → list of unique aids
    → Đây là ground truth cho Recall@20
    
    Returns: pd.DataFrame với columns [session, type, ground_truth]
    """
    print("Building ground truth from val.parquet...")
    
    TYPE_REVERSE = {0: "clicks", 1: "carts", 2: "orders"}
    
    gt_pl = (
        val_df
        .group_by(["session", "type"])
        .agg(pl.col("aid").unique().alias("ground_truth"))
    )
    
    # Convert to pandas cho validation step
    gt_pd = gt_pl.to_pandas()
    gt_pd["type"] = gt_pd["type"].map(TYPE_REVERSE)
    
    n_types = gt_pd["type"].nunique()
    n_sessions = gt_pd["session"].nunique()
    print(f"  → {len(gt_pd):,} rows | {n_sessions:,} sessions | "
          f"{n_types} types: {gt_pd['type'].unique().tolist()}")
    
    # Stats per type
    for t in ["clicks", "carts", "orders"]:
        t_rows = gt_pd[gt_pd["type"] == t]
        if not t_rows.empty:
            avg_aids = t_rows["ground_truth"].apply(len).mean()
            print(f"    {t:8s}: {len(t_rows):,} sessions | avg {avg_aids:.1f} aids/session")
    
    return gt_pd


def build_train_history_and_labels(
    df: pl.DataFrame,
    history_window_days: int = 14,
) -> tuple:
    """
    Chia train data thành history (input) và labels (target).
    
    Logic:
    - Cho mỗi session, cutoff = max_ts - 24h
    - History = events TRƯỚC cutoff (trong history_window_days gần nhất)
    - Labels  = events SAU cutoff (ground truth)
    
    Returns: (history_df, ground_truth_df, full_history_for_features)
    """
    print("\nBuilding train history & labels...")
    
    # Tính cutoff cho mỗi session
    session_cutoffs = df.group_by("session").agg(
        (pl.col("ts").max() - 24 * 3600).alias("cutoff_ts")
    )
    
    last_ts = df["ts"].max()
    min_ts = last_ts - history_window_days * 24 * 3600
    
    # Join cutoff
    df_with_cutoff = df.join(session_cutoffs, on="session", how="left")
    
    # Chia history / labels
    history_source = df_with_cutoff.filter(
        (pl.col("ts") < pl.col("cutoff_ts")) & 
        (pl.col("ts") >= min_ts)
    )
    labels_source = df_with_cutoff.filter(
        pl.col("ts") >= pl.col("cutoff_ts")
    )
    
    # Ground truth: group by (session, type) → list of aids
    ground_truth = (
        labels_source
        .group_by(["session", "type"])
        .agg(pl.col("aid").alias("ground_truth"))
    )
    
    # History: unique (session, aid) pairs
    history_df = history_source.select(["session", "aid"]).unique()
    
    # Full history cho feature engineering
    full_history = history_source.drop("cutoff_ts")
    
    print(f"  History: {history_df.height:,} session-aid pairs | "
          f"{history_df['session'].n_unique():,} sessions")
    print(f"  Labels:  {ground_truth.height:,} ground truth rows")
    
    return history_df, ground_truth, full_history


# Load data
train_df = load_raw_data(TRAIN_PARQUET)
val_df   = load_raw_data(LOCAL_TEST_PARQUET)  # Input (history) cho validation

# Load ground truth từ test_labels.parquet
print(f"Loading {LOCAL_TEST_LABELS.name}...")
val_gt = pd.read_parquet(LOCAL_TEST_LABELS)
if 'labels' in val_gt.columns:
    val_gt = val_gt.rename(columns={'labels': 'ground_truth'})

# Build training history và labels sớm để tránh leakage
train_history, train_gt, train_full_history = build_train_history_and_labels(train_df)

train_events_count = train_df.height

# Xóa train_df gốc để giải phóng RAM ngay lập tức
del train_df
gc.collect()


# ══════════════════════════════════════════════════════════════════════════════
# CELL 4: Co-visitation Matrix Generation
# ══════════════════════════════════════════════════════════════════════════════

def compute_covisit_matrix(
    df: pl.DataFrame,
    matrix_type: str,    # "clicks", "cart_order", "buy2buy"
    top_k: int = 20,
    valid_time_hours: int = 24,
    last_n_events: int = 30,
    type_weight: dict = None,
    chunk_size: int = 100_000,  # 100K sessions/chunk (self-join tạo O(N²) pairs)
) -> pl.DataFrame:
    """
    Tính ma trận co-visitation trên Polars (CPU).
    
    Logic:
    1. Sort by (session, ts DESC)
    2. Giữ last_n_events events mỗi session
    3. Self-join on session → tạo tất cả cặp (aid_x, aid_y)
    4. Lọc: |ts_x - ts_y| < valid_time VÀ aid_x != aid_y
    5. Gán trọng số theo loại matrix
    6. Group by (aid_x, aid_y) → sum(wgt)
    7. Giữ top_k aid_y cho mỗi aid_x
    
    Returns:
        DataFrame với columns: [aid, candidate_aid, wgt_{type}, rank_{type}]
    """
    valid_time_sec = valid_time_hours * 3600
    
    print(f"\n{'='*60}")
    print(f"Computing Co-visitation Matrix: {matrix_type}")
    print(f"  top_k={top_k} | valid_time={valid_time_hours}h | last_n={last_n_events}")
    print(f"{'='*60}")
    
    # Filter cho buy2buy: chỉ carts + orders
    if matrix_type == "buy2buy":
        source_df = df.filter(pl.col("type").is_in([1, 2]))
        print(f"  [buy2buy] Filtered to carts+orders: {source_df.height:,} events")
    else:
        source_df = df
    
    # Chia sessions thành chunks để xử lý tuần tự (tránh OOM)
    all_sessions = source_df["session"].unique().sort().to_list()
    n_sessions = len(all_sessions)
    n_chunks = (n_sessions + chunk_size - 1) // chunk_size
    
    print(f"  Processing {n_sessions:,} sessions in {n_chunks} chunks...")
    
    all_results = []
    
    for chunk_idx in range(n_chunks):
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, n_sessions)
        chunk_sessions = all_sessions[start:end]
        
        t0 = time.time()
        
        # Lọc ra events của chunk sessions
        chunk_df = source_df.filter(pl.col("session").is_in(chunk_sessions))
        
        # Sort by (session, ts) DESC để lấy events gần nhất
        chunk_df = chunk_df.sort(["session", "ts"], descending=[False, True])
        
        # Giữ last_n_events events mỗi session
        # Dùng row_number thay cho cum_count (tương thích Polars mới hơn)
        chunk_df = (
            chunk_df
            .with_columns(
                pl.arange(0, pl.len()).over("session").alias("event_rank")
            )
            .filter(pl.col("event_rank") < last_n_events)
            .drop("event_rank")
        )
        
        # Self-join: tạo tất cả cặp trong cùng session
        pairs_df = chunk_df.join(chunk_df, on="session", suffix="_y")
        
        # Lọc cặp hợp lệ
        pairs_df = pairs_df.filter(
            ((pl.col("ts") - pl.col("ts_y")).abs() < valid_time_sec) &
            (pl.col("aid") != pl.col("aid_y"))
        )
        
        # Deduplicate: 1 cặp (session, aid_x, aid_y) chỉ đếm 1 lần
        pairs_df = pairs_df.unique(subset=["session", "aid", "aid_y"])
        
        # Gán trọng số
        if matrix_type == "cart_order" and type_weight:
            pairs_df = pairs_df.with_columns(
                pl.col("type_y").replace_strict(type_weight).cast(pl.Float32).alias("wgt")
            )
        elif matrix_type == "clicks":
            # Time-weighted: sự kiện gần hơn có trọng số cao hơn
            ts_min = pairs_df["ts"].min()
            ts_max = pairs_df["ts"].max()
            ts_range = max(ts_max - ts_min, 1)
            pairs_df = pairs_df.with_columns(
                (1.0 + 3.0 * (pl.col("ts") - ts_min) / ts_range).cast(pl.Float32).alias("wgt")
            )
        else:  # buy2buy
            pairs_df = pairs_df.with_columns(
                pl.lit(1.0).cast(pl.Float32).alias("wgt")
            )
        
        # Group by (aid, aid_y) → sum weights
        result = (
            pairs_df
            .group_by(["aid", "aid_y"])
            .agg(pl.col("wgt").sum())
        )
        
        all_results.append(result)
        
        elapsed = time.time() - t0
        print(f"  Chunk {chunk_idx+1}/{n_chunks}: {len(chunk_sessions):,} sessions | "
              f"{result.height:,} pairs | {elapsed:.1f}s")
        
        del chunk_df, pairs_df, result
        gc.collect()
    
    # Merge tất cả chunks
    print("  Merging all chunks...")
    merged = pl.concat(all_results)
    del all_results
    gc.collect()
    
    # Aggregate lại sau merge
    merged = (
        merged
        .group_by(["aid", "aid_y"])
        .agg(pl.col("wgt").sum())
    )
    
    # Lấy top_k cho mỗi aid
    merged = (
        merged
        .sort(["aid", "wgt"], descending=[False, True])
        .with_columns(
            pl.arange(0, pl.len()).over("aid").alias("rank")
        )
        .filter(pl.col("rank") < top_k)
    )
    
    # Rename columns
    wgt_col = f"wgt_{matrix_type}"
    rank_col = f"rank_{matrix_type}"
    merged = merged.rename({
        "aid_y": "candidate_aid",
        "wgt": wgt_col,
        "rank": rank_col,
    })
    
    # Cast types cho tiết kiệm RAM
    merged = merged.with_columns(
        pl.col(rank_col).cast(pl.UInt16),
    )
    
    print(f"Done: {merged.height:,} total pairs | "
          f"{merged['aid'].n_unique():,} unique source aids")
    
    return merged


# --- Tạo 3 ma trận co-visitation ---
t_start = time.time()

covisit_clicks = compute_covisit_matrix(
    train_full_history,
    matrix_type="clicks",
    **COVISIT_CONFIG["clicks"],
)

covisit_cart_order = compute_covisit_matrix(
    train_full_history,
    matrix_type="cart_order",
    type_weight=TYPE_WEIGHTS_CART_ORDER,
    **COVISIT_CONFIG["cart_order"],
)

covisit_buy2buy = compute_covisit_matrix(
    train_full_history,
    matrix_type="buy2buy",
    **COVISIT_CONFIG["buy2buy"],
)

print(f"\nTotal co-visitation time: {time.time() - t_start:.0f}s")
gc.collect()


# ══════════════════════════════════════════════════════════════════════════════
# CELL 5: Candidate Generation
# ══════════════════════════════════════════════════════════════════════════════

def get_popular_items(df: pl.DataFrame, n_days: int = 7) -> pl.DataFrame:
    """Lấy top popular items trong n_days gần nhất."""
    last_ts = df["ts"].max()
    cutoff_ts = last_ts - n_days * 24 * 3600
    
    recent = df.filter(pl.col("ts") >= cutoff_ts)
    
    top_clicks = (
        recent.filter(pl.col("type") == 0)["aid"]
        .value_counts()
        .sort("count", descending=True)
        .head(TOP_POPULAR_CLICKS)["aid"]
    )
    top_carts = (
        recent.filter(pl.col("type") == 1)["aid"]
        .value_counts()
        .sort("count", descending=True)
        .head(TOP_POPULAR_CARTS)["aid"]
    )
    top_orders = (
        recent.filter(pl.col("type") == 2)["aid"]
        .value_counts()
        .sort("count", descending=True)
        .head(TOP_POPULAR_ORDERS)["aid"]
    )
    
    popular = pl.concat([top_clicks, top_carts, top_orders]).unique()
    popular_df = pl.DataFrame({"candidate_aid": popular})
    print(f"Popular items: {popular_df.height} unique aids")
    return popular_df


def generate_candidates(
    history_df: pl.DataFrame,    # (session, aid) — unique session-aid pairs
    df_clicks: pl.DataFrame,     # co-visitation clicks matrix
    df_buys: pl.DataFrame,       # co-visitation cart_order matrix
    df_buy2buy: pl.DataFrame,    # co-visitation buy2buy matrix
    popular_df: pl.DataFrame,    # popular items
    chunk_size: int = CANDIDATE_CHUNK_SIZE,
) -> pl.DataFrame:
    """
    Tổng hợp ứng viên từ 4 nguồn:
    1. History (items user đã tương tác)
    2. Popular items
    3. Co-visitation clicks
    4. Co-visitation cart-order
    5. Co-visitation buy2buy
    
    Returns: DataFrame (session, candidate_aid) + source features
    """
    all_sessions = history_df["session"].unique().sort().to_list()
    n_sessions = len(all_sessions)
    n_chunks = (n_sessions + chunk_size - 1) // chunk_size
    
    print(f"\n{'='*60}")
    print(f"Generating Candidates")
    print(f"  {n_sessions:,} sessions in {n_chunks} chunks")
    print(f"{'='*60}")
    
    all_candidates = []
    
    for chunk_idx in range(n_chunks):
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, n_sessions)
        chunk_sessions = all_sessions[start:end]
        
        t0 = time.time()
        
        # History cho chunk này
        history_chunk = history_df.filter(pl.col("session").is_in(chunk_sessions))
        
        # --- Nguồn 1: History candidates ---
        cand_history = (
            history_chunk
            .rename({"aid": "candidate_aid"})
            .with_columns(pl.lit(1).cast(pl.UInt8).alias("source_history"))
        )
        
        # --- Nguồn 2: Popular candidates ---
        sessions_in_chunk = history_chunk.select("session").unique()
        cand_popular = sessions_in_chunk.join(popular_df, how="cross")
        
        # --- Nguồn 3-5: Co-visitation candidates ---
        cand_clicks_raw = history_chunk.join(df_clicks, on="aid", how="inner")
        cand_buys_raw   = history_chunk.join(df_buys, on="aid", how="inner")
        cand_b2b_raw    = history_chunk.join(df_buy2buy, on="aid", how="inner")
        
        # --- Union tất cả candidates ---
        candidates_df = pl.concat([
            cand_history.select(["session", "candidate_aid"]),
            cand_popular.select(["session", "candidate_aid"]),
            cand_clicks_raw.select(["session", "candidate_aid"]),
            cand_buys_raw.select(["session", "candidate_aid"]),
            cand_b2b_raw.select(["session", "candidate_aid"]),
        ]).unique(subset=["session", "candidate_aid"])
        
        # --- Join back source features ---
        # History flag
        candidates_df = candidates_df.join(
            cand_history.select(["session", "candidate_aid", "source_history"]),
            on=["session", "candidate_aid"],
            how="left",
        )
        
        # Co-visitation features: lấy min rank, max wgt cho mỗi (session, candidate)
        for cand_raw, name in [
            (cand_clicks_raw, "clicks"),
            (cand_buys_raw, "cart_order"),
            (cand_b2b_raw, "buy2buy"),
        ]:
            rank_col = f"rank_{name}"
            wgt_col = f"wgt_{name}"
            
            if rank_col in cand_raw.columns:
                agg = (
                    cand_raw
                    .group_by(["session", "candidate_aid"])
                    .agg([
                        pl.col(rank_col).min(),
                        pl.col(wgt_col).max(),
                    ])
                )
                candidates_df = candidates_df.join(
                    agg, on=["session", "candidate_aid"], how="left"
                )
        
        all_candidates.append(candidates_df)
        
        elapsed = time.time() - t0
        n_cand = candidates_df.height
        avg_per_session = n_cand / max(len(chunk_sessions), 1)
        print(f"  Chunk {chunk_idx+1}/{n_chunks}: {n_cand:,} candidates "
              f"({avg_per_session:.0f}/session) | {elapsed:.1f}s")
        
        del (history_chunk, cand_history, cand_popular, 
             cand_clicks_raw, cand_buys_raw, cand_b2b_raw, candidates_df)
        gc.collect()
    
    result = pl.concat(all_candidates)
    del all_candidates
    gc.collect()
    
    print(f"Total candidates: {result.height:,} | "
          f"Avg: {result.height / n_sessions:.0f}/session")
    
    return result


# --- Chunk-based Training Pipeline Definition ---
TRAIN_CHUNK_SIZE = 100_000
TRAIN_DATA_DIR = WORKING_DIR / "train_chunks"
TRAIN_DATA_DIR.mkdir(exist_ok=True)

def build_training_data_chunked(
    history_df: pl.DataFrame,
    ground_truth_df: pl.DataFrame,
    feature_source_df: pl.DataFrame,
    global_item_feats_all: pl.DataFrame,
    global_item_feats_7d: pl.DataFrame,
    df_clicks: pl.DataFrame,
    df_buys: pl.DataFrame,
    df_buy2buy: pl.DataFrame,
    popular_df: pl.DataFrame,
    out_dir: Path,
    chunk_size: int = TRAIN_CHUNK_SIZE,
) -> dict:
    all_sessions = history_df["session"].unique().sort().to_list()
    n_sessions = len(all_sessions)
    n_chunks = (n_sessions + chunk_size - 1) // chunk_size

    print(f"\n{'='*60}")
    print(f"Building Training Data — Chunked (No OOM)")
    print(f"  {n_sessions:,} sessions | {n_chunks} chunks | chunk_size={chunk_size:,}")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}")

    chunk_paths = {t: [] for t in ["clicks", "carts", "orders"]}

    for chunk_idx in range(n_chunks):
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, n_sessions)
        chunk_sessions = all_sessions[start:end]
        t0 = time.time()

        history_chunk = history_df.filter(pl.col("session").is_in(chunk_sessions))
        gt_chunk = ground_truth_df.filter(pl.col("session").is_in(chunk_sessions))

        # Generate candidates for this chunk ONLY
        candidates = generate_candidates(
            history_chunk,
            df_clicks,
            df_buys,
            df_buy2buy,
            popular_df,
            chunk_size=chunk_size
        )

        # Add features
        candidates_feat = add_all_features(
            candidates, feature_source_df,
            global_item_feats_all, global_item_feats_7d,
        )
        del candidates
        gc.collect()

        # Label and write to disk
        for pred_type in ["clicks", "carts", "orders"]:
            labeled = create_labeled_training_set(candidates_feat, gt_chunk, pred_type)
            if labeled.height == 0:
                continue
            out_path = out_dir / f"{pred_type}_chunk_{chunk_idx:04d}.parquet"
            labeled.write_parquet(str(out_path))
            chunk_paths[pred_type].append(out_path)

        del candidates_feat, gt_chunk
        gc.collect()

        print(f"  Chunk {chunk_idx+1}/{n_chunks}: {len(chunk_sessions):,} sessions | {time.time()-t0:.1f}s")

    for t, paths in chunk_paths.items():
        print(f"  {t}: {len(paths)} parquet files")
    return chunk_paths


# ══════════════════════════════════════════════════════════════════════════════
# CELL 6: Feature Engineering
# ══════════════════════════════════════════════════════════════════════════════

def create_item_features(df: pl.DataFrame, suffix: str = "_all") -> pl.DataFrame:
    """Tạo item-level features (count + ratio) cho một cửa sổ thời gian."""
    item_feats = (
        df
        .group_by("aid")
        .agg([
            pl.count().alias(f"item_total_cnt{suffix}"),
            pl.col("type").filter(pl.col("type") == 0).count().alias(f"item_click_cnt{suffix}"),
            pl.col("type").filter(pl.col("type") == 1).count().alias(f"item_cart_cnt{suffix}"),
            pl.col("type").filter(pl.col("type") == 2).count().alias(f"item_order_cnt{suffix}"),
            pl.col("session").n_unique().alias(f"item_unique_sessions{suffix}"),
        ])
        .rename({"aid": "candidate_aid"})
    )
    
    # Conversion ratios (smoothing +10)
    item_feats = item_feats.with_columns([
        (pl.col(f"item_order_cnt{suffix}") / (pl.col(f"item_click_cnt{suffix}") + 10))
            .alias(f"item_buy_ratio{suffix}"),
        (pl.col(f"item_cart_cnt{suffix}") / (pl.col(f"item_click_cnt{suffix}") + 10))
            .alias(f"item_cart_ratio{suffix}"),
        (pl.col(f"item_order_cnt{suffix}") / (pl.col(f"item_cart_cnt{suffix}") + 10))
            .alias(f"item_order_per_cart{suffix}"),
    ])
    
    return item_feats


def create_session_features(df: pl.DataFrame) -> tuple:
    """
    Tạo session-level features.
    Returns: (session_feats, interaction_feats, last_item_info)
    """
    # Session level
    session_feats = (
        df
        .group_by("session")
        .agg([
            pl.count().alias("session_length"),
            pl.col("aid").n_unique().alias("session_unique_aids"),
            pl.col("ts").max().alias("session_end_ts"),
            (pl.col("ts").max() - pl.col("ts").min()).alias("session_duration"),
            # Type distribution
            pl.col("type").filter(pl.col("type") == 0).count().alias("session_click_cnt"),
            pl.col("type").filter(pl.col("type") == 1).count().alias("session_cart_cnt"),
            pl.col("type").filter(pl.col("type") == 2).count().alias("session_order_cnt"),
        ])
    )
    
    # Click ratio trong session
    session_feats = session_feats.with_columns([
        (pl.col("session_click_cnt") / (pl.col("session_length") + 1))
            .alias("session_click_ratio"),
        (pl.col("session_cart_cnt") / (pl.col("session_length") + 1))
            .alias("session_cart_ratio"),
    ])
    
    # Interaction level (per session-aid pair)
    interaction_feats = (
        df
        .group_by(["session", "aid"])
        .agg([
            pl.count().alias("num_repetitions"),
            pl.col("ts").max().alias("last_item_ts"),
            pl.col("ts").min().alias("first_item_ts"),
        ])
        .rename({"aid": "candidate_aid"})
    )
    
    # Last item in session
    last_items = (
        df
        .sort("ts")
        .group_by("session", maintain_order=True)
        .last()
        .select(["session", "aid"])
        .rename({"aid": "last_aid"})
    )
    
    return session_feats, interaction_feats, last_items


def add_all_features(
    candidates_df: pl.DataFrame,
    feature_source_df: pl.DataFrame,
    global_item_feats_all: pl.DataFrame,
    global_item_feats_7d: pl.DataFrame,
) -> pl.DataFrame:
    """
    Thêm tất cả features cho candidates DataFrame.
    """
    print("\nAdding features...")
    t0 = time.time()
    
    df = candidates_df.clone()
    
    # --- Item features ---
    df = df.join(global_item_feats_all, on="candidate_aid", how="left")
    df = df.join(global_item_feats_7d, on="candidate_aid", how="left")
    
    # --- Session features ---
    # Lọc feature_source_df để chỉ tính session features cho các session trong candidates
    active_sessions = df["session"].unique()
    session_history = feature_source_df.filter(pl.col("session").is_in(active_sessions))
    
    session_feats, interaction_feats, last_items = create_session_features(session_history)
    
    df = df.join(session_feats, on="session", how="left")
    df = df.join(interaction_feats, on=["session", "candidate_aid"], how="left")
    df = df.join(last_items, on="session", how="left")
    
    # --- Derived features ---
    
    # Fill null ranks with 999
    for c in ["rank_clicks", "rank_cart_order", "rank_buy2buy"]:
        if c not in df.columns:
            df = df.with_columns(pl.lit(999).cast(pl.UInt16).alias(c))
        else:
            df = df.with_columns(pl.col(c).fill_null(999))
    
    # Fill null weights with 0
    for c in ["wgt_clicks", "wgt_cart_order", "wgt_buy2buy"]:
        if c not in df.columns:
            df = df.with_columns(pl.lit(0.0).cast(pl.Float32).alias(c))
        else:
            df = df.with_columns(pl.col(c).fill_null(0.0))
    
    df = df.with_columns([
        # --- Trend features ---
        (pl.col("item_click_cnt_7d").fill_null(0) / (pl.col("item_click_cnt_all").fill_null(0) + 10))
            .alias("click_trend_7d"),
        (pl.col("item_order_cnt_7d").fill_null(0) / (pl.col("item_order_cnt_all").fill_null(0) + 10))
            .alias("order_trend_7d"),
        (pl.col("item_buy_ratio_7d").fill_null(0) - pl.col("item_buy_ratio_all").fill_null(0))
            .alias("conversion_trend_diff"),
        
        # --- Cross-source rank features ---
        (pl.col("rank_clicks") - pl.col("rank_buy2buy")).cast(pl.Int32)
            .alias("rank_diff_click_b2b"),
        (pl.col("rank_cart_order") - pl.col("rank_buy2buy")).cast(pl.Int32)
            .alias("rank_diff_buy_b2b"),
        
        # Combined weight
        (pl.col("wgt_buy2buy") * 2.0 + pl.col("wgt_cart_order") * 1.0)
            .alias("combined_buy_weight"),
        
        # --- Recency features ---
        (pl.col("session_end_ts") - pl.col("last_item_ts")).fill_null(7 * 24 * 3600)
            .alias("recency_sec"),
        
        # --- Flags ---
        (pl.col("candidate_aid") == pl.col("last_aid")).cast(pl.Int8).fill_null(0)
            .alias("is_last_viewed"),
        (pl.col("num_repetitions").fill_null(0) > 1).cast(pl.Int8)
            .alias("is_repeated"),
        
        # Source history flag
        pl.col("source_history").fill_null(0),
    ])
    
    # Log recency
    df = df.with_columns(
        pl.col("recency_sec").cast(pl.Float64).log1p().alias("log_recency")
    )
    
    # Decayed weights
    df = df.with_columns([
        (pl.col("wgt_buy2buy") / (pl.col("log_recency") + 1)).alias("wgt_b2b_decayed"),
        (pl.col("wgt_clicks") / (pl.col("log_recency") + 1)).alias("wgt_clicks_decayed"),
    ])
    
    # Sorted rank features: min_rank_1, min_rank_2, n_sources (Optimized using horizontal column-wise ops)
    a = pl.col("rank_clicks").cast(pl.Int32)
    b = pl.col("rank_cart_order").cast(pl.Int32)
    c = pl.col("rank_buy2buy").cast(pl.Int32)
    
    min_val = pl.min_horizontal([a, b, c])
    max_val = pl.max_horizontal([a, b, c])
    
    df = df.with_columns([
        min_val.cast(pl.UInt16).alias("min_rank_1"),
        (a + b + c - min_val - max_val).cast(pl.UInt16).alias("min_rank_2"),
        ((a < 999).cast(pl.Int8) + (b < 999).cast(pl.Int8) + (c < 999).cast(pl.Int8)).alias("n_sources_present")
    ])

    
    # Drop helper columns
    cols_to_drop = ["session_end_ts", "last_item_ts", "first_item_ts", "last_aid"]
    df = df.drop([c for c in cols_to_drop if c in df.columns])
    
    # Fill remaining nulls
    df = df.fill_null(0)
    
    elapsed = time.time() - t0
    print(f"Features added: {len(df.columns)} columns | {elapsed:.1f}s")
    
    return df


# --- Precompute global item features ---
print("\nPrecomputing global item features on train_full_history...")
t_item_start = time.time()
last_ts = train_full_history["ts"].max()
global_item_feats_all = create_item_features(train_full_history, suffix="_all")
recent_7d = train_full_history.filter(pl.col("ts") >= last_ts - 7 * 24 * 3600)
global_item_feats_7d = create_item_features(recent_7d, suffix="_7d")
print(f"  Done precomputing global item features: {time.time() - t_item_start:.1f}s")
gc.collect()


# Đã bỏ phần tính features toàn bộ vào RAM ở đây.


# ══════════════════════════════════════════════════════════════════════════════
# CELL 7: Training Set Construction
# ══════════════════════════════════════════════════════════════════════════════

def create_labeled_training_set(
    candidates_df: pl.DataFrame,
    ground_truth_df: pl.DataFrame,
    prediction_type: str,     # "clicks", "carts", "orders"
    neg_pos_ratio: int = NEG_POS_RATIO,
    popular_neg_frac: float = POPULAR_NEG_FRAC,
    seed: int = 42,
) -> pl.DataFrame:
    """
    Tạo training set có label cho một loại prediction.
    
    Logic:
    1. Join candidates với ground truth → label=1 nếu khớp, else 0
    2. Lấy toàn bộ positives
    3. Sample negatives: 50% popular (hard) + 50% random (easy)
    """
    type_code = TYPE_LABELS[prediction_type]
    
    print(f"\n--- Creating training set for '{prediction_type}' (type={type_code}) ---")
    
    # Lấy ground truth cho type này
    # ground_truth_df (Polars) có cột type là Int8, so sánh bằng int
    type_gt = ground_truth_df.filter(pl.col("type") == type_code)
    
    if type_gt.height == 0:
        print(f"No ground truth found for type={type_code}. Check type column values.")
        print(f"     Available types: {ground_truth_df['type'].unique().to_list()}")
        # Fallback: return empty labeled candidates
        return candidates_df.head(0).with_columns(pl.lit(0).cast(pl.UInt8).alias("label"))
    
    # Explode ground_truth list → individual (session, candidate_aid)
    type_labels = (
        type_gt
        .explode("ground_truth")
        .rename({"ground_truth": "candidate_aid"})
        .with_columns(pl.lit(1).cast(pl.UInt8).alias("label"))
        .select(["session", "candidate_aid", "label"])
        .unique()
    )
    
    # Join labels
    labeled_df = candidates_df.join(
        type_labels,
        on=["session", "candidate_aid"],
        how="left",
    ).with_columns(pl.col("label").fill_null(0))
    
    # Tách positive / negative
    positives = labeled_df.filter(pl.col("label") == 1)
    negatives = labeled_df.filter(pl.col("label") == 0)
    
    n_pos = positives.height
    n_neg_target = min(n_pos * neg_pos_ratio, negatives.height)
    n_popular_neg = int(n_neg_target * popular_neg_frac)
    n_random_neg = n_neg_target - n_popular_neg
    
    print(f"  Positives: {n_pos:,}")
    print(f"  Negatives target: {n_neg_target:,} ({n_popular_neg:,} popular + {n_random_neg:,} random)")
    
    # Popular negatives: lấy những negatives có item_total_cnt cao
    if "item_total_cnt_all" in negatives.columns:
        popular_neg = (
            negatives
            .sort("item_total_cnt_all", descending=True)
            .head(n_popular_neg)
        )
    else:
        popular_neg = negatives.sample(n=min(n_popular_neg, negatives.height), seed=seed)
    
    # Random negatives: từ phần còn lại
    remaining = negatives.join(
        popular_neg.select(["session", "candidate_aid"]),
        on=["session", "candidate_aid"],
        how="anti",
    )
    random_neg = remaining.sample(
        n=min(n_random_neg, remaining.height),
        seed=seed,
    )
    
    # Concat
    final_cols = positives.columns
    final_df = pl.concat([
        positives,
        popular_neg.select(final_cols),
        random_neg.select(final_cols),
    ])
    
    print(f"  Final training set: {final_df.height:,} rows "
          f"(pos/neg ratio = 1:{(final_df.height - n_pos) / max(n_pos, 1):.1f})")
    
    return final_df


# --- Build toàn bộ training data theo chunks ---
popular_items = get_popular_items(train_full_history, n_days=7)

train_chunk_paths = build_training_data_chunked(
    history_df            = train_history,
    ground_truth_df       = train_gt,
    feature_source_df     = train_full_history,
    global_item_feats_all = global_item_feats_all,
    global_item_feats_7d  = global_item_feats_7d,
    df_clicks             = covisit_clicks,
    df_buys               = covisit_cart_order,
    df_buy2buy            = covisit_buy2buy,
    popular_df            = popular_items,
    out_dir               = TRAIN_DATA_DIR,
    chunk_size            = TRAIN_CHUNK_SIZE,
)

gc.collect()


# ══════════════════════════════════════════════════════════════════════════════
# CELL 8: LGBMRanker Training
# ══════════════════════════════════════════════════════════════════════════════

def get_feature_columns(df: pl.DataFrame) -> list:
    """Lấy danh sách feature columns (loại bỏ session, candidate_aid, label)."""
    ignore = {"session", "candidate_aid", "label"}
    return [c for c in df.columns if c not in ignore]


def train_lgbm_ranker(
    df: pl.DataFrame,
    model_type: str,
    params: dict = LGBM_PARAMS,
) -> tuple:
    """
    Train LGBMRanker cho một loại prediction.
    
    Returns: (model, feature_names)
    """
    print(f"\n{'='*60}")
    print(f"Training LGBMRanker for '{model_type}'")
    print(f"{'='*60}")
    
    # Sort by session (QUAN TRỌNG cho LGBMRanker)
    df = df.sort("session")
    
    feature_cols = get_feature_columns(df)
    print(f"  Features: {len(feature_cols)}")
    
    X = df.select(feature_cols).to_numpy()
    y = df.select("label").to_numpy().ravel()
    
    # Groups: số candidates mỗi session
    groups = df.group_by("session", maintain_order=True).len()["len"].to_numpy()
    
    print(f"  X shape: {X.shape}")
    print(f"  Positives: {y.sum():,.0f} | Negatives: {(1-y).sum():,.0f}")
    print(f"  Groups: {len(groups):,} sessions")
    
    # Train
    model = lgb.LGBMRanker(**params)
    
    model.fit(
        X, y,
        group=groups,
        eval_set=[(X, y)],
        eval_group=[groups],
        callbacks=[
            lgb.early_stopping(50, verbose=False),
            lgb.log_evaluation(100),
        ],
    )
    
    # Feature importance
    imp = sorted(
        zip(feature_cols, model.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    print(f"\n  Top 10 features:")
    for name, gain in imp[:10]:
        print(f"    {name:35s} → {gain:,.0f}")
    
    return model, feature_cols


# Train 3 models — đọc từng file parquet, concat rồi train
models = {}
feature_names = {}

for pred_type in ["clicks", "carts", "orders"]:
    paths = train_chunk_paths.get(pred_type, [])
    if not paths:
        print(f"[WARN] No training data for {pred_type}, skipping.")
        continue

    print(f"\nLoading {len(paths)} chunk files for '{pred_type}'...")
    # Đọc tuần tự và concat — mỗi file nhỏ nên vẫn an toàn RAM
    df_train = pl.concat([pl.read_parquet(str(p)) for p in paths])
    print(f"  Total rows: {df_train.height:,} | "
          f"Positives: {df_train['label'].sum():,.0f}")

    models[pred_type], feature_names[pred_type] = train_lgbm_ranker(
        df_train, model_type=pred_type,
    )
    del df_train
    gc.collect()

gc.collect()


# ══════════════════════════════════════════════════════════════════════════════
# CELL 9: Validation (Local CV)
# ══════════════════════════════════════════════════════════════════════════════

def run_validation(
    val_history_source: pl.DataFrame,
    val_gt_pd: pd.DataFrame,
    models: dict,
    feature_names: dict,
    global_item_feats_all: pl.DataFrame,
    global_item_feats_7d: pl.DataFrame,
    chunk_size: int = 50_000,
) -> dict:
    """
    Chạy full pipeline trên validation set (theo chunks) và tính Recall@20.
    
    Data flow (Local CV chuẩn):
    - test.parquet (val_history_source) = history của validation sessions
    - test_labels.parquet (val_gt_pd)   = ground truth
    """
    print(f"\n{'='*60}")
    print("Running Validation (Chunked Local CV)")
    print(f"{'='*60}")
    
    val_session_ids = val_history_source["session"].unique().sort().to_list()
    val_history = val_history_source.select(["session", "aid"]).unique()
    
    print(f"Val history: {val_history.height:,} session-aid pairs | "
          f"{val_history['session'].n_unique():,} sessions")
    
    n_sessions = len(val_session_ids)
    n_chunks = (n_sessions + chunk_size - 1) // chunk_size
    print(f"Processing validation in {n_chunks} chunks of {chunk_size:,} sessions...")
    
    all_top_20 = {
        "clicks": [],
        "carts": [],
        "orders": []
    }
    
    for chunk_idx in range(n_chunks):
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, n_sessions)
        chunk_sessions = val_session_ids[start:end]
        
        t0 = time.time()
        
        # Lọc history cho chunk này
        chunk_hist = val_history.filter(pl.col("session").is_in(chunk_sessions))
        chunk_hist_src = val_history_source.filter(pl.col("session").is_in(chunk_sessions))
        
        # 2. Generate candidates
        chunk_candidates = generate_candidates(
            chunk_hist,
            covisit_clicks,
            covisit_cart_order,
            covisit_buy2buy,
            popular_items,
            chunk_size=chunk_size,
        )
        
        # 3. Add features
        chunk_featured = add_all_features(
            chunk_candidates, 
            chunk_hist_src,
            global_item_feats_all,
            global_item_feats_7d,
        )
        
        # 4. Predict scores
        chunk_preds = chunk_featured.select(["session", "candidate_aid"]).clone()
        
        for pred_type in ["clicks", "carts", "orders"]:
            feats = feature_names[pred_type]
            # Đảm bảo tất cả feature columns tồn tại
            for f in feats:
                if f not in chunk_featured.columns:
                    chunk_featured = chunk_featured.with_columns(pl.lit(0.0).alias(f))
            
            X_val = chunk_featured.select(feats).to_numpy()
            scores = models[pred_type].predict(X_val)
            
            preds_type_df = chunk_featured.select(["session", "candidate_aid"]).with_columns(
                pl.Series("score", scores)
            )
            
            top_20 = (
                preds_type_df
                .sort("score", descending=True)
                .group_by("session", maintain_order=False)
                .head(20)
                .group_by("session")
                .agg(pl.col("candidate_aid").alias("predicted_aids"))
            )
            all_top_20[pred_type].append(top_20)
            
        elapsed = time.time() - t0
        print(f"  Chunk {chunk_idx+1}/{n_chunks}: {len(chunk_sessions):,} sessions completed in {elapsed:.1f}s")
        
        del chunk_hist, chunk_hist_src, chunk_candidates, chunk_featured, chunk_preds
        gc.collect()
    
    # 5. Tính Recall@20
    recalls = {}
    for pred_type in ["clicks", "carts", "orders"]:
        print(f"\nCalculating Recall@20 for '{pred_type}'...")
        # Combine all chunk predictions
        top_20_all = pl.concat(all_top_20[pred_type])
        top_20_all_pd = top_20_all.to_pandas()
        
        # Merge with ground truth
        # val_gt_pd["type"] is string, pred_type is also string → match directly
        gt_type = val_gt_pd[val_gt_pd["type"] == pred_type].copy()
        
        if gt_type.empty:
            # Try matching with integer type code
            gt_type = val_gt_pd[val_gt_pd["type"] == str(TYPE_LABELS[pred_type])].copy()
        
        if gt_type.empty:
            print(f" No ground truth for {pred_type}")
            print(f"     Available types: {val_gt_pd['type'].unique().tolist()}")
            recalls[pred_type] = 0.0
            continue
        
        merged = gt_type.merge(top_20_all_pd, on="session", how="left")
        
        predicted = [list(x) if hasattr(x, '__iter__') else [] for x in merged["predicted_aids"]]
        ground_truth = [list(x) if hasattr(x, '__iter__') else [] for x in merged["ground_truth"]]
        
        # Calculate hits
        hits = [
            len(set(gt).intersection(set(pred)))
            for gt, pred in zip(ground_truth, predicted)
        ]
        gt_counts = [min(len(gt), 20) for gt in ground_truth]
        
        recall = sum(hits) / max(sum(gt_counts), 1)
        recalls[pred_type] = recall
        print(f"  {pred_type:8s} Recall@20 = {recall:.5f}")
    
    # Weighted score
    weighted_score = sum(
        RECALL_WEIGHTS[t] * recalls[t] for t in recalls
    )
    print(f"\n  Weighted Score = {weighted_score:.5f}")
    print(f"    (0.10×clicks + 0.30×carts + 0.60×orders)")
    
    return recalls


# Run validation
val_recalls = run_validation(
    val_history_source=val_df, # Data đã load từ test.parquet
    val_gt_pd=val_gt,          # test_labels.parquet
    models=models, 
    feature_names=feature_names,
    global_item_feats_all=global_item_feats_all,
    global_item_feats_7d=global_item_feats_7d,
)


# ══════════════════════════════════════════════════════════════════════════════
# CELL 9.5: Serialization & Standalone Batch Inference Utilities
# ══════════════════════════════════════════════════════════════════════════════

def save_pipeline_artifacts(
    covisit_clicks: pl.DataFrame,
    covisit_cart_order: pl.DataFrame,
    covisit_buy2buy: pl.DataFrame,
    popular_items: pl.DataFrame,
    global_item_feats_all: pl.DataFrame,
    global_item_feats_7d: pl.DataFrame,
    models: dict,
    feature_names: dict,
    artifacts_dir: str = "/kaggle/working/artifacts"
):
    """
    Lưu tất cả co-visitation matrices, features, LightGBM models, và metadata xuống đĩa.
    """
    dir_path = Path(artifacts_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\nSaving pipeline artifacts to {dir_path}...")
    t0 = time.time()
    
    # Lưu Polars DataFrames dưới dạng parquet (nén tốt, đọc ghi cực nhanh)
    covisit_clicks.write_parquet(dir_path / "covisit_clicks.parquet")
    covisit_cart_order.write_parquet(dir_path / "covisit_cart_order.parquet")
    covisit_buy2buy.write_parquet(dir_path / "covisit_buy2buy.parquet")
    popular_items.write_parquet(dir_path / "popular_items.parquet")
    global_item_feats_all.write_parquet(dir_path / "global_item_feats_all.parquet")
    global_item_feats_7d.write_parquet(dir_path / "global_item_feats_7d.parquet")
    
    # Lưu các model LGBMRanker bằng pickle
    import pickle
    with open(dir_path / "models.pkl", "wb") as f:
        pickle.dump(models, f)
        
    # Lưu feature names bằng json
    import json
    with open(dir_path / "feature_names.json", "w") as f:
        json.dump(feature_names, f, indent=4)
        
    print(f"Artifacts saved successfully in {time.time() - t0:.1f}s!")


def load_pipeline_artifacts(
    artifacts_dir: str = "/kaggle/working/artifacts"
) -> tuple:
    """
    Load lại toàn bộ artifacts đã được lưu từ đĩa.
    """
    dir_path = Path(artifacts_dir)
    if not dir_path.exists():
        raise FileNotFoundError(f"Artifacts directory {dir_path} not found.")
        
    print(f"\nLoading pipeline artifacts from {dir_path}...")
    t0 = time.time()
    
    covisit_clicks = pl.read_parquet(dir_path / "covisit_clicks.parquet")
    covisit_cart_order = pl.read_parquet(dir_path / "covisit_cart_order.parquet")
    covisit_buy2buy = pl.read_parquet(dir_path / "covisit_buy2buy.parquet")
    popular_items = pl.read_parquet(dir_path / "popular_items.parquet")
    global_item_feats_all = pl.read_parquet(dir_path / "global_item_feats_all.parquet")
    global_item_feats_7d = pl.read_parquet(dir_path / "global_item_feats_7d.parquet")
    
    import pickle
    with open(dir_path / "models.pkl", "rb") as f:
        models = pickle.load(f)
        
    import json
    with open(dir_path / "feature_names.json", "r") as f:
        feature_names = json.load(f)
        
    print(f"Artifacts loaded successfully in {time.time() - t0:.1f}s!")
    return (
        covisit_clicks,
        covisit_cart_order,
        covisit_buy2buy,
        popular_items,
        global_item_feats_all,
        global_item_feats_7d,
        models,
        feature_names
    )


def recommend_for_batch(
    session_events: pl.DataFrame,
    covisit_clicks: pl.DataFrame,
    covisit_cart_order: pl.DataFrame,
    covisit_buy2buy: pl.DataFrame,
    popular_items: pl.DataFrame,
    global_item_feats_all: pl.DataFrame,
    global_item_feats_7d: pl.DataFrame,
    models: dict,
    feature_names: dict,
) -> dict:
    """
    Nhận vào DataFrame chứa lịch sử tương tác của một lô sessions (session, aid, ts, type).
    Trả về gợi ý top 20 (clicks, carts, orders) cho từng session dưới dạng python dict:
    {
        session_id: {
            "clicks": [aid1, aid2, ...],
            "carts": [aid1, aid2, ...],
            "orders": [aid1, aid2, ...]
        },
        ...
    }
    """
    sessions = session_events["session"].unique().to_list()
    results = {sess: {"clicks": [], "carts": [], "orders": []} for sess in sessions}
    
    # 1. Trích xuất history
    history = session_events.select(["session", "aid"]).unique()
    
    # 2. Tạo ứng viên
    candidates = generate_candidates(
        history,
        covisit_clicks,
        covisit_cart_order,
        covisit_buy2buy,
        popular_items,
        chunk_size=max(len(sessions), 1)
    )
    
    if candidates.height == 0:
        return results
        
    # 3. Thêm features
    featured = add_all_features(
        candidates,
        session_events,
        global_item_feats_all,
        global_item_feats_7d,
    )
    
    if featured.height == 0:
        return results
        
    # 4. Dự đoán điểm số và lọc top 20 cho mỗi mục tiêu
    for pred_type in ["clicks", "carts", "orders"]:
        feats = feature_names[pred_type]
        # Đảm bảo các feature tồn tại
        for f in feats:
            if f not in featured.columns:
                featured = featured.with_columns(pl.lit(0.0).alias(f))
                
        X = featured.select(feats).to_numpy()
        scores = models[pred_type].predict(X)
        
        preds_df = featured.select(["session", "candidate_aid"]).with_columns(
            pl.Series("score", scores)
        )
        
        top_20 = (
            preds_df
            .sort("score", descending=True)
            .group_by("session", maintain_order=False)
            .head(20)
            .group_by("session")
            .agg(pl.col("candidate_aid").alias("aids"))
        )
        
        for row in top_20.iter_rows():
            sess_id, aids = row
            if sess_id in results:
                results[sess_id][pred_type] = list(aids)
                
    return results


# ══════════════════════════════════════════════════════════════════════════════
# CELL 10: Test Inference & Submission
# ══════════════════════════════════════════════════════════════════════════════

def create_submission(
    test_df: pl.DataFrame,
    train_df: pl.DataFrame,
    models: dict,
    feature_names: dict,
    global_item_feats_all: pl.DataFrame,
    global_item_feats_7d: pl.DataFrame,
    output_path: str = "/kaggle/working/submission.csv",
    chunk_size: int = 50_000,
) -> pl.DataFrame:
    """
    Chạy full inference trên test set và tạo file submission theo chunks.
    """
    print(f"\n{'='*60}")
    print("Creating Submission (Chunked)")
    print(f"{'='*60}")
    
    # 1. History
    test_history = test_df.select(["session", "aid"]).unique()
    test_sessions = test_df["session"].unique().sort().to_list()
    
    n_sessions = len(test_sessions)
    n_chunks = (n_sessions + chunk_size - 1) // chunk_size
    print(f"Processing inference in {n_chunks} chunks of {chunk_size:,} sessions...")
    
    all_top_20 = {
        "clicks": [],
        "carts": [],
        "orders": []
    }
    
    for chunk_idx in range(n_chunks):
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, n_sessions)
        chunk_sess = test_sessions[start:end]
        
        t0 = time.time()
        
        # Filter history cho chunk này
        chunk_hist = test_history.filter(pl.col("session").is_in(chunk_sess))
        chunk_hist_src = test_df.filter(pl.col("session").is_in(chunk_sess))
        
        # 2. Candidates
        chunk_candidates = generate_candidates(
            chunk_hist,
            covisit_clicks,
            covisit_cart_order,
            covisit_buy2buy,
            popular_items,
            chunk_size=chunk_size,
        )
        
        # 3. Features
        chunk_featured = add_all_features(
            chunk_candidates, 
            chunk_hist_src,
            global_item_feats_all,
            global_item_feats_7d,
        )
        
        # 4. Predict
        for pred_type in ["clicks", "carts", "orders"]:
            feats = feature_names[pred_type]
            for f in feats:
                if f not in chunk_featured.columns:
                    chunk_featured = chunk_featured.with_columns(pl.lit(0.0).alias(f))
            
            X = chunk_featured.select(feats).to_numpy()
            scores = models[pred_type].predict(X)
            
            preds_type_df = chunk_featured.select(["session", "candidate_aid"]).with_columns(
                pl.Series("score", scores)
            )
            
            top_20 = (
                preds_type_df
                .sort("score", descending=True)
                .group_by("session", maintain_order=False)
                .head(20)
                .group_by("session")
                .agg(pl.col("candidate_aid").alias("aids"))
            )
            all_top_20[pred_type].append(top_20)
            
        elapsed = time.time() - t0
        print(f"  Chunk {chunk_idx+1}/{n_chunks}: {len(chunk_sess):,} sessions completed in {elapsed:.1f}s")
        
        del chunk_hist, chunk_hist_src, chunk_candidates, chunk_featured
        gc.collect()
        
    # 5. Format submission.csv (Optimized with Polars)
    print("\nFormatting submission (Optimized with Polars)...")
    t_fmt = time.time()
    
    submission_parts = []
    for pred_type in ["clicks", "carts", "orders"]:
        top_20_all = pl.concat(all_top_20[pred_type])
        
        # Biến đổi nhanh trên Polars: aids (list[int]) -> chuỗi string ngăn cách bằng dấu cách
        # Tạo cột session_type bằng cách cộng chuỗi
        top_20_all = top_20_all.with_columns([
            pl.col("aids").list.eval(pl.element().cast(pl.String)).list.join(" ").alias("labels"),
            (pl.col("session").cast(pl.String) + pl.lit(f"_{pred_type}")).alias("session_type")
        ]).select(["session_type", "labels"])
        
        submission_parts.append(top_20_all)
        
        del top_20_all
        gc.collect()
        
    submission = pl.concat(submission_parts)
    submission.write_csv(output_path)
    
    print(f"\n Submission saved: {output_path} | Formatting time: {time.time() - t_fmt:.1f}s")
    print(f"  Rows: {submission.height:,}")
    print(f"  Preview:")
    print(submission.head(6))
    
    return submission



# --- Tạo submission ---
test_raw = load_raw_data(KAGGLE_TEST_PARQUET)
submission = create_submission(test_raw, train_full_history, models, feature_names, global_item_feats_all, global_item_feats_7d)


# ══════════════════════════════════════════════════════════════════════════════
# CELL 11: Summary
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PIPELINE SUMMARY")
print("=" * 60)
print(f"Data:")
print(f"  Train events : {train_events_count:,}")
print(f"  Val events   : {val_df.height:,}")
print(f"\nCo-visitation Matrices:")
print(f"  Clicks     : {covisit_clicks.height:,} pairs")
print(f"  Cart-Order : {covisit_cart_order.height:,} pairs")
print(f"  Buy2Buy    : {covisit_buy2buy.height:,} pairs")
print(f"\nModels trained: {list(models.keys())}")
print(f"\nValidation Recall@20:")
for t, r in val_recalls.items():
    w = RECALL_WEIGHTS[t]
    print(f"  {t:8s}: {r:.5f} (weight={w:.2f}, contribution={w*r:.5f})")
weighted = sum(RECALL_WEIGHTS[t] * val_recalls[t] for t in val_recalls)
print(f"  {'TOTAL':8s}: {weighted:.5f}")
print("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# CELL 12: Save Artifacts & Demo Standalone Batch Inference
# ══════════════════════════════════════════════════════════════════════════════

# 1. Lưu các artifacts xuống thư mục /kaggle/working/artifacts
artifacts_dir = WORKING_DIR / "artifacts"
save_pipeline_artifacts(
    covisit_clicks=covisit_clicks,
    covisit_cart_order=covisit_cart_order,
    covisit_buy2buy=covisit_buy2buy,
    popular_items=popular_items,
    global_item_feats_all=global_item_feats_all,
    global_item_feats_7d=global_item_feats_7d,
    models=models,
    feature_names=feature_names,
    artifacts_dir=artifacts_dir
)

# 2. Demo chạy load lại và inference thử
print("\n" + "=" * 60)
print("DEMO: LOAD ARTIFACTS AND RUN STANDALONE BATCH INFERENCE")
print("=" * 60)

# Load lại từ đĩa để chứng minh sự độc lập
(
    loaded_clicks,
    loaded_cart_order,
    loaded_buy2buy,
    loaded_popular,
    loaded_feats_all,
    loaded_feats_7d,
    loaded_models,
    loaded_features
) = load_pipeline_artifacts(artifacts_dir=artifacts_dir)

# Lấy thử 3 session từ test set làm ví dụ
sample_sessions = test_raw["session"].unique().head(3).to_list()
sample_df = test_raw.filter(pl.col("session").is_in(sample_sessions))

print(f"\nRunning standalone inference for sample sessions: {sample_sessions}")
predictions = recommend_for_batch(
    session_events=sample_df,
    covisit_clicks=loaded_clicks,
    covisit_cart_order=loaded_cart_order,
    covisit_buy2buy=loaded_buy2buy,
    popular_items=loaded_popular,
    global_item_feats_all=loaded_feats_all,
    global_item_feats_7d=loaded_feats_7d,
    models=loaded_models,
    feature_names=loaded_features
)

# In kết quả gợi ý
for sess, preds in predictions.items():
    print(f"\nSuggestions for Session {sess}:")
    print(f"  - Clicks (Top 5): {preds['clicks'][:5]} (Total suggestions: {len(preds['clicks'])})")
    print(f"  - Carts  (Top 5): {preds['carts'][:5]} (Total suggestions: {len(preds['carts'])})")
    print(f"  - Orders (Top 5): {preds['orders'][:5]} (Total suggestions: {len(preds['orders'])})")
print("=" * 60)

