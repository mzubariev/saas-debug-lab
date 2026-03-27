import time

import httpx
import sentry_sdk
import structlog
from kafka.errors import NoBrokersAvailable
from opentelemetry import trace
from saas_shared.kafka_envelope import parse_envelope_message
from saas_shared.kafka_trace import attach_kafka_message_trace

from ..core.config import settings
from ..infrastructure.http.client import post_json_sync
from ..infrastructure.kafka.consumer import create_webhook_dlq_consumer

logger = structlog.get_logger()


def process_dlq() -> dict:
    """
    Drain all currently available messages from the webhook_dlq Kafka topic
    and re-attempt delivery to WEBHOOK_URL.

    Uses a short-lived consumer with a 5-second drain timeout so the job
    always terminates within a predictable window. Messages are committed
    regardless of retry outcome — the DLQ is a best-effort second chance,
    not an infinite retry loop. Persistent failures are logged as warnings
    and visible in Flower / Kibana.
    """
    t0 = time.perf_counter()
    logger.info("webhook_dlq_retry_job_started")

    try:
        consumer = create_webhook_dlq_consumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
        )
    except NoBrokersAvailable as exc:
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
        logger.info(
            "webhook_dlq_retry_job_finished",
            retried=0,
            failed=0,
            messages_processed=0,
            duration_seconds=round(duration, 3),
            error=str(exc),
        )
        return {"retried": 0, "failed": 0, "error": str(exc)}

    retried = 0
    failed = 0

    try:
        for msg in consumer:
            _event_type, payload, envelope_trace_id = parse_envelope_message(msg.value)
            with attach_kafka_message_trace(envelope_trace_id):
                with _tracer.start_as_current_span(
                    "kafka.consume",
                    attributes={
                        "messaging.system": "kafka",
                        "messaging.destination.name": msg.topic,
                        "messaging.kafka.offset": msg.offset,
                    },
                ):
                    # Strip the "error" key appended by webhook-dispatcher before retrying.
                    clean_payload = {k: v for k, v in payload.items() if k != "error"}

                    try:
                        resp = post_json_sync(
                            settings.webhook_url,
                            clean_payload,
                            timeout=settings.webhook_timeout,
                        )
                        resp.raise_for_status()

                        logger.info(
                            "dlq_webhook_retried",
                            task_id=payload.get("id"),
                            event_type=_event_type,
                            status_code=resp.status_code,
                            topic_offset=msg.offset,
                        )
                        retried += 1

                    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                        logger.warning(
                            "dlq_webhook_retry_failed",
                            task_id=payload.get("id"),
                            event_type=_event_type,
                            error=str(exc),
                            topic_offset=msg.offset,
                        )
                        sentry_sdk.add_breadcrumb(
                            category="dlq",
                            message="DLQ webhook retry failed",
                            level="warning",
                            data={
                                "task_id": payload.get("id"),
                                "error": str(exc),
                                "topic_offset": msg.offset,
                                "webhook_url": settings.webhook_url,
                            },
                        )
                        failed += 1

    finally:
        consumer.close()

    duration = time.perf_counter() - t0
    processed = retried + failed
    logger.info(
        "webhook_dlq_retry_job_finished",
        retried=retried,
        failed=failed,
        messages_processed=processed,
        duration_seconds=round(duration, 3),
    )
    return {"retried": retried, "failed": failed}
