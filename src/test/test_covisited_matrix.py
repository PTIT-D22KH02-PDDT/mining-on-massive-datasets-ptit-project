# python -m  src.test.test_covisited_matrix
from pyspark.sql import SparkSession
from src.core.constant import DATASETS_DIR
from src.core import SparkService
covisited_path = DATASETS_DIR / "co_visited_unified.parquet"

if __name__ == "__main__":
    spark = SparkSession.builder.appName("TestReadParquet").getOrCreate()
    df = spark.read.parquet(str(covisited_path))
    df.show(truncate=False, n=5)  # In 5 dòng đầu, không cắt nội dung
    df.printSchema()
    print(f"Số lượng dòng: {df.count()}")
    spark.stop()