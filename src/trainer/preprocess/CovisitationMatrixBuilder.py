from pyspark.sql import DataFrame, Window, functions
from pyspark.sql import functions as F
from src.core import SparkService
from src.core.constant import (
    AID_COLUMN_NAME, SESSION_COLUMN_NAME, TS_COLUMN_NAME, TYPE_COLUMN_NAME,
    CARTS_ORDERS_MATRIX_PARQUET_FILE, BUY2BUY_MATRIX_PARQUET_FILE, CLICKS_MATRIX_PARQUET_FILE,
    PAIRS_24H_PARQUET_FILE, PAIRS_14D_BUY2BUY_PARQUET_FILE, CLICK_TYPE, CART_TYPE, ORDER_TYPE,
    WEIGHT_INTERMEDIATE_COLUMN, DATASETS_FILEPATH, EVENTS_COLUMN_NAME
)


class CovisitationMatrixBuilder:
    def __init__(self, spark_service: SparkService):
        self.spark_service: SparkService = spark_service

    @staticmethod
    def _save_top_k(counts: DataFrame, output_path: str, top_k: int) -> None:
        """Helper to keep top K candidates per item and save to parquet."""
        # Repartitioning ensures all candidates for an AID are on the same executor
        # before the window function, preventing memory skew and OOM.
        aid1_col = f"{AID_COLUMN_NAME}1"

        # Optimization: Only repartition if we have enough data to justify it.
        # Window function will trigger a shuffle anyway if not partitioned by aid1_col.
        window_spec = Window.partitionBy(aid1_col).orderBy(F.desc(WEIGHT_INTERMEDIATE_COLUMN),
                                                           F.desc(f"{AID_COLUMN_NAME}2"))

        matrix_df = counts.withColumn("rank", F.row_number().over(window_spec)) \
            .filter(F.col("rank") <= top_k) \
            .drop("rank")

        # Coalesce to fewer files if the result is small enough,
        # but for top-k co-visitation, it's usually still large.
        # We use overwrite mode which can be space-intensive as it writes to a temp dir first.
        matrix_df.write.mode("overwrite").parquet(str(output_path))

    def build_carts_orders_matrix(self) -> None:
        """1) 'Carts Orders' Co-visitation Matrix - Type Weighted"""
        pairs = self.spark_service.spark_session.read.parquet(str(PAIRS_24H_PARQUET_FILE))

        # Map weights using string keys: clicks: 1, carts: 6, orders: 3
        type_weights = F.create_map([
            F.lit(CLICK_TYPE), F.lit(1),
            F.lit(CART_TYPE), F.lit(6),
            F.lit(ORDER_TYPE), F.lit(3)
        ])

        # Aggregate weights directly to save a shuffle stage (skipping dropDuplicates)
        counts = pairs.withColumn(WEIGHT_INTERMEDIATE_COLUMN, type_weights[F.col(f"{TYPE_COLUMN_NAME}2")]) \
            .groupBy(f"{AID_COLUMN_NAME}1", f"{AID_COLUMN_NAME}2") \
            .agg(F.sum(WEIGHT_INTERMEDIATE_COLUMN).alias(WEIGHT_INTERMEDIATE_COLUMN))

        self._save_top_k(counts, CARTS_ORDERS_MATRIX_PARQUET_FILE, top_k=15)

    def build_buy2buy_matrix(self) -> None:
        """2) 'Buy2Buy' Co-visitation Matrix"""
        pairs = self.spark_service.spark_session.read.parquet(str(PAIRS_14D_BUY2BUY_PARQUET_FILE))

        # Aggregate
        counts = pairs.groupBy(f"{AID_COLUMN_NAME}1", f"{AID_COLUMN_NAME}2") \
            .agg(F.count(SESSION_COLUMN_NAME).alias(WEIGHT_INTERMEDIATE_COLUMN))

        self._save_top_k(counts, BUY2BUY_MATRIX_PARQUET_FILE, top_k=15)

    def build_clicks_matrix(self, min_ts: int, max_ts: int) -> None:
        """3) 'Clicks' Co-visitation Matrix - Time Weighted"""
        pairs = self.spark_service.spark_session.read.parquet(str(PAIRS_24H_PARQUET_FILE))

        # Time weighting formula: 1 + 3 * (ts - min) / (max - min)
        # Aggregate directly to save a shuffle stage
        counts = pairs.withColumn(WEIGHT_INTERMEDIATE_COLUMN,
                                  1 + 3 * (F.col(f"{TS_COLUMN_NAME}1") - min_ts) / (max_ts - min_ts)) \
            .groupBy(f"{AID_COLUMN_NAME}1", f"{AID_COLUMN_NAME}2") \
            .agg(F.sum(WEIGHT_INTERMEDIATE_COLUMN).alias(WEIGHT_INTERMEDIATE_COLUMN))

        self._save_top_k(counts, CLICKS_MATRIX_PARQUET_FILE, top_k=20)


def main():
    spark_service = SparkService()
    # Load dataset
    data_path = str(DATASETS_FILEPATH)
    spark_service.spark_logger.info(f"Loading data from: {data_path}")
    df = spark_service.spark_session.read.parquet(data_path)
    df = df.select(
        functions.col(SESSION_COLUMN_NAME),
        functions.explode(functions.col(EVENTS_COLUMN_NAME)).alias(EVENTS_COLUMN_NAME),
    ).select(
        functions.col(SESSION_COLUMN_NAME),
        functions.col(f"{EVENTS_COLUMN_NAME}.{AID_COLUMN_NAME}").alias(AID_COLUMN_NAME),
        functions.col(f"{EVENTS_COLUMN_NAME}.{TS_COLUMN_NAME}").alias(TS_COLUMN_NAME),
        functions.col(f"{EVENTS_COLUMN_NAME}.{TYPE_COLUMN_NAME}").alias(TYPE_COLUMN_NAME),
    )

    # data_processor = DataProcessor(spark_service)
    # # 1. Create intermediate pairs to save RAM
    # spark_service.spark_logger.info("Creating intermediate pairs (disk-based)...")
    # data_processor.build_intermediate_pairs(df)

    covisition_matrix = CovisitationMatrixBuilder(spark_service)
    # 2. Build the 3 matrices using the saved pairs
    spark_service.spark_logger.info("Building Carts Orders Matrix...")
    # covisition_matrix.build_carts_orders_matrix()

    # spark_service.spark_logger.info("Building Buy2Buy Matrix...")
    # covisition_matrix.build_buy2buy_matrix()

    # spark_service.spark_logger.info("Building Clicks Matrix...")
    # # Get min/max ts for clicks weighting
    stats = df.select(functions.min(TS_COLUMN_NAME), functions.max(TS_COLUMN_NAME)).collect()[0]
    covisition_matrix.build_clicks_matrix(min_ts=stats[0], max_ts=stats[1])


if __name__ == '__main__':
    main()