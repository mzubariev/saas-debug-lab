import asyncio
import json

import httpx
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI

from .config import settings
from .webhook import deliver

logger = structlog.get_logger()

_CONSUME_TOPICS = ("task_created", "task_updated")
_GROUP_ID = "integration-service"


async def start_kafka(app: FastAPI) -> None:
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    app.state.kafka_producer = producer

    http_client = httpx.AsyncClient()
    app.state.http_client = http_client

    consumer = AIOKafkaConsumer(
        *_CONSUME_TOPICS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=_GROUP_ID,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    app.state.kafka_consumer = consumer

    app.state.consumer_task = asyncio.create_task(
        _consume_loop(consumer, producer, http_client)
    )

    logger.info("kafka_started", topics=_CONSUME_TOPICS, group_id=_GROUP_ID)


async def stop_kafka(app: FastAPI) -> None:
    app.state.consumer_task.cancel()
    try:
        await app.state.consumer_task
    except asyncio.CancelledError:
        pass

    await app.state.kafka_consumer.stop()
    await app.state.kafka_producer.stop()
    await app.state.http_client.aclose()

    logger.info("kafka_stopped")


async def _consume_loop(
    consumer: AIOKafkaConsumer,
    producer: AIOKafkaProducer,
    http_client: httpx.AsyncClient,
) -> None:
    async for msg in consumer:
        try:
            event = json.loads(msg.value.decode("utf-8"))
            logger.info(
                "event_received",
                topic=msg.topic,
                task_id=event.get("id"),
                status=event.get("status"),
            )
            await deliver(http_client, producer, event)
        except Exception as exc:
            logger.error(
                "event_processing_failed",
                topic=msg.topic,
                offset=msg.offset,
                error=str(exc),
            )
