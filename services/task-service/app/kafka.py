import json
from typing import Optional

import sentry_sdk
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI

from .config import settings


async def start_kafka(app: FastAPI) -> None:

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )

    await producer.start()

    app.state.kafka = producer


async def stop_kafka(app: FastAPI) -> None:

    await app.state.kafka.stop()


def _sentry_kafka_headers() -> list[tuple[str, bytes]]:
    """Return Kafka message headers carrying the current Sentry trace context.

    These headers mirror the HTTP ``sentry-trace`` / ``baggage`` headers so
    that consumers can call ``sentry_sdk.continue_trace()`` and link their
    transaction to the originating browser request — completing the full
    Browser → Gateway → Service → Worker trace chain.
    """
    headers: list[tuple[str, bytes]] = []

    traceparent: Optional[str] = sentry_sdk.get_traceparent()
    baggage: Optional[str] = sentry_sdk.get_baggage()

    if traceparent:
        headers.append(("sentry-trace", traceparent.encode("utf-8")))
    if baggage:
        headers.append(("baggage", baggage.encode("utf-8")))

    return headers


async def publish_event(producer: AIOKafkaProducer, topic: str, payload: dict) -> None:

    value = json.dumps(payload).encode("utf-8")

    await producer.send_and_wait(topic, value, headers=_sentry_kafka_headers())