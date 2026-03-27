"""Prometheus metrics (``METRICS_PORT``, default 9100)."""

from prometheus_client import Counter

emails_sent_total = Counter(
    "emails_sent_total",
    "SMTP notifications delivered successfully.",
)

emails_failed_total = Counter(
    "emails_failed_total",
    "SMTP notification delivery failures.",
)

kafka_messages_consumed_total = Counter(
    "kafka_messages_consumed_total",
    "Kafka records processed by this consumer.",
    ["topic"],
)
