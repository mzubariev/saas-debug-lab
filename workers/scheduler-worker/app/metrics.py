"""Prometheus metrics (``METRICS_PORT``, default 9100)."""

from prometheus_client import Counter

celery_tasks_total = Counter(
    "celery_tasks_total",
    "Celery tasks completed successfully.",
    ["task_name"],
)

celery_failures_total = Counter(
    "celery_failures_total",
    "Celery task failures.",
    ["task_name"],
)

dlq_processed_total = Counter(
    "dlq_processed_total",
    "Messages read from the webhook DLQ topic (each retry attempt).",
)

kafka_messages_consumed_total = Counter(
    "kafka_messages_consumed_total",
    "Kafka records processed by this consumer.",
    ["topic"],
)
