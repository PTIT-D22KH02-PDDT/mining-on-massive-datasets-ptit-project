"""
Worker main entry point.
Uses the decorator-based registration system.
"""

import asyncio
import logging
from src.core import cfg
from src.worker.worker import Worker

# Setup Logging
logging.basicConfig(
    level=cfg.get("app", {}).get("log_level", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Worker
worker = Worker()

@worker.register("recommender_updates")
async def handle_recommendations(msg):
    """Callback for recommender-updates topic."""
    logger.info(f"[recommender-updates] Received: {msg}")

@worker.register("user_events")
async def handle_user_events(msg):
    """Callback for user-events topic."""
    logger.info(f"[user-events] Received: {msg}")

async def main():
    # Start the worker (this handles topics, producers, and all consumers)
    async with worker:
        # Keep the main thread alive while workers run in background
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service shutdown by user.")