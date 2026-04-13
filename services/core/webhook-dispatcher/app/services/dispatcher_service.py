import asyncio
import json
import random
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from aiokafka import AIOKafkaProducer
from saas_shared.kafka_envelope import encode_envelope_bytes, parse_envelope_message
from saas_shared.kafka_messaging import kafka_consume_span, kafka_publish_span
from saas_shared.kafka_trace import current_trace_id_for_kafka_envelope, otel_kafka_headers
from saas_shared.prometheus_metrics import (
    dlq_messages_total,
    kafka_messages_consumed_total,
    kafka_processing_errors_total,
    otel_trace_id,
    webhook_delivery_duration_seconds,
    webhook_in_progress,
    webhook_requests_total,
    webhook_retries_total,
)

from ..core.config import settings

logger = structlog.get_logger()

_TOPIC_EVENT_TYPE: dict[str, str] = {
    "webhook_sent": "webhook.sent",
    "webhook_failed": "webhook.failed",
    "webhook_dlq": "webhook.dlq",
}

_BACKOFF_BASE = 1.0  # seconds
_TARGET = settings.webhook_url  # constant label value — set once at import time


def _webhook_reason(exc: httpx.RequestError) -> str:
    """Classify a failed httpx request into a controlled low-cardinality reason label.

    ``TimeoutException`` is a subclass of ``RequestError``, so it must be checked first.
    """
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return "network"


async def deliver(
    client: httpx.AsyncClient,
    producer: AIOKafkaProducer,
    payload: dict,
) -> None:
    """Deliver payload to WEBHOOK_URL with exponential backoff + jitter.

    Retry policy:
    - ``httpx.RequestError`` (network / timeout) → retry up to MAX_RETRIES.
    - HTTP 5xx → retry up to MAX_RETRIES.
    - HTTP 4xx → fail immediately; retrying a client error is pointless.

    Every attempt sends an ``Idempotency-Key`` header so the receiver can
    deduplicate safe retries without side-effects.

    On permanent failure the DLQ payload includes ``error``, ``attempts``,
    and ``timestamp`` for forensic analysis.
    """
    last_error: str = ""
    attempts_made: int = 0
    # Capture once — the Kafka consumer span is active at function entry.
    tid = otel_trace_id()
    _exemplar = {"trace_id": tid} if tid else None

    webhook_in_progress.inc()
    try:
        for attempt in range(1, settings.max_retries + 1):
            attempts_made = attempt
            if attempt > 1:
                webhook_retries_total.inc()

            t0 = time.perf_counter()
            try:
                resp = await client.post(
                    settings.webhook_url,
                    json=payload,
                    headers={"Idempotency-Key": str(payload.get("id", ""))},
                    timeout=settings.webhook_timeout,
                )
                resp.raise_for_status()

                elapsed = time.perf_counter() - t0
                _obs = webhook_delivery_duration_seconds.labels(status="success")
                _obs.observe(elapsed, _exemplar) if _exemplar else _obs.observe(elapsed)
                webhook_requests_total.labels(
                    status="success", reason="", target=_TARGET
                ).inc()

                logger.info(
                    "webhook_sent",
                    task_id=payload.get("id"),
                    status_code=resp.status_code,
                    attempt=attempt,
                )
                await _produce(producer, "webhook_sent", payload)
                return

            except httpx.HTTPStatusError as exc:
                elapsed = time.perf_counter() - t0
                last_error = str(exc)
                status = exc.response.status_code

                if 400 <= status < 500:
                    reason = "4xx"
                    _obs = webhook_delivery_duration_seconds.labels(status="4xx")
                    _obs.observe(elapsed, _exemplar) if _exemplar else _obs.observe(elapsed)
                    webhook_requests_total.labels(
                        status="fail", reason=reason, target=_TARGET
                    ).inc()
                    logger.warning(
                        "webhook_attempt_failed",
                        task_id=payload.get("id"),
                        attempt=attempt,
                        status_code=status,
                        error=last_error,
                        retry=False,
                    )
                    break  # client error — retrying won't help, go straight to DLQ

                reason = "5xx"
                _obs = webhook_delivery_duration_seconds.labels(status="5xx")
                _obs.observe(elapsed, _exemplar) if _exemplar else _obs.observe(elapsed)
                webhook_requests_total.labels(
                    status="fail", reason=reason, target=_TARGET
                ).inc()
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
                elapsed = time.perf_counter() - t0
                last_error = str(exc)
                reason = _webhook_reason(exc)  # "timeout" or "network"
                _obs = webhook_delivery_duration_seconds.labels(status=reason)
                _obs.observe(elapsed, _exemplar) if _exemplar else _obs.observe(elapsed)
                webhook_requests_total.labels(
                    status="fail", reason=reason, target=_TARGET
                ).inc()
                logger.warning(
                    "webhook_attempt_failed",
                    task_id=payload.get("id"),
                    attempt=attempt,
                    max_retries=settings.max_retries,
                    reason=reason,
                    error=last_error,
                )
                if attempt < settings.max_retries:
                    backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
                    jitter = random.uniform(0, backoff * 0.1)
                    await asyncio.sleep(backoff + jitter)
    finally:
        webhook_in_progress.dec()

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
    dlq_messages_total.inc()
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
        kafka_processing_errors_total.labels(topic=msg.topic).inc()
        logger.error(
            "event_processing_failed",
            topic=msg.topic,
            offset=msg.offset,
            error=str(exc),
        )
