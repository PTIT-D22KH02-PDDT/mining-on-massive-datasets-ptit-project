import os.path

from dependencies import start_spark
from dependencies.constant import CONFIG_PATH, CONFIG_FILE_NAME, APP_NAME
from jobs.mining_job import analyze_data

def main():
    # Start Spark Session and get logger/config
    config_path = os.path.join(CONFIG_PATH, CONFIG_FILE_NAME)
    spark, logger, config = start_spark(
        app_name=APP_NAME,
        files=[config_path]
    )

    logger.info("Spark session started successfully!")
    
    if config:
        logger.info(f"Running job with config: {config}")
        # Run the actual job logic
        analyze_data(spark, config)
    else:
        logger.error("Failed to load configuration. Job aborted.")

    logger.info("Everything done!")
    spark.stop()

if __name__ == '__main__':
    main()