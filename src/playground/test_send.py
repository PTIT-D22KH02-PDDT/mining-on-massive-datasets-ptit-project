"""
Script to send test messages to BOTH topics for verification.
"""

import asyncio
import logging
from src.core.infra.kafka import KafkaProducerService
from src.core.config import cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def run_test():
    producer = KafkaProducerService()
    await producer.start()
    
    # Send to Recommender Updates
    rec_topic = cfg["kafka"]["topics"]["recommender_updates"]["name"]
    rec_msg = {"type": "recommendation", "data": "New model available"}
    logger.info(f"Sending to {rec_topic}...")
    await producer.send(rec_topic, rec_msg)
    await asyncio.sleep(1.0)
    
    # Send to User Events
    user_topic = cfg["kafka"]["topics"]["user_events"]["name"]
    user_msg = {"type": "event", "user": "user_123", "action": "click"}
    logger.info(f"Sending to {user_topic}...")
    await producer.send(user_topic, user_msg)
    
    logger.info("All test messages sent successfully!")
    await producer.stop()

if __name__ == "__main__":
    asyncio.run(run_test())
