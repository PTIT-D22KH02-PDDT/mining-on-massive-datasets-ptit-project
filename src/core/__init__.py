"""
src.core — shared infrastructure & utilities.

Exports:
    - cfg                   : Global config dict (from config/config.yml)
    - KafkaProducerService  : Async Kafka producer
    - ensure_topics         : Auto-create topics from config
    - SparkService          : Spark session wrapper
    - _start_spark          : Low-level Spark session builder
    - Log4j                 : Spark-aware logger
"""

from src.core.config import cfg
from src.core.infra.kafka import KafkaProducerService, ensure_topics
from src.core.infra.spark import SparkService, _start_spark
from src.core.logging import Log4j
