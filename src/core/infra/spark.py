import os
from typing import Tuple

from dotenv import load_dotenv
from pyspark.sql import SparkSession

from src.core import logging

load_dotenv()
class SparkService:
    def __init__(self):
        spark_session, spark_logger = _start_spark()
        self.spark_session = spark_session
        self.spark_logger = spark_logger
        self.context = self.spark_session.sparkContext

def _start_spark(app_name: str = 'my_spark_app') -> Tuple[SparkSession, logging.Log4j]:
    """
    Start Spark session, get Spark logger
    """

    master = os.getenv('SPARK_MASTER', 'local[*]')

    spark_builder = (
        SparkSession
        .builder
        .master(master)
        .appName(app_name))
    # Create session and logger
    spark_sess = spark_builder.getOrCreate()
    spark_logger = logging.Log4j(spark_sess)

    return spark_sess, spark_logger
