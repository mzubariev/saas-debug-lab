import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .services.dispatcher_service import process_consumed_message


async def run_consumer_loop(
    consumer: AIOKafkaConsumer,
    producer: AIOKafkaProducer,
    http_client: httpx.AsyncClient,
) -> None:
    async for msg in consumer:
        await process_consumed_message(msg, http_client, producer)
