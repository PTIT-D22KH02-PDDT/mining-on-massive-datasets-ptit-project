"""
Low-level Kafka infrastructure.
Focuses on Producer and Topic Management.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from aiokafka import AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from src.core.config import cfg

logger = logging.getLogger(__name__)

def _kafka_cfg() -> Dict[str, Any]:
    return cfg.get("kafka", {})

def _bootstrap_servers() -> str:
    return _kafka_cfg().get("bootstrap_servers", "localhost:29092")

async def ensure_topics() -> tuple[List[str], bool]:
    """
    Auto-create topics from config.yml.
    Returns (topic_list, newly_created_flag)
    """
    topic_defs = _kafka_cfg().get("topics", {})
    if not topic_defs:
        return [], False

    admin = AIOKafkaAdminClient(bootstrap_servers=_bootstrap_servers())
    await admin.start()

    created = []
    newly_created = False
    try:
        for td in topic_defs.values():
            new_topic = NewTopic(
                name=td["name"],
                num_partitions=td.get("partitions", 1),
                replication_factor=td.get("replication_factor", 1),
            )
            try:
                await admin.create_topics([new_topic])
                logger.info(f"Created topic: {td['name']}")
                created.append(td["name"])
                newly_created = True
            except TopicAlreadyExistsError:
                created.append(td["name"])
    finally:
        await admin.close()

    return created, newly_created

class KafkaProducerService:
    """Simple wrapper for AIOKafkaProducer."""
    
    def __init__(self):
        self._bootstrap = _bootstrap_servers()
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        if self._producer: return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            enable_idempotence=True
        )
        await self._producer.start()

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def send(self, topic: str, message: Any, key: str | None = None):
        if not self._producer: await self.start()
        encoded_key = key.encode("utf-8") if key else None
        return await self._producer.send_and_wait(topic, message, key=encoded_key)
