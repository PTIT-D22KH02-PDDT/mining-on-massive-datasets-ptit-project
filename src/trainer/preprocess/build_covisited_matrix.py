"""
build_covisit_unified.py
=========================
Tạo 1 co-visitation matrix duy nhất, gộp tất cả event type.

Công thức weight mỗi cặp (aid_a, aid_b) trong 1 session:
    wgt = event_bonus(type_a, type_b)

    Bảng bonus (symmetric):
        click  + click  = 1.0
        click  + cart   = 3.0
        click  + order  = 4.0
        cart   + cart   = 6.0
        cart   + order  = 7.0
        order  + order  = 10.0

Undirected: luôn normalize aid_a < aid_b trước khi group → (A,B) và (B,A) cộng gộp chung.

Output schema (parquet):
    aid        : long
    candidates : array<struct<aid2: long, wgt: double>>   ← sorted desc by wgt, top-K
"""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from src.core import SparkService
from src.core.constant import (
    AID_COLUMN_NAME, SESSION_COLUMN_NAME, TS_COLUMN_NAME, TYPE_COLUMN_NAME,
    CLICK_TYPE, CART_TYPE, ORDER_TYPE,
    DATASETS_FILEPATH, DATASETS_DIR,
)

OUTPUT_PATH   = DATASETS_DIR / "co_visited_unified.parquet"
TOP_K         = 20
TAIL_SIZE     = 30          # giữ 30 event cuối mỗi session (tránh explosion)
TIME_WINDOW_S = 24 * 3600   # chỉ ghép cặp nếu |ts_a - ts_b| < 24h (ts tính bằng ms)
WINDOW_SIZE = 5

AID_A = "aid_a"
AID_B = "aid_b"
TYPE_A = "type_a"
TYPE_B = "type_b"
WGT   = "wgt"
CANDIDATES = "candidates"

# Bước 1 & 2: Gom nhóm, lấy tail & sinh cặp (undirected, 24h window) dùng duy nhất 1 lần Shuffle
def _generate_pairs(df: DataFrame, tail_size: int = TAIL_SIZE) -> DataFrame:
    """
    Gom nhóm theo session, lấy tail_size event cuối cùng của mỗi session,
    sau đó sinh cặp (undirected, 24h window) dùng sliding window ±5 event.
    """
    time_window_ms = TIME_WINDOW_S * 1000

    # B1: gom session thành list events (sắp xếp giảm dần để lấy tail, sau đó tăng dần)
    df_grouped = (
        df.groupBy(SESSION_COLUMN_NAME)
        .agg(
            F.sort_array(
                F.collect_list(
                    F.struct(
                        F.col(TS_COLUMN_NAME).alias("ts"),
                        F.col(AID_COLUMN_NAME).alias("aid"),
                        F.col(TYPE_COLUMN_NAME).alias("type"),
                    )
                ),
                asc=False
            ).alias("events_desc")
        )
        .withColumn("events_tail", F.slice("events_desc", 1, tail_size))
        .withColumn("events", F.sort_array("events_tail", asc=True))
        .drop("events_desc", "events_tail")
    )

    # B2: explode + lấy window trước/sau
    pairs = (
        df_grouped
        .select("*", F.posexplode("events").alias("i", "event"))
        # 5 event sau
        .withColumn(
            "after",
            F.expr(f"slice(events, cast(i + 2 as int), {WINDOW_SIZE})")
        )
        # 5 event trước
        .withColumn(
            "before",
            F.expr(f"slice(events, cast(greatest(1, i + 1 - {WINDOW_SIZE}) as int), cast(least({WINDOW_SIZE}, i) as int))")
        )
        # gộp
        .withColumn("neighbors", F.concat("before", "after"))
        .withColumn("neighbor", F.explode("neighbors"))
        # FILTER
        .filter(
            (F.col("event.aid") != F.col("neighbor.aid")) &
            (F.abs(F.col("event.ts") - F.col("neighbor.ts")) < time_window_ms)
        )
        # NORMALIZE UNDIRECTED
        .select(
            SESSION_COLUMN_NAME,

            F.least(F.col("event.aid"), F.col("neighbor.aid")).alias(AID_A),
            F.greatest(F.col("event.aid"), F.col("neighbor.aid")).alias(AID_B),

            F.when(
                F.col("event.aid") < F.col("neighbor.aid"),
                F.col("event.type")
            ).otherwise(F.col("neighbor.type")).alias(TYPE_A),

            F.when(
                F.col("event.aid") < F.col("neighbor.aid"),
                F.col("neighbor.type")
            ).otherwise(F.col("event.type")).alias(TYPE_B),
        )

        # tránh duplicate trong cùng session
        .dropDuplicates([SESSION_COLUMN_NAME, AID_A, AID_B, TYPE_A, TYPE_B])
    )

    return pairs

