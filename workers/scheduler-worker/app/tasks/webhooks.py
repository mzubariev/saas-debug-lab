import json

import httpx
import structlog
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from ..celery import celery_app
from ..config import settings


logger = structlog.get_logger()

_DLQ_TOPIC = "webhook_dlq"
_GROUP_ID = "scheduler-worker"


@celery_app.task(name="app.tasks.webhooks.retry_failed_webhooks")
def retry_failed_webhooks() -> dict:
    """
    Drain all currently available messages from the webhook_dlq Kafka topic
    and re-attempt delivery to WEBHOOK_URL.

    Uses a short-lived consumer with a 5-second drain timeout so the task
    always terminates within a predictable window. Messages are committed
    regardless of retry outcome — the DLQ is a best-effort second chance,
    not an infinite retry loop. Persistent failures are logged as warnings
    and visible in Flower / Kibana.
    """
    try:
        consumer = KafkaConsumer(
            _DLQ_TOPIC,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=_GROUP_ID,
            auto_offset_reset="earliest",
            # Stop iterating after 5 s with no new messages so the task
            # finishes deterministically even when the topic is empty.
            consumer_timeout_ms=5000,
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
    except NoBrokersAvailable as exc:
        logger.error("dlq_consumer_unavailable", error=str(exc))
        return {"retried": 0, "failed": 0, "error": str(exc)}

    retried = 0
    failed = 0

    try:
        for msg in consumer:
            payload: dict = msg.value
            # Strip the "error" key appended by integration-service before retrying.
            clean_payload = {k: v for k, v in payload.items() if k != "error"}

            try:
                with httpx.Client(timeout=settings.webhook_timeout) as client:
                    resp = client.post(settings.webhook_url, json=clean_payload)
                    resp.raise_for_status()

                logger.info(
                    "dlq_webhook_retried",
                    task_id=payload.get("id"),
                    status_code=resp.status_code,
                    topic_offset=msg.offset,
                )
                retried += 1

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning(
                    "dlq_webhook_retry_failed",
                    task_id=payload.get("id"),
                    error=str(exc),
                    topic_offset=msg.offset,
                )
                failed += 1

    finally:
        consumer.close()

    logger.info("dlq_retry_cycle_complete", retried=retried, failed=failed)
    return {"retried": retried, "failed": failed}
