from src.core import SparkService
from src.core.constant import DATASETS_FILEPATH


def main():
    spark_service = SparkService()
    # Load dataset
    data_path = str(DATASETS_FILEPATH)
    spark_service.spark_logger.info(f"Loading data from: {data_path}")
    df = spark_service.spark_session.read.parquet(data_path)


if __name__ == '__main__':
    main()