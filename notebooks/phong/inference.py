"""
OTTO Recommender System — Standalone Inference Script

Tài liệu/Mã nguồn chạy inference độc lập cho hệ thống gợi ý OTTO.
Script này tự chứa (self-contained) toàn bộ logic sinh ứng viên (Candidate Generation), 
tính toán đặc trưng (Feature Engineering) và chấm điểm xếp hạng (Re-ranking bằng LightGBM), 
hoàn toàn không phụ thuộc vào mã nguồn huấn luyện.

Yêu cầu môi trường:
  - polars
  - numpy
  - lightgbm
"""

import os
import gc
import time
import json
import pickle
from pathlib import Path
import numpy as np
import polars as pl
import lightgbm as lgb

# ══════════════════════════════════════════════════════════════════════════════
# 1. Các hàm Load Artifacts
# ══════════════════════════════════════════════════════════════════════════════

def load_pipeline_artifacts(artifacts_dir: str) -> tuple:
    """
    Tải lại toàn bộ các tài nguyên (ma trận, đặc trưng toàn cục, mô hình) từ đĩa.
    
    Args:
        artifacts_dir: Đường dẫn đến thư mục chứa các file lưu trữ.
        
    Returns:
        tuple: (covisit_clicks, covisit_cart_order, covisit_buy2buy, popular_items, 
                global_item_feats_all, global_item_feats_7d, models, feature_names)
    """
    dir_path = Path(artifacts_dir)
    if not dir_path.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục artifacts tại: {dir_path}")
        
    print(f"\n[Inference] Đang tải các tài nguyên từ {dir_path}...")
    t0 = time.time()
    
    covisit_clicks = pl.read_parquet(dir_path / "covisit_clicks.parquet")
    covisit_cart_order = pl.read_parquet(dir_path / "covisit_cart_order.parquet")
    covisit_buy2buy = pl.read_parquet(dir_path / "covisit_buy2buy.parquet")
    popular_items = pl.read_parquet(dir_path / "popular_items.parquet")
    global_item_feats_all = pl.read_parquet(dir_path / "global_item_feats_all.parquet")
    global_item_feats_7d = pl.read_parquet(dir_path / "global_item_feats_7d.parquet")
    
    with open(dir_path / "models.pkl", "rb") as f:
        models = pickle.load(f)
        
    with open(dir_path / "feature_names.json", "r") as f:
        feature_names = json.load(f)
        
    print(f"[Inference] Tải tài nguyên thành công trong {time.time() - t0:.1f}s!")
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

# ══════════════════════════════════════════════════════════════════════════════
# 2. Pipeline Core (Candidates & Feature Engineering)
# ══════════════════════════════════════════════════════════════════════════════

def generate_candidates(
    history_df: pl.DataFrame,
    df_clicks: pl.DataFrame,
    df_buys: pl.DataFrame,
    df_buy2buy: pl.DataFrame,
    popular_df: pl.DataFrame,
    chunk_size: int = 50_000,
) -> pl.DataFrame:
    """
    Tạo danh sách ứng viên (candidate retrieval) từ 5 nguồn:
    History, Popular items, Co-visitation clicks, Co-visitation cart-order, Co-visitation buy2buy.
    """
    all_sessions = history_df["session"].unique().sort().to_list()
    n_sessions = len(all_sessions)
    n_chunks = (n_sessions + chunk_size - 1) // chunk_size
    
    all_candidates = []
    
    for chunk_idx in range(n_chunks):
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, n_sessions)
        chunk_sessions = all_sessions[start:end]
        
        # History cho chunk này
        history_chunk = history_df.filter(pl.col("session").is_in(chunk_sessions))
        
        # --- Nguồn 1: Lịch sử tương tác của user ---
        cand_history = (
            history_chunk
            .rename({"aid": "candidate_aid"})
            .with_columns(pl.lit(1).cast(pl.UInt8).alias("source_history"))
        )
        
        # --- Nguồn 2: Sản phẩm phổ biến ---
        sessions_in_chunk = history_chunk.select("session").unique()
        cand_popular = sessions_in_chunk.join(popular_df, how="cross")
        
        # --- Nguồn 3-5: Co-visitation matrices ---
        cand_clicks_raw = history_chunk.join(df_clicks, on="aid", how="inner")
        cand_buys_raw   = history_chunk.join(df_buys, on="aid", how="inner")
        cand_b2b_raw    = history_chunk.join(df_buy2buy, on="aid", how="inner")
        
        # --- Gộp tất cả ứng viên và lọc trùng trùng ---
        candidates_df = pl.concat([
            cand_history.select(["session", "candidate_aid"]),
            cand_popular.select(["session", "candidate_aid"]),
            cand_clicks_raw.select(["session", "candidate_aid"]),
            cand_buys_raw.select(["session", "candidate_aid"]),
            cand_b2b_raw.select(["session", "candidate_aid"]),
        ]).unique(subset=["session", "candidate_aid"])
        
        # --- Ghép lại các đặc trưng nguồn (source features) ---
        candidates_df = candidates_df.join(
            cand_history.select(["session", "candidate_aid", "source_history"]),
            on=["session", "candidate_aid"],
            how="left",
        )
        
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
        
    if not all_candidates:
        return pl.DataFrame(schema={
            "session": pl.Int64, "candidate_aid": pl.Int64, "source_history": pl.UInt8,
            "rank_clicks": pl.UInt16, "wgt_clicks": pl.Float32,
            "rank_cart_order": pl.UInt16, "wgt_cart_order": pl.Float32,
            "rank_buy2buy": pl.UInt16, "wgt_buy2buy": pl.Float32
        })
        
    result = pl.concat(all_candidates)
    return result


