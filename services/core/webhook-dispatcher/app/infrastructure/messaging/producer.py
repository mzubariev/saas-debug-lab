from aiokafka import AIOKafkaProducer

from ...core.config import settings


async def create_producer() -> AIOKafkaProducer:
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    return producer


async def close_producer(producer: AIOKafkaProducer) -> None:
    await producer.stop()