# Tính event bonus
def _apply_event_bonus(pairs: DataFrame) -> DataFrame:
    """
    Gán điểm thưởng dựa trên combination của (type_a, type_b).
    Vì đã normalize aid_a < aid_b, type_a/type_b không nhất thiết theo thứ tự
    → dùng LEAST/GREATEST trên type để map symmetric.

    Bảng bonus:
        click+click=1  click+cart=3   click+order=4
                       cart+cart=6    cart+order=7
                                      order+order=10
    """
    # Dùng least/greatest để đảm bảo symmetric khi lookup
    t_lo = F.least(F.col(TYPE_A),   F.col(TYPE_B))    # type "nhỏ hơn" alphabetically
    t_hi = F.greatest(F.col(TYPE_A), F.col(TYPE_B))

    bonus = (
        F.when((t_lo == CLICK_TYPE)  & (t_hi == CLICK_TYPE),  F.lit(1.0))
         .when((t_lo == CART_TYPE)   & (t_hi == CART_TYPE),   F.lit(6.0))
         .when((t_lo == ORDER_TYPE)  & (t_hi == ORDER_TYPE),  F.lit(10.0))
         .when((t_lo == CART_TYPE)   & (t_hi == CLICK_TYPE),  F.lit(3.0))
         .when((t_lo == CLICK_TYPE)  & (t_hi == ORDER_TYPE),  F.lit(4.0))
         .when((t_lo == CART_TYPE)   & (t_hi == ORDER_TYPE),  F.lit(7.0))
         .otherwise(F.lit(1.0))    # fallback an toàn
    )
    return pairs.withColumn(WGT, bonus)


# ─────────────────────────────────────────────────────────────
# Bước 4: Aggregate → top-K → group thành array
# ─────────────────────────────────────────────────────────────
def _aggregate_and_group(pairs: DataFrame, top_k: int = TOP_K) -> DataFrame:
    # 4a. Tổng weight qua tất cả session
    counts = (
        pairs
        .groupBy(AID_A, AID_B)
        .agg(F.sum(WGT).alias(WGT))
    )

    # 4b. Tạo 2 chiều từ undirected: (aid_a→aid_b) và (aid_b→aid_a)
    #     vì khi lookup "neighbors của X", X có thể nằm ở cột aid_a hoặc aid_b
    forward  = counts.select(F.col(AID_A).alias("aid1"), F.col(AID_B).alias("aid2"), WGT)
    backward = counts.select(F.col(AID_B).alias("aid1"), F.col(AID_A).alias("aid2"), WGT)
    both = forward.union(backward)

    # Tối ưu hóa: Repartition rõ ràng theo 'aid1' để chia đều dữ liệu trước khi chạy Window rank
    # Điều này tránh skew OOM trên các executor khi một số aid1 cực kỳ hot.
    both_partitioned = both.repartition(200, "aid1")

    # 4c. Top-K per aid1 bằng Window rank
    w = Window.partitionBy("aid1").orderBy(F.desc(WGT), F.desc("aid2"))
    top_k_df = (
        both_partitioned
        .withColumn("_rank", F.row_number().over(w))
        .filter(F.col("_rank") <= top_k)
        .drop("_rank")
    )

    # 4d. Collect thành array struct, sort desc theo wgt
    result = (
        top_k_df
        # Đưa wgt lên trước để sort_array hoạt động chính xác theo score (wgt)
        .withColumn("candidate_sortable", F.struct(F.col(WGT).alias("wgt"), F.col("aid2").alias("aid2")))
        .groupBy("aid1")
        .agg(
            F.sort_array(F.collect_list("candidate_sortable"), asc=False).alias("sorted_candidates")
        )
        # Khôi phục về schema struct chuẩn array<struct<aid2: long, wgt: double>>
        .withColumn(
            CANDIDATES,
            F.expr("transform(sorted_candidates, x -> struct(x.aid2 as aid2, x.wgt as wgt))")
        )
        .drop("sorted_candidates")
        .withColumnRenamed("aid1", AID_COLUMN_NAME)
    )
    return result


# ─────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────
def build_covisit_unified(
    spark_service: SparkService,
    output_path: str = OUTPUT_PATH,
    top_k: int = TOP_K,
    tail_size: int = TAIL_SIZE,
) -> None:
    spark = spark_service.spark_session
    logger = spark_service.spark_logger

    # 0. Load & flatten
    logger.info("Loading dataset...")

    df = (
        spark.read.parquet(str(DATASETS_FILEPATH))
        .select(
            F.col(SESSION_COLUMN_NAME),
            F.col(AID_COLUMN_NAME),
            F.col(TS_COLUMN_NAME),
            F.col(TYPE_COLUMN_NAME),
        )
        .repartition(100, SESSION_COLUMN_NAME)
    )

    # 1 & 2. Gom nhóm, tail & sinh pairs cực kỳ tối ưu (chỉ 1 lần Shuffle, không dùng Window)
    logger.info(f"Generating pairs with last {tail_size} events per session...")
    pairs = _generate_pairs(df, tail_size)

    # 3. Event bonus
    logger.info("Applying event bonus...")
    pairs_weighted = _apply_event_bonus(pairs)

    # 4. Aggregate + top-K + group
    logger.info(f"Aggregating and keeping top-{top_k} candidates per aid...")
    result = _aggregate_and_group(pairs_weighted, top_k)

    # 5. Save
    logger.info(f"Saving to {output_path}...")
    result.write.mode("overwrite").parquet(str(output_path))
    logger.info("Done!")


def main():
    spark_service = SparkService()
    build_covisit_unified(spark_service)


if __name__ == "__main__":
    main()
