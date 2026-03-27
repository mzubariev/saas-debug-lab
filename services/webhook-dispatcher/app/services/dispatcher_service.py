import asyncio
import json
from typing import Any

import httpx
import structlog
from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from saas_shared.kafka_envelope import encode_envelope_bytes, parse_envelope_message
from saas_shared.kafka_trace import (
    attach_kafka_message_trace,
    current_trace_id_for_kafka_envelope,
)

from ..core.config import settings

logger = structlog.get_logger()
_tracer = trace.get_tracer(__name__)

_TOPIC_EVENT_TYPE: dict[str, str] = {
    "webhook_sent": "webhook.sent",
    "webhook_failed": "webhook.failed",
    "webhook_dlq": "webhook.dlq",
}

_BACKOFF_BASE = 1.0  # seconds


async def deliver(
    client: httpx.AsyncClient,
    producer: AIOKafkaProducer,
    payload: dict,
) -> None:
    """
    Deliver payload to WEBHOOK_URL (webhook-simulator or any real endpoint).

    Retries up to MAX_RETRIES times with exponential backoff.
    On permanent failure, publishes the payload to the webhook_dlq Kafka topic.
    """
    last_error: str = ""

    for attempt in range(1, settings.max_retries + 1):
        try:
            resp = await client.post(
                settings.webhook_url,
                json=payload,
                timeout=settings.webhook_timeout,
            )
            resp.raise_for_status()

            logger.info(
                "webhook_sent",
                task_id=payload.get("id"),
                status_code=resp.status_code,
                attempt=attempt,
            )
            await _produce(producer, "webhook_sent", payload)
            return

        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_error = str(exc)
            logger.warning(
                "webhook_attempt_failed",
                task_id=payload.get("id"),
                attempt=attempt,
                max_retries=settings.max_retries,
                error=last_error,
            )

            if attempt < settings.max_retries:
                backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

    logger.error(
        "webhook_failed_permanently",
        task_id=payload.get("id"),
        error=last_error,
    )
    await _produce(producer, "webhook_failed", {**payload, "error": last_error})
    await _produce(producer, "webhook_dlq", {**payload, "error": last_error})


async def _produce(producer: AIOKafkaProducer, topic: str, payload: dict) -> None:
    try:
        event_type = _TOPIC_EVENT_TYPE.get(topic, topic.replace("_", "."))
        value = encode_envelope_bytes(
            event_type,
            payload,
            trace_id=current_trace_id_for_kafka_envelope(),
        )
        await producer.send_and_wait(topic, value)
    except Exception as exc:
        logger.error("kafka_produce_failed", topic=topic, error=str(exc))


async def process_consumed_message(
    msg: Any,
    http_client: httpx.AsyncClient,
    producer: AIOKafkaProducer,
) -> None:
    """Decode one Kafka record, log, deliver (retry/DLQ inside deliver)."""
    try:
        raw = json.loads(msg.value.decode("utf-8"))
        event_type, event, envelope_trace_id = parse_envelope_message(raw)
        with attach_kafka_message_trace(envelope_trace_id):
            with _tracer.start_as_current_span(
                "kafka.consume",
                attributes={
                    "messaging.system": "kafka",
                    "messaging.destination.name": msg.topic,
                    "messaging.kafka.partition": msg.partition,
                    "messaging.kafka.offset": msg.offset,
                },
            ):
                logger.info(
                    "event_received",
                    topic=msg.topic,
                    event_type=event_type,
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
