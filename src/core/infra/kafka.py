"""
Low-level Kafka infrastructure.
Focuses on Producer and Topic Management.
"""

import json
import logging
from typing import Any, Dict, Optional

from aiokafka import AIOKafkaProducer

from src.core.config import cfg

logger = logging.getLogger(__name__)


def _kafka_cfg() -> Dict[str, Any]:
    return cfg.get("kafka", {})


def _bootstrap_servers() -> str:
    import os

    return os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        _kafka_cfg().get("bootstrap_servers", "localhost:29092"),
    )


def _normalize_acks(val: Any) -> Any:
    if isinstance(val, int) or val == "all":
        return val
    if val in ("0", "1", "-1"):
        return int(val)
    return 1


class KafkaProducerService:
    """Simple wrapper for AIOKafkaProducer."""

    def __init__(self):
        self._bootstrap = _bootstrap_servers()
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        if self._producer:
            return
        producer_cfg = _kafka_cfg().get("producer", {})
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks=_normalize_acks(producer_cfg.get("acks", 1)),
            enable_idempotence=producer_cfg.get("enable_idempotence", False),
            linger_ms=producer_cfg.get("linger_ms", 10),
            request_timeout_ms=producer_cfg.get("request_timeout_ms", 5000),
        )
        await self._producer.start()

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def send_buffered(self, topic: str, message: Any, key: str | None = None):
        """Fire-and-forget: returns as soon as the message is buffered (no ack wait)."""
        if not self._producer:
            await self.start()
        encoded_key = key.encode("utf-8") if key else None
        return await self._producer.send(topic, message, key=encoded_key)
