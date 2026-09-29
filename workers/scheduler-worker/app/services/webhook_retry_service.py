import time

import sentry_sdk
import structlog
from kafka.errors import KafkaTimeoutError
from saas_shared.kafka_envelope import parse_envelope_message
from saas_shared.kafka_messaging import kafka_consume_span

from saas_shared.prometheus_metrics import dlq_processed_total, kafka_messages_consumed_total

from ..core.config import settings
from ..infrastructure.kafka.consumer import create_webhook_dlq_consumer

logger = structlog.get_logger()

# Consumed per Beat tick (dispatch is fast; stay well within the 60 s window).
_MAX_MESSAGES = 200
# Hard wall-clock cap so the Beat task always returns before the next tick.
_MAX_RUNTIME_SECONDS = 20


def process_dlq() -> dict:
    """Read up to _MAX_MESSAGES from the webhook DLQ and dispatch one
    ``retry_single_webhook`` Celery task per message (fan-out).

    This function is the *producer* side — it commits Kafka offsets and enqueues
    Celery tasks.  Actual HTTP delivery, retries, and back-off happen inside each
    ``retry_single_webhook`` task running in a worker sub-process.

    By keeping this function fast (no HTTP calls), it can safely consume up to
    _MAX_MESSAGES messages per 60 s Beat tick without blocking the Beat scheduler.

    Incident simulation:
    - Stop external-service-simulator → retry_single_webhook tasks raise
      httpx.RequestError, fill the Celery queue, celery_queue_size rises.
    - Reduce worker --concurrency → queue depth grows faster than it drains.
    - Set _MAX_MESSAGES low → DLQ lag grows even when workers are idle.
    """
    t0 = time.perf_counter()
    logger.info("webhook_dlq_fanout_started")

    try:
        consumer = create_webhook_dlq_consumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
        )
    except KafkaTimeoutError as exc:
        duration = time.perf_counter() - t0
        logger.error(
            "dlq_consumer_unavailable",
            error=str(exc),
            duration_seconds=round(duration, 3),
        )
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("task", "retry_failed_webhooks")
            scope.set_tag("error_type", "kafka_unavailable")
            scope.set_extra("kafka_servers", settings.kafka_bootstrap_servers)
            sentry_sdk.capture_exception(exc)
        return {"dispatched": 0, "error": str(exc)}

    # Lazy import breaks the circular dependency:
    #   webhook_tasks → webhook_retry_service (this module)
    #   webhook_retry_service → webhook_tasks  ← only needed at call time
    from app.tasks.webhook_tasks import retry_single_webhook  # noqa: PLC0415

    dispatched = 0

    try:
        for msg in consumer:
            if dispatched >= _MAX_MESSAGES:
                break
            if time.perf_counter() - t0 > _MAX_RUNTIME_SECONDS:
                logger.warning(
                    "dlq_fanout_runtime_cap_reached",
                    dispatched=dispatched,
                    elapsed_seconds=round(time.perf_counter() - t0, 2),
                )
                break

            kafka_messages_consumed_total.labels(topic=msg.topic).inc()
            dlq_processed_total.inc()

            _event_type, payload, envelope_trace_id = parse_envelope_message(msg.value)

            with kafka_consume_span(
                msg.topic,
                msg.partition,
                msg.offset,
                envelope_trace_id,
                getattr(msg, "headers", None),
            ):
                clean_payload = {k: v for k, v in payload.items() if k != "error"}

                retry_single_webhook.delay(
                    payload=clean_payload,
                    event_type=_event_type,
                    task_id=payload.get("id"),
                )

            dispatched += 1

    finally:
        consumer.close()

    duration = time.perf_counter() - t0
    logger.info(
        "webhook_dlq_fanout_finished",
        dispatched=dispatched,
        duration_seconds=round(duration, 3),
    )
    return {"dispatched": dispatched}
