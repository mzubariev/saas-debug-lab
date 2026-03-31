"""Prometheus metrics (exposed on ``METRICS_PORT``, default 9100).

This consumer exposes only ``/metrics`` via ``start_http_server`` (no public HTTP API).
``http_requests_total`` / ``http_request_duration_seconds`` are registered on FastAPI services.
"""

from prometheus_client import Counter

webhook_requests_total = Counter(
    "webhook_requests_total",
    "Successful outbound webhook HTTP deliveries (2xx).",
)

webhook_failures_total = Counter(
    "webhook_failures_total",
    "Webhook deliveries that exhausted retries and were sent to DLQ.",
)

webhook_retries_total = Counter(
    "webhook_retries_total",
    "Retry attempts after an initial failed webhook HTTP request.",
)

kafka_messages_consumed_total = Counter(
    "kafka_messages_consumed_total",
    "Kafka records processed by this consumer.",
    ["topic"],
)
