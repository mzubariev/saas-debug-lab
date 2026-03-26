from typing import Optional

import sentry_sdk
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from saas_shared.kafka_envelope import encode_envelope_bytes
from saas_shared.kafka_trace import current_trace_id_for_kafka_envelope

from ...core.config import settings

_TOPIC_EVENT_TYPE: dict[str, str] = {
    "task_created": "task.created",
    "task_updated": "task.updated",
}


async def start_kafka(app: FastAPI) -> None:
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    app.state.kafka = producer


async def stop_kafka(app: FastAPI) -> None:
    await app.state.kafka.stop()


def _sentry_kafka_headers() -> list[tuple[str, bytes]]:
    """Return Kafka message headers carrying the current Sentry trace context.

    These headers mirror the HTTP ``sentry-trace`` / ``baggage`` headers so
    that consumers can call ``sentry_sdk.continue_trace()`` and link their
    transaction to the originating browser request.
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
    event_type = _TOPIC_EVENT_TYPE.get(topic, topic.replace("_", "."))
    value = encode_envelope_bytes(
        event_type,
        payload,
        trace_id=current_trace_id_for_kafka_envelope(),
    )
    await producer.send_and_wait(topic, value, headers=_sentry_kafka_headers())