def create_session_features(df: pl.DataFrame) -> tuple:
    """Tạo các đặc trưng thống kê ở cấp độ session và sự tương tác."""
    # Session level
    session_feats = (
        df
        .group_by("session")
        .agg([
            pl.count().alias("session_length"),
            pl.col("aid").n_unique().alias("session_unique_aids"),
            pl.col("ts").max().alias("session_end_ts"),
            (pl.col("ts").max() - pl.col("ts").min()).alias("session_duration"),
            pl.col("type").filter(pl.col("type") == 0).count().alias("session_click_cnt"),
            pl.col("type").filter(pl.col("type") == 1).count().alias("session_cart_cnt"),
            pl.col("type").filter(pl.col("type") == 2).count().alias("session_order_cnt"),
        ])
    )
    
    session_feats = session_feats.with_columns([
        (pl.col("session_click_cnt") / (pl.col("session_length") + 1)).alias("session_click_ratio"),
        (pl.col("session_cart_cnt") / (pl.col("session_length") + 1)).alias("session_cart_ratio"),
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
    
    # Last item
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
    """Tạo và ghép nối toàn bộ các đặc trưng cho danh sách ứng viên."""
    df = candidates_df.clone()
    
    # Ghép global item features
    df = df.join(global_item_feats_all, on="candidate_aid", how="left")
    df = df.join(global_item_feats_7d, on="candidate_aid", how="left")
    
    # Tính toán session features cho các session đang xét
    active_sessions = df["session"].unique()
    session_history = feature_source_df.filter(pl.col("session").is_in(active_sessions))
    
    session_feats, interaction_feats, last_items = create_session_features(session_history)
    
    df = df.join(session_feats, on="session", how="left")
    df = df.join(interaction_feats, on=["session", "candidate_aid"], how="left")
    df = df.join(last_items, on="session", how="left")
    
    # Điền giá trị mặc định cho rank (999) và weight (0.0)
    for c in ["rank_clicks", "rank_cart_order", "rank_buy2buy"]:
        if c not in df.columns:
            df = df.with_columns(pl.lit(999).cast(pl.UInt16).alias(c))
        else:
            df = df.with_columns(pl.col(c).fill_null(999))
            
    for c in ["wgt_clicks", "wgt_cart_order", "wgt_buy2buy"]:
        if c not in df.columns:
            df = df.with_columns(pl.lit(0.0).cast(pl.Float32).alias(c))
        else:
            df = df.with_columns(pl.col(c).fill_null(0.0))
            
    # Tính toán đặc trưng phái sinh (Derived features)
    df = df.with_columns([
        # Click/Order trend
        (pl.col("item_click_cnt_7d").fill_null(0) / (pl.col("item_click_cnt_all").fill_null(0) + 10))
            .alias("click_trend_7d"),
        (pl.col("item_order_cnt_7d").fill_null(0) / (pl.col("item_order_cnt_all").fill_null(0) + 10))
            .alias("order_trend_7d"),
        (pl.col("item_buy_ratio_7d").fill_null(0) - pl.col("item_buy_ratio_all").fill_null(0))
            .alias("conversion_trend_diff"),
        
        # Rank diff
        (pl.col("rank_clicks") - pl.col("rank_buy2buy")).cast(pl.Int32).alias("rank_diff_click_b2b"),
        (pl.col("rank_cart_order") - pl.col("rank_buy2buy")).cast(pl.Int32).alias("rank_diff_buy_b2b"),
        
        # Combined weight
        (pl.col("wgt_buy2buy") * 2.0 + pl.col("wgt_cart_order") * 1.0).alias("combined_buy_weight"),
        
        # Recency
        (pl.col("session_end_ts") - pl.col("last_item_ts")).fill_null(7 * 24 * 3600).alias("recency_sec"),
        
        # Binary flags
        (pl.col("candidate_aid") == pl.col("last_aid")).cast(pl.Int8).fill_null(0).alias("is_last_viewed"),
        (pl.col("num_repetitions").fill_null(0) > 1).cast(pl.Int8).alias("is_repeated"),
        pl.col("source_history").fill_null(0),
    ])
    
    df = df.with_columns(
        pl.col("recency_sec").cast(pl.Float64).log1p().alias("log_recency")
    )
    
    df = df.with_columns([
        (pl.col("wgt_buy2buy") / (pl.col("log_recency") + 1)).alias("wgt_b2b_decayed"),
        (pl.col("wgt_clicks") / (pl.col("log_recency") + 1)).alias("wgt_clicks_decayed"),
    ])
    
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
    
    cols_to_drop = ["session_end_ts", "last_item_ts", "first_item_ts", "last_aid"]
    df = df.drop([c for c in cols_to_drop if c in df.columns])
    df = df.fill_null(0)
    
    return df

# ══════════════════════════════════════════════════════════════════════════════
# 3. Hàm Inference Chính (recommend_for_batch)
# ══════════════════════════════════════════════════════════════════════════════

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
    Sinh gợi ý top 20 (clicks, carts, orders) cho từng session trong lô đầu vào.
    
    Args:
        session_events: DataFrame chứa lịch sử (session, aid, ts, type).
        covisit_clicks, covisit_cart_order, covisit_buy2buy: Ma trận đồng truy cập.
        popular_items: Danh sách item phổ biến làm fallback.
        global_item_feats_all, global_item_feats_7d: Các đặc trưng item toàn cục.
        models: Dictionary chứa 3 model LGBMRanker đã train.
        feature_names: Dictionary chứa danh sách tên features của từng model.
        
    Returns:
        dict: { session_id: { "clicks": [aid1, ...], "carts": [...], "orders": [...] } }
    """
    sessions = session_events["session"].unique().to_list()
    results = {sess: {"clicks": [], "carts": [], "orders": []} for sess in sessions}
    
    # 1. Lấy thông tin history độc nhất
    history = session_events.select(["session", "aid"]).unique()
    
    # 2. Sinh ứng viên (Retrieval)
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
        
    # 3. Tạo đặc trưng (Feature Engineering)
    featured = add_all_features(
        candidates,
        session_events,
        global_item_feats_all,
        global_item_feats_7d,
    )
    
    if featured.height == 0:
        return results
        
    # 4. Dự đoán điểm số và xếp hạng top 20
    for pred_type in ["clicks", "carts", "orders"]:
        feats = feature_names[pred_type]
        
        # Đảm bảo các đặc trưng đầu vào mô hình yêu cầu đều tồn tại
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


def recommend_topk(
    click_sequence: list,
    covisit_clicks: pl.DataFrame,
    covisit_cart_order: pl.DataFrame,
    covisit_buy2buy: pl.DataFrame,
    popular_items: pl.DataFrame,
    global_item_feats_all: pl.DataFrame,
    global_item_feats_7d: pl.DataFrame,
    models: dict,
    feature_names: dict,
    type_sequence: list = None,
    ts_sequence: list = None,
    target_type: str = "clicks",
    k: int = 20,
    exclude_clicked: bool = True
) -> tuple:
    """
    Sinh gợi ý Top-K sản phẩm cho một session duy nhất từ chuỗi click và các hành động khác.
    
    Args:
        click_sequence: Danh sách các aid gốc tương tác trong session (ví dụ: [123, 456, ...]).
        covisit_clicks, covisit_cart_order, covisit_buy2buy: Ma trận đồng truy cập.
        popular_items: Danh sách item phổ biến làm fallback.
        global_item_feats_all, global_item_feats_7d: Các đặc trưng item toàn cục.
        models: Dictionary chứa 3 model LGBMRanker đã train.
        feature_names: Dictionary chứa danh sách tên features của từng model.
        type_sequence: Danh sách loại hành động tương ứng với click_sequence (0: click, 1: cart, 2: order/buy).
                       Nếu None, mặc định tất cả hành động là 0 (click).
        ts_sequence: Danh sách timestamp tương ứng với click_sequence.
                     Nếu None, mặc định sinh tự động tăng dần.
        target_type: Loại mô hình muốn gợi ý ("clicks", "carts", hoặc "orders").
        k: Số lượng gợi ý muốn lấy.
        exclude_clicked: Nếu True, sẽ lọc bỏ các item trong click_sequence khỏi kết quả gợi ý.
        
    Returns:
        tuple: (top_aids: list, top_scores: list)
    """
    if not click_sequence:
        # Fallback trả về popular items
        pop_aids = popular_items["candidate_aid"].head(k).to_list()
        return pop_aids, [0.0] * len(pop_aids)
        
    n_events = len(click_sequence)
    if type_sequence is None:
        type_sequence = [0] * n_events
    elif len(type_sequence) != n_events:
        raise ValueError("Độ dài type_sequence phải bằng độ dài click_sequence.")
        
    if ts_sequence is None:
        ts_sequence = list(range(n_events))
    elif len(ts_sequence) != n_events:
        raise ValueError("Độ dài ts_sequence phải bằng độ dài click_sequence.")
        
    # 1. Tạo session_events DataFrame giả lập cho 1 session duy nhất
    session_events = pl.DataFrame({
        "session": [0] * n_events,
        "aid": click_sequence,
        "ts": ts_sequence,
        "type": type_sequence
    })
    
    # 2. History unique
    history = session_events.select(["session", "aid"]).unique()
    
    # 3. Sinh ứng viên
    candidates = generate_candidates(
        history,
        covisit_clicks,
        covisit_cart_order,
        covisit_buy2buy,
        popular_items,
        chunk_size=1
    )
    
    # Fallback 1: Không tìm thấy ứng viên
    if candidates.height == 0:
        pop_aids = popular_items["candidate_aid"].to_list()
        if exclude_clicked:
            pop_aids = [aid for aid in pop_aids if aid not in click_sequence]
        top_aids = pop_aids[:k]
        return top_aids, [0.0] * len(top_aids)
        
    # 4. Tính đặc trưng
    featured = add_all_features(
        candidates,
        session_events,
        global_item_feats_all,
        global_item_feats_7d
    )
    
    # Fallback 2: Tính đặc trưng rỗng
    if featured.height == 0:
        pop_aids = popular_items["candidate_aid"].to_list()
        if exclude_clicked:
            pop_aids = [aid for aid in pop_aids if aid not in click_sequence]
        top_aids = pop_aids[:k]
        return top_aids, [0.0] * len(top_aids)
        
    # 5. Điền cột đặc trưng thiếu và Predict
    feats = feature_names[target_type]
    for f in feats:
        if f not in featured.columns:
            featured = featured.with_columns(pl.lit(0.0).alias(f))
            
    X = featured.select(feats).to_numpy()
    scores = models[target_type].predict(X)
    
    # Gom kết quả
    preds_df = featured.select(["candidate_aid"]).with_columns(
        pl.Series("score", scores)
    )
    
    # 6. Loại bỏ các aid đã click trong session
    if exclude_clicked:
        preds_df = preds_df.filter(~pl.col("candidate_aid").is_in(click_sequence))
        
    # 7. Sắp xếp giảm dần và lấy top k
    top_k_df = preds_df.sort("score", descending=True).head(k)
    top_aids = top_k_df["candidate_aid"].to_list()
    top_scores = [float(s) for s in top_k_df["score"].to_list()]
    
    # 8. Điền thêm popular items làm fallback nếu thiếu gợi ý
    if len(top_aids) < k:
        extra_needed = k - len(top_aids)
        pop_aids = popular_items["candidate_aid"].to_list()
        exclude_set = set(top_aids)
        if exclude_clicked:
            exclude_set.update(click_sequence)
        for aid in pop_aids:
            if aid not in exclude_set:
                top_aids.append(aid)
                top_scores.append(-99.0)
                if len(top_aids) == k:
                    break
                    
    return top_aids, top_scores


# ══════════════════════════════════════════════════════════════════════════════
# 4. Chương trình chính mẫu (Demo)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Thay đổi đường dẫn này trỏ tới thư mục chứa các file đã lưu của bạn
    ARTIFACTS_PATH = "./artifacts"
    
    print("============================================================")
    # Kiểm tra xem có thư mục artifacts mẫu để chạy demo không
    if not os.path.exists(ARTIFACTS_PATH):
        print(f"Lưu ý: Không tìm thấy thư mục '{ARTIFACTS_PATH}' ở vị trí hiện tại.")
        print("Vui lòng cấu hình ARTIFACTS_PATH trỏ đúng đến thư mục lưu trữ của bạn.")
        print("Dưới đây là ví dụ cách dự đoán từ chuỗi tương tác của người dùng:")
        print("============================================================")
        
        # Giả lập code chạy mẫu để người dùng dễ hình dung
        example_code = """
        # Khởi tạo chuỗi aid đã tương tác của người dùng
        click_sequence = [1492293, 910862, 1491172, 424964]
        # Loại tương tác tương ứng: 0: click, 1: cart, 2: order/buy
        type_sequence  = [0, 0, 1, 2] 
        
        # Load artifacts
        covisit_clicks, covisit_cart_order, covisit_buy2buy, popular_items, \\
        global_item_feats_all, global_item_feats_7d, models, feature_names = \\
            load_pipeline_artifacts(ARTIFACTS_PATH)
            
        # Dự đoán gợi ý
        top_aids, top_scores = recommend_topk(
            click_sequence=click_sequence,
            covisit_clicks=covisit_clicks,
            covisit_cart_order=covisit_cart_order,
            covisit_buy2buy=covisit_buy2buy,
            popular_items=popular_items,
            global_item_feats_all=global_item_feats_all,
            global_item_feats_7d=global_item_feats_7d,
            models=models,
            feature_names=feature_names,
            type_sequence=type_sequence,
            target_type="clicks",
            k=20,
            exclude_clicked=True
        )
        print("Gợi ý top-20:", top_aids)
        """
        print(example_code)
    else:
        # Load thực tế nếu thư mục tồn tại
        try:
            (
                covisit_clicks,
                covisit_cart_order,
                covisit_buy2buy,
                popular_items,
                global_item_feats_all,
                global_item_feats_7d,
                models,
                feature_names
            ) = load_pipeline_artifacts(ARTIFACTS_PATH)
            
            # Chuỗi click mẫu để chạy thử
            click_sequence = [1492293, 910862, 1491172, 424964]
            type_sequence  = [0, 0, 1, 2] # 2 click, 1 cart, 1 buy
            print(f"\nChạy thử recommend_topk với click_sequence: {click_sequence} và type_sequence: {type_sequence}")
            
            top_aids, top_scores = recommend_topk(
                click_sequence=click_sequence,
                covisit_clicks=covisit_clicks,
                covisit_cart_order=covisit_cart_order,
                covisit_buy2buy=covisit_buy2buy,
                popular_items=popular_items,
                global_item_feats_all=global_item_feats_all,
                global_item_feats_7d=global_item_feats_7d,
                models=models,
                feature_names=feature_names,
                type_sequence=type_sequence,
                target_type="clicks",
                k=20,
                exclude_clicked=True
            )
            
            print(f"\nKết quả gợi ý thành công cho loại 'clicks':")
            print(f"  Top-20 AIDs  : {top_aids}")
            print(f"  Top-5 Scores : {[f'{s:.4f}' for s in top_scores[:5]]} ...")
        except Exception as e:
            print(f"Có lỗi xảy ra khi chạy thử nghiệm: {e}")
    print("============================================================")

