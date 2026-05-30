"""
src.core — shared infrastructure & utilities.

Exports:
    - cfg                   : Global config dict (from config/config.yml)
    - KafkaProducerService  : Async Kafka producer
    - SparkService          : Spark session wrapper
    - _start_spark          : Low-level Spark session builder
    - Log4j                 : Spark-aware logger
"""

from src.core.config import cfg
from src.core.infra.kafka import KafkaProducerService
from src.core.logging import Log4j


def __getattr__(name):
    if name in ("SparkService", "_start_spark"):
        from src.core.infra.spark import SparkService, _start_spark
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "cfg",
    "KafkaProducerService",
    "Log4j",
    "SparkService",
    "_start_spark",
]
