from src.core import _start_spark


def main():
    spark, logger = _start_spark()
    logger.info("Spark session started successfully!")
    spark.stop()

if __name__ == '__main__':
    main()