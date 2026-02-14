import asyncio
from src.core import KafkaProducerService

async def send_model_update():
    producer = KafkaProducerService()
    try:
        await producer.send("user-events", {"status": "trained", "model_id": "123"})
    finally:
        await producer.stop()

if __name__ == "__main__":
    asyncio.run(send_model_update())