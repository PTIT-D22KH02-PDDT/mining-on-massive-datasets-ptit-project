import json
import asyncio
import random
from aiokafka import AIOKafkaProducer
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class SessionProducer:
    """Kafka producer that sends session events to user-events topic."""

    def __init__(self, bootstrap_servers: str, topic: str = "user-events"):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer = None

    async def start(self):
        """Start the Kafka producer."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self.producer.start()

    async def stop(self):
        """Stop the Kafka producer."""
        if self.producer:
            await self.producer.stop()

    async def send_session(self, session_data: Dict[str, Any]):
        """Send all events of a session to Kafka."""
        session_id = session_data["session"]
        events = session_data["events"]

        for event in events:
            message = {
                "session": session_id,
                "aid": event["aid"],
                "ts": event["ts"],
                "type": event["type"],
            }
            await self.producer.send(self.topic, message)

    async def send_session_replay(self, session_data: Dict[str, Any], speed_multiplier: float = 1.0):
        """Replay a session with timing preserved (adjusted by speed)."""
        events = sorted(session_data["events"], key=lambda x: x["ts"])

        if not events:
            return

        base_time = datetime.now()
        first_ts = events[0]["ts"]

        for event in events:
            original_delay = (event["ts"] - first_ts) / 1000 / speed_multiplier
            await asyncio.sleep(max(0, original_delay))

            message = {
                "session": session_data["session"],
                "aid": event["aid"],
                "ts": int((base_time + timedelta(seconds=original_delay)).timestamp() * 1000),
                "type": event["type"],
            }
            await self.producer.send(self.topic, message)
