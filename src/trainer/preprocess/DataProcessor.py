from typing import Optional

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from src.core import SparkService
from src.core.constant import (
    SESSION_COLUMN_NAME, TS_COLUMN_NAME, AID_COLUMN_NAME, TYPE_COLUMN_NAME,
    PAIRS_24H_PARQUET_FILE, PAIRS_14D_BUY2BUY_PARQUET_FILE, TAIL_SIZE, ONE_DAY_IN_SECONDS, CART_TYPE, ORDER_TYPE,
    FOURTEEN_DAYS_IN_SECONDS
)


class DataProcessor:
    def __init__(self, spark_service: SparkService):
        self.spark_service: SparkService = spark_service

    @staticmethod
    def _get_session_tail(df: DataFrame, tail_size: int = 30) -> DataFrame:
        """Helper to get the last N events for each session."""
        window_spec = Window.partitionBy(SESSION_COLUMN_NAME).orderBy(F.desc(TS_COLUMN_NAME))
        return df.withColumn("rank", F.row_number().over(window_spec)) \
            .filter(F.col("rank") <= tail_size) \
            .drop("rank")

    @staticmethod
    def _generate_pairs(df: DataFrame, time_window_seconds: int) -> DataFrame:
        """Helper to generate pairs within a time window (ts in ms)."""
        df_alias = df.alias("y")
        pairs = df.alias("x").join(df_alias, SESSION_COLUMN_NAME)

        # Filter: Remove self-matches and apply time window (is in ms)
        time_window_ms = time_window_seconds * 1000
        return pairs.filter(
            (F.col(f"x.{AID_COLUMN_NAME}") != F.col(f"y.{AID_COLUMN_NAME}")) &
            (F.abs(F.col(f"x.{TS_COLUMN_NAME}") - F.col(f"y.{TS_COLUMN_NAME}")) < time_window_ms)
        )

    def build_intermediate_pairs(self, df: DataFrame) -> None:
        """Generates and saves intermediate pairs to disk"""
        # 1. Pairs for Carts/Orders and Clicks (24h window, last 30 events)
        self.spark_service.spark_logger.info("Generating 24h intermediate pairs...")
        df_tail = self._get_session_tail(df, TAIL_SIZE)
        pairs_24h = self._generate_pairs(df_tail, ONE_DAY_IN_SECONDS)

        pairs_24h = pairs_24h.select(
            SESSION_COLUMN_NAME,
            F.col(f"x.{AID_COLUMN_NAME}").alias(f"{AID_COLUMN_NAME}1"),
            F.col(f"y.{AID_COLUMN_NAME}").alias(f"{AID_COLUMN_NAME}2"),
            F.col(f"x.{TS_COLUMN_NAME}").alias(f"{TS_COLUMN_NAME}1"),
            F.col(f"y.{TYPE_COLUMN_NAME}").alias(f"{TYPE_COLUMN_NAME}2")
        )
        pairs_24h.write.mode("overwrite").parquet(str(PAIRS_24H_PARQUET_FILE))

        # 2. Pairs for Buy2Buy (14d window, last 30 events, only carts/orders)
        self.spark_service.spark_logger.info("Generating 14d Buy2Buy intermediate pairs...")
        df_buys = df.filter(F.col(TYPE_COLUMN_NAME).isin([CART_TYPE, ORDER_TYPE]))
        df_buys_tail = self._get_session_tail(df_buys, TAIL_SIZE)
        pairs_14d = self._generate_pairs(df_buys_tail, FOURTEEN_DAYS_IN_SECONDS)

        pairs_14d = pairs_14d.select(
            SESSION_COLUMN_NAME,
            F.col(f"x.{AID_COLUMN_NAME}").alias(f"{AID_COLUMN_NAME}1"),
            F.col(f"y.{AID_COLUMN_NAME}").alias(f"{AID_COLUMN_NAME}2")
        ).distinct()  # Buy2Buy counts unique session-pairs
        pairs_14d.write.mode("overwrite").parquet(str(PAIRS_14D_BUY2BUY_PARQUET_FILE))


