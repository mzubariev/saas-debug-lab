import asyncio

import structlog
from aiokafka import AIOKafkaConsumer
from prometheus_client import start_http_server
from saas_shared.sentry_setup import setup_sentry_worker
from saas_shared.telemetry import setup_worker_telemetry

from .consumer import run_consumer_loop
from .core.config import CONSUME_TOPICS, settings
from .core.logging import setup_logging
from .infrastructure.http_client import create_http_client
from .infrastructure.messaging.producer import close_producer, create_producer


logger = structlog.get_logger()


async def _async_main() -> None:
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
    setup_logging(service_name=settings.service_name, log_level=settings.log_level)
    setup_worker_telemetry(
        settings.service_name,
        settings.otlp_endpoint,
    )
    setup_sentry_worker(
        service_name=settings.service_name,
        dsn=settings.sentry_dsn,
        worker_name="webhook-dispatcher",
    )
    start_http_server(settings.metrics_port)
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
