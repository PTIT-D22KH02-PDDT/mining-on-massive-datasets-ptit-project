from typing import Optional

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions 
from src.core import SparkService
from src.core.constant import EVENT_PAIRS_PARQUET_FILE, AID_COLUMN_NAME, COVISITATION_MATRIX_PARQUET_FILE


class CovisitationMatrixBuilder:
    def __init__(self, spark_service: SparkService):
        self.spark_service: SparkService = spark_service
        self.matrix:Optional[DataFrame] = None
    def load_event_pairs(self):
        df = self.spark_service.spark_session.read.parquet(str(EVENT_PAIRS_PARQUET_FILE))
        return df
    def build_covisitation_matrix(self, top_k=20) -> None:
        # 6. Aggregate weights (count occurrences across all sessions)
        pairs = self.load_event_pairs()
        counts = pairs.groupBy(f"{AID_COLUMN_NAME}1", f"{AID_COLUMN_NAME}2").count()

        # 7. Keep top K candidates for each item
        top_k_window = (Window.partitionBy(f"{AID_COLUMN_NAME}1")
                        .orderBy(functions.desc("count")))

        matrix_df = counts.withColumn("rank", functions.row_number().over(top_k_window)) \
            .filter(functions.col("rank") <= top_k) \
            .drop("rank")
        matrix_df.write.mode("overwrite").parquet(str(COVISITATION_MATRIX_PARQUET_FILE))
    def load_covisitation_matrix(self):
        self.matrix = self.spark_service.spark_session.read.parquet(str(COVISITATION_MATRIX_PARQUET_FILE))