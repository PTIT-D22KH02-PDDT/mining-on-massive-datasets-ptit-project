from src.core import KafkaProducerService
async def send_model_update():
    producer = KafkaProducerService(bootstrap_servers="localhost:9092")
    await producer.send("my-topic", {"status": "trained", "model_id": "123"})
    await producer.stop()