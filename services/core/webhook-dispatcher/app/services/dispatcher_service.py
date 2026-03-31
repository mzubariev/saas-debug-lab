import asyncio
import json
import random
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from aiokafka import AIOKafkaProducer
from saas_shared.kafka_envelope import encode_envelope_bytes, parse_envelope_message
from saas_shared.kafka_messaging import kafka_consume_span, kafka_publish_span
from saas_shared.kafka_trace import current_trace_id_for_kafka_envelope, otel_kafka_headers

from ..core.config import settings
from ..metrics import (
    kafka_messages_consumed_total,
    webhook_failures_total,
    webhook_requests_total,
    webhook_retries_total,
)

logger = structlog.get_logger()

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
    """Deliver payload to WEBHOOK_URL with exponential backoff + jitter.

    Retry policy:
    - ``httpx.RequestError`` (network failure) → retry up to MAX_RETRIES.
    - HTTP 5xx → retry up to MAX_RETRIES.
    - HTTP 4xx → fail immediately; retrying a client error is pointless.

    Every attempt sends an ``Idempotency-Key`` header so the receiver can
    deduplicate safe retries without side-effects.

    On permanent failure the full DLQ payload includes ``error``, ``attempts``,
    and ``timestamp`` for forensic analysis.
    """
    last_error: str = ""
    attempts_made: int = 0

    for attempt in range(1, settings.max_retries + 1):
        attempts_made = attempt
        if attempt > 1:
            webhook_retries_total.inc()
        try:
            resp = await client.post(
                settings.webhook_url,
                json=payload,
                headers={"Idempotency-Key": str(payload.get("id", ""))},
                timeout=settings.webhook_timeout,
            )
            resp.raise_for_status()

            logger.info(
                "webhook_sent",
                task_id=payload.get("id"),
                status_code=resp.status_code,
                attempt=attempt,
            )
            webhook_requests_total.inc()
            await _produce(producer, "webhook_sent", payload)
            return

        except httpx.HTTPStatusError as exc:
            last_error = str(exc)
            status = exc.response.status_code

            if 400 <= status < 500:
                logger.warning(
                    "webhook_attempt_failed",
                    task_id=payload.get("id"),
                    attempt=attempt,
                    status_code=status,
                    error=last_error,
                    retry=False,
                )
                break  # client error — retrying won't help, go straight to DLQ

            logger.warning(
                "webhook_attempt_failed",
                task_id=payload.get("id"),
                attempt=attempt,
                max_retries=settings.max_retries,
                status_code=status,
                error=last_error,
            )
            if attempt < settings.max_retries:
                backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
                jitter = random.uniform(0, backoff * 0.1)
                await asyncio.sleep(backoff + jitter)

        except httpx.RequestError as exc:
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
                jitter = random.uniform(0, backoff * 0.1)
                await asyncio.sleep(backoff + jitter)

    dlq_payload = {
        **payload,
        "error": last_error,
        "attempts": attempts_made,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.error(
        "webhook_failed_permanently",
        task_id=payload.get("id"),
        webhook_url=settings.webhook_url,
        total_attempts=attempts_made,
        error=last_error,
    )
    webhook_failures_total.inc()
    await _produce(producer, "webhook_failed", dlq_payload)
    await _produce(producer, "webhook_dlq", dlq_payload)


async def _produce(producer: AIOKafkaProducer, topic: str, payload: dict) -> None:
    try:
        async with kafka_publish_span(topic):
            event_type = _TOPIC_EVENT_TYPE.get(topic, topic.replace("_", "."))
            value = encode_envelope_bytes(
                event_type,
                payload,
                trace_id=current_trace_id_for_kafka_envelope(),
            )
            await producer.send_and_wait(topic, value, headers=otel_kafka_headers())
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
        kafka_messages_consumed_total.labels(topic=msg.topic).inc()
        event_type, event, envelope_trace_id = parse_envelope_message(raw)
        with kafka_consume_span(
            msg.topic,
            msg.partition,
            msg.offset,
            envelope_trace_id,
            msg.headers,
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
            error=str(exc)
        )
