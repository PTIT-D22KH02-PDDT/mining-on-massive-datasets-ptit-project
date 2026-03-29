from src.core import SparkService
from src.core.constant import DATASETS_FILEPATH, SESSION_COLUMN_NAME, AID_COLUMN_NAME, TS_COLUMN_NAME, \
    EVENTS_COLUMN_NAME, TYPE_COLUMN_NAME
from pyspark.sql import functions


def main():
    spark_service = SparkService()
    try:
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
    finally:
        spark_service.stop()

if __name__ == '__main__':
    main()