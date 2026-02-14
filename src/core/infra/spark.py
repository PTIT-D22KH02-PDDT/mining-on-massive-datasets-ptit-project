"""
Spark infrastructure layer.

Reads spark settings from the global config (config/config.yml).
"""

import logging
from typing import Tuple

from pyspark.sql import SparkSession

from src.core import logging as spark_logging
from src.core.config import cfg

logger = logging.getLogger(__name__)


def _spark_cfg():
    return cfg.get("spark", {})


class SparkService:
    """Convenience wrapper around a SparkSession + Log4j logger."""

    def __init__(self):
        spark_session, spark_logger = _start_spark()
        self.spark_session = spark_session
        self.spark_logger = spark_logger
        self.context = self.spark_session.sparkContext


def _start_spark(app_name: str | None = None) -> Tuple[SparkSession, spark_logging.Log4j]:
    """
    Start Spark session using settings from config/config.yml.
    """
    sc = _spark_cfg()
    master = sc.get("master", "local[*]")
    name = app_name or sc.get("app_name", "pyspark-app")

    builder = (
        SparkSession
        .builder
        .master(master)
        .appName(name)
    )

    # Apply any extra spark config from the YAML
    for key, value in sc.get("config", {}).items():
        builder = builder.config(key, str(value))

    spark_sess = builder.getOrCreate()
    spark_logger = spark_logging.Log4j(spark_sess)

    logger.info(f"SparkSession started → master={master}  app={name}")
    return spark_sess, spark_logger
