import asyncio
from src.core import KafkaListenerService

async def process_message(msg):
    print(f"Received update message: {msg}")
    # Add logic here to update the model based on the message

async def main():
    # Setup Kafka listener
    listener = KafkaListenerService(
        bootstrap_servers="localhost:9092",
        topic="recommender-updates",
        group_id="recommender-group"
    )
    
    print("Starting Kafka listener service...")
    await listener.listen(process_message)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Service stopped by user")