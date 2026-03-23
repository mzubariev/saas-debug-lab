import json

from kafka import KafkaConsumer

WEBHOOK_DLQ_TOPIC = "webhook_dlq"
DEFAULT_DLQ_GROUP_ID = "scheduler-worker"


def create_webhook_dlq_consumer(
    *,
    bootstrap_servers: str,
    group_id: str = DEFAULT_DLQ_GROUP_ID,
    consumer_timeout_ms: int = 5000,
) -> KafkaConsumer:
    """Short-lived consumer for draining ``webhook_dlq`` with a bounded wait."""
    return KafkaConsumer(
        WEBHOOK_DLQ_TOPIC,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        auto_offset_reset="earliest",
        consumer_timeout_ms=consumer_timeout_ms,
        enable_auto_commit=True,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
    )
