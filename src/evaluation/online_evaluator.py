import json
import asyncio
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class OnlineEvaluator:
    """Real-time evaluation of predictions against actual events."""

    def __init__(
        self,
        bootstrap_servers: str,
        predictions_topic: str = "predictions",
        user_events_topic: str = "user-events",
        results_topic: str = "evaluation-results",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.predictions_topic = predictions_topic
        self.user_events_topic = user_events_topic
        self.results_topic = results_topic

        self.consumer = None
        self.producer = None
        self.prediction_cache = defaultdict(list)
        self.latencies = []

    async def start(self):
        """Start Kafka consumer and producer."""
        self.consumer = AIOKafkaConsumer(
            self.predictions_topic,
            self.user_events_topic,
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            group_id="evaluation-group",
            auto_offset_reset="latest",
        )
        await self.consumer.start()

        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self.producer.start()
        logger.info("Online evaluator started")

    async def stop(self):
        """Stop Kafka consumer and producer."""
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        logger.info("Online evaluator stopped")

    async def run(self):
        """Main loop to process messages and evaluate predictions."""
        try:
            async for msg in self.consumer:
                topic = msg.topic

                if topic == self.predictions_topic:
                    await self._handle_prediction(msg.value)
                elif topic == self.user_events_topic:
                    await self._handle_actual_event(msg.value)

        except Exception as e:
            logger.error(f"Error in online evaluator: {e}")

    async def _handle_prediction(self, data: dict):
        """Cache predictions for later evaluation."""
        session_id = data.get("session")
        predictions = data.get("predictions", [])
        timestamp = data.get("ts", datetime.now().timestamp() * 1000)

        self.prediction_cache[session_id].append({
            "predictions": predictions,
            "ts": timestamp,
        })

    async def _handle_actual_event(self, data: dict):
        """Evaluate predictions when actual event occurs."""
        session_id = data.get("session")
        actual_aid = data.get("aid")
        event_type = data.get("type")
        timestamp = data.get("ts")

        if session_id not in self.prediction_cache:
            return

        cached = self.prediction_cache[session_id]
        if not cached:
            return

        latest_pred = cached[-1]
        predictions = latest_pred["predictions"]

        hit = actual_aid in predictions
        latency = (timestamp - latest_pred["ts"]) / 1000

        result = {
            "session": session_id,
            "actual_aid": actual_aid,
            "event_type": event_type,
            "predictions": predictions[:20],
            "hit": hit,
            "latency_ms": latency,
            "timestamp": datetime.now().isoformat(),
        }

        await self.producer.send(self.results_topic, result)
        logger.info(f"Evaluation: session={session_id}, hit={hit}, latency={latency:.2f}ms")

        self.latencies.append(latency)

    def get_stats(self) -> dict:
        """Get current evaluation statistics."""
        if not self.latencies:
            return {"avg_latency": 0, "count": 0}

        return {
            "avg_latency": sum(self.latencies) / len(self.latencies),
            "min_latency": min(self.latencies),
            "max_latency": max(self.latencies),
            "count": len(self.latencies),
        }
