"""
spark.py
~~~~~~~~

Module containing helper function for use with Apache Spark
"""
import os
from typing import Tuple

from dotenv import load_dotenv
from pyspark.sql import SparkSession

from src.core import logging

load_dotenv()

def start_spark(app_name: str = 'my_spark_app') -> Tuple[SparkSession, logging.Log4j]:
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
