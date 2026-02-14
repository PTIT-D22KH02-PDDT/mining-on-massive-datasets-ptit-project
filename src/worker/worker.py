"""
Worker framework - Reference-based Implementation.
Supports multiple consumers per topic, batch processing with getmany(),
and a decorator-based registration system.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from aiokafka import AIOKafkaConsumer
from src.core.infra.kafka import KafkaProducerService, ensure_topics, _bootstrap_servers
from src.core.config import cfg

logger = logging.getLogger(__name__)

class Topic:
    """Represents a Kafka topic configuration."""
    def __init__(self, name: str, consumer_count: int = 1, batch_size: int = 1):
        self.name = name
        self.consumer_count = consumer_count
        self.batch_size = batch_size

    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        return isinstance(other, Topic) and self.name == other.name

class Worker:
    """
    Main Worker class similar to Oxalis.
    Orchestrates multiple consumers and a single producer.
    """
    def __init__(self):
        self.bootstrap_servers = _bootstrap_servers()
        self.group_id = cfg["kafka"]["consumer"].get("group_id", "worker-group")
        
        self.producer = KafkaProducerService()
        self.consumers: List[AIOKafkaConsumer] = []
        
        # Maps topic_name -> callback function
        self.handlers: Dict[str, Callable] = {}
        # Set of Topic objects to listen to
        self.topics: Set[Topic] = set()
        
        self._running = False
        self._tasks: List[asyncio.Task] = []

    def register(self, topic_key: str):
        """
        Decorator to register a handler for a topic defined in config.yml.
        Usage:
            @worker.register("recommender_updates")
            async def handle(msg): ...
        """
        topic_config = cfg["kafka"]["topics"][topic_key]
        topic = Topic(
            name=topic_config["name"],
            consumer_count=topic_config.get("consumer_count", 1),
            batch_size=topic_config.get("batch_size", 1)
        )
        
        def decorator(func: Callable):
            self.handlers[topic.name] = func
            self.topics.add(topic)
            return func
        return decorator

    async def start(self):
        """Initializes infrastructure and starts all consumer loops."""
        if self._running:
            return

        # 1. Ensure topics exist and wait if new
        await ensure_topics()


        # 2. Start Producer
        await self.producer.start()
        
        self._running = True
        
        # 3. Start Consumer loops (multiple per topic as configured)
        for topic in self.topics:
            for i in range(topic.consumer_count):
                task = asyncio.create_task(self._start_consumer(topic, i))
                self._tasks.append(task)
        
        logger.info(f"Worker fully started with {len(self._tasks)} consumer loops.")

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        logger.info("Stopping worker...")
        
        # Stop all consumer tasks
        for task in self._tasks:
            task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Stop AIOfka objects
        for consumer in self.consumers:
            await consumer.stop()
        
        await self.producer.stop()
        logger.info("Worker stopped.")

    async def send(self, topic_name: str, message: Any, key: str | None = None):
        """Alias for producer.send."""
        return await self.producer.send(topic_name, message, key=key)

    async def _start_consumer(self, topic: Topic, index: int):
        """Individual consumer loop using getmany()."""
        # CRITICAL: Group ID must be unique per topic if consumers only subscribe to one topic
        topic_group_id = f"{self.group_id}-{topic.name}"
        
        consumer = AIOKafkaConsumer(
            topic.name,
            bootstrap_servers=self.bootstrap_servers,
            group_id=topic_group_id,
            # We will handle decoding manually to prevent crashes on bad messages
            auto_offset_reset="earliest",
            enable_auto_commit=True
        )
        self.consumers.append(consumer)
        
        logger.info(f"Starting consumer {index} for topic: {topic.name}")
        
        # Silence aiokafka logs during startup chatter
        aio_logger = logging.getLogger("aiokafka")
        aio_logger.setLevel(logging.CRITICAL)

        try:
            # Add a small jittered delay to prevent race conditions during group join
            await asyncio.sleep(index * 0.5)
            
            await consumer.start()
            logger.info(f"Consumer {index} started, subscribing to: {topic.name}")
            
            # Wait for rebalancing/assignment to complete
            await asyncio.sleep(3.0)
            
            # Restore logging level and show assignment
            aio_logger.setLevel(logging.INFO)
            assignment = consumer.assignment()
            if not assignment:
                logger.warning(f"Consumer {index} for {topic.name} has NO partitions assigned yet. Rebalancing may be slow.")
            else:
                logger.info(f"Consumer {index} for {topic.name} assigned to: {assignment}")
            
            while self._running:
                # Use getmany to match batch_size from config
                data = await consumer.getmany(
                    timeout_ms=2000, 
                    max_records=topic.batch_size
                )
                
                if not data:
                    continue
                
                for tp, messages in data.items():
                    callback = self.handlers.get(tp.topic)
                    if not callback:
                        continue
                        
                    for msg in messages:
                        try:
                            # 1. Decode bytes to JSON
                            if msg.value is None:
                                continue
                            
                            payload = json.loads(msg.value.decode("utf-8"))
                            
                            # 2. Support both sync and async callbacks
                            res = callback(payload)
                            if asyncio.iscoroutine(res):
                                await res
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipping malformed JSON on {tp.topic}: {e} (Raw: {msg.value})")
                        except Exception as e:
                            logger.error(f"Error in handler for {tp.topic}: {e}", exc_info=True)
                            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Consumer {index} for {topic.name} failed: {e}")
        finally:
            await consumer.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()
