from src.core.infra.kafka import KafkaProducerService


def __getattr__(name):
    if name in ("SparkService", "_start_spark"):
        from src.core.infra.spark import SparkService, _start_spark
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["KafkaProducerService", "SparkService", "_start_spark"]
