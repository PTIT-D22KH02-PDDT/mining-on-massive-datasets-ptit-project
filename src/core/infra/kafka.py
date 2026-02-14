import json
import logging
import os
from typing import Callable, Any, Optional
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from dotenv import load_dotenv

# Get logger
logger = logging.getLogger(__name__)
load_dotenv()
def _load_kafka_bootstrap_server() -> str:
    kafka_host = os.getenv("KAFKA_HOST_EXTERNAL", "localhost")
    kafka_port = os.getenv("KAFKA_PORT_EXTERNAL", "29092")
    bootstrap_servers = f"{kafka_host}:{kafka_port}"
    return bootstrap_servers
class KafkaProducerService:
    """
    Service for producing messages to Kafka asynchronously.
    """
    def __init__(self):
        self.bootstrap_servers = _load_kafka_bootstrap_server()
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Initializes and starts the Kafka producer."""
        if self.producer is None:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            await self.producer.start()
            logger.info(f"Kafka producer started for servers: {self.bootstrap_servers}")

    async def stop(self):
        """Stops the Kafka producer."""
        if self.producer:
            await self.producer.stop()
            self.producer = None
            logger.info("Kafka producer stopped.")

    async def send(self, topic: str, message: Any):
        """Sends a message to a Kafka topic."""
        if self.producer is None:
            await self.start()
        
        try:
            await self.producer.send_and_wait(topic, message)
            logger.debug(f"Message sent to topic {topic}")
        except Exception as e:
            logger.error(f"Failed to send message to Kafka topic {topic}: {e}")
            raise

class KafkaListenerService:
    """
    Service for listening to Kafka topics asynchronously.
    """
    def __init__(self, topic: str, group_id: str):
        self.bootstrap_servers = _load_kafka_bootstrap_server()
        self.topic = topic
        self.group_id = group_id
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._running = False

    async def start(self):
        """Initializes and starts the Kafka consumer."""
        if self.consumer is None:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='earliest'
            )
            await self.consumer.start()
            self._running = True
            logger.info(f"Kafka listener started for topic: {self.topic} (group: {self.group_id})")

    async def stop(self):
        """Stops the Kafka consumer."""
        self._running = False
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
            logger.info("Kafka listener stopped.")

    async def listen(self, callback: Callable[[Any], Any]):
        """
        Starts listening for messages and triggers the callback for each.
        """
        if self.consumer is None:
            await self.start()
        
        try:
            async for msg in self.consumer:
                if not self._running:
                    break
                try:
                    await callback(msg.value)
                except Exception as e:
                    logger.error(f"Error processing Kafka message: {e}")
        finally:
            await self.stop()
