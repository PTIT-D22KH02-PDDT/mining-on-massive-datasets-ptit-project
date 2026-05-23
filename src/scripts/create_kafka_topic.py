import asyncio
import os

from aiokafka.admin import AIOKafkaAdminClient, NewTopic


async def create_topic():
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
    topic_name = "user-events"

    print(f"Connecting to Kafka at {bootstrap_servers} using aiokafka...")
    admin_client = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)

    await admin_client.start()
    try:
        # Check if topic exists
        existing_topics = await admin_client.list_topics()
        if topic_name in existing_topics:
            print(f"Topic '{topic_name}' already exists.")
        else:
            new_topic = NewTopic(
                name=topic_name, num_partitions=1, replication_factor=1
            )
            await admin_client.create_topics(new_topics=[new_topic])
            print(f"Successfully created topic: {topic_name}")
    except Exception as e:
        print(f"Failed to create topic: {e}")
    finally:
        await admin_client.close()


if __name__ == "__main__":
    asyncio.run(create_topic())
