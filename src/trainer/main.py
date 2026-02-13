from src.core import start_spark


def main():
    spark, logger = start_spark()
    logger.info("Spark session started successfully!")
    spark.stop()

if __name__ == '__main__':
    main()