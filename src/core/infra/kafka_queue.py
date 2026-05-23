"""
Dedicated Kafka producer queue.

Decouples API handlers from Kafka produce latency:
API pushes messages into an async queue, a single background worker
consumes and produces to Kafka sequentially. If the queue is full,
messages are dropped (graceful degradation) instead of blocking the event loop.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from src.core.infra.kafka import KafkaProducerService

logger = logging.getLogger(__name__)


@dataclass
class KafkaMessage:
    topic: str
    message: dict
    key: Optional[str] = None


class KafkaQueue:
    def __init__(self, producer: KafkaProducerService, maxsize: int = 5000):
        self._producer = producer
        self._queue: asyncio.Queue[KafkaMessage] = asyncio.Queue(maxsize=maxsize)
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Kafka queue worker started")

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("Kafka queue worker stopped")

    def put_nowait(self, msg: KafkaMessage):
        try:
            self._queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("Kafka queue full, dropping message")

    async def _worker_loop(self):
        while True:
            msg = await self._queue.get()
            task = asyncio.create_task(
                self._producer.send_buffered(msg.topic, msg.message, key=msg.key)
            )
            task.add_done_callback(
                lambda t: (
                    self._queue.task_done()
                    or (
                        t.exception()
                        and logger.error("Kafka send error: %s", t.exception())
                    )
                )
            )
