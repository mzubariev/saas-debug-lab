import asyncio
import json

import structlog
from aiokafka import AIOKafkaConsumer

from .config import settings
from .logging import setup_logging


logger = structlog.get_logger()

TOPIC = "task_created"
GROUP_ID = "notification-worker"


async def handle_event(event: dict) -> None:

    logger.info(
        "notification_sent",
        task_id=event.get("id"),
        title=event.get("title"),
    )


async def consume() -> None:

    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",
    )

    await consumer.start()

    logger.info("consumer_started", topic=TOPIC, group_id=GROUP_ID)

    try:
        async for msg in consumer:
            try:
                event = json.loads(msg.value.decode("utf-8"))
                await handle_event(event)
            except Exception as exc:
                logger.error(
                    "event_processing_failed",
                    error=str(exc),
                    topic=msg.topic,
                    offset=msg.offset,
                )
    finally:
        await consumer.stop()


def run() -> None:
    setup_logging(settings.log_level, settings.service_name)
    asyncio.run(consume())


if __name__ == "__main__":
    run()
