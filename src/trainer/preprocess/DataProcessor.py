from typing import Optional

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from src.core import SparkService
from src.core.constant import SESSION_COLUMN_NAME, TS_COLUMN_NAME, AID_COLUMN_NAME, EVENT_PAIRS_PARQUET_FILE


class DataProcessor:
    def __init__(self, spark_service: SparkService):
        self.spark_service: SparkService = spark_service
        self.processed_df:Optional[DataFrame] = None

    def build_event_pairs(self, df: DataFrame, time_window_seconds=3600):
        # sort in desc order timestamp
        window_spec = Window.partitionBy(SESSION_COLUMN_NAME).orderBy(F.desc(TS_COLUMN_NAME))
        # Take last 30 events per session
        df = df.withColumn("rank", F.row_number().over(window_spec)) \
            .filter(F.col("rank") <= 30) \
            .drop("rank")
        # 3. Generate pairs via distributed self-join
        # Spark will handle the shuffling and distribution automatically
        df_alias = df.alias("y")
        pairs = df.alias("x").join(df_alias, SESSION_COLUMN_NAME)

        # Filters
        time_window_ms = time_window_seconds * 1000
        # remove self matches and remove pairs of event that happen too long(time_window_seconds)
        pairs = pairs.filter(
            (F.col(f"x.{AID_COLUMN_NAME}") != F.col(f"y.{AID_COLUMN_NAME}")) &  # Remove self-matches
            (F.abs(F.col(f"x.{TS_COLUMN_NAME}") - F.col(f"y.{TS_COLUMN_NAME}")) < time_window_ms)
        )

        # 5. Session-level de-duplication (count (A,B) once per session)
        # Also renames columns to avoid duplicate column name error when writing to parquet
        pairs = pairs.select(
            F.col(SESSION_COLUMN_NAME),
            F.col(f"x.{AID_COLUMN_NAME}").alias(f"{AID_COLUMN_NAME}1"),
            F.col(f"y.{AID_COLUMN_NAME}").alias(f"{AID_COLUMN_NAME}2")
        ).distinct()

        pairs.write.mode("overwrite").parquet(str(EVENT_PAIRS_PARQUET_FILE))
        print(f"Total event pairs: {pairs.count()}")


