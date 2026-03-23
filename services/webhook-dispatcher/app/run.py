import asyncio

import sentry_sdk
import structlog
from aiokafka import AIOKafkaConsumer

from .consumer import run_consumer_loop
from .core.config import CONSUME_TOPICS, settings
from .core.logging import setup_logging
from .infrastructure.http_client import create_http_client
from .infrastructure.messaging.producer import close_producer, create_producer

logger = structlog.get_logger()


def _setup_sentry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", settings.service_name)
    sentry_sdk.set_tag("worker", "webhook-dispatcher")


async def _async_main() -> None:
    setup_logging(settings.log_level, settings.service_name)
    _setup_sentry()

    producer = await create_producer()
    http_client = create_http_client()

    consumer = AIOKafkaConsumer(
        *CONSUME_TOPICS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.consumer_group,
        auto_offset_reset="earliest",
    )
    await consumer.start()

    logger.info(
        "webhook_dispatcher_started",
        topics=CONSUME_TOPICS,
        group_id=settings.consumer_group,
        webhook_url=settings.webhook_url,
    )

    try:
        await run_consumer_loop(consumer, producer, http_client)
    finally:
        await consumer.stop()
        await close_producer(producer)
        await http_client.aclose()
        logger.info("webhook_dispatcher_stopped")


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
