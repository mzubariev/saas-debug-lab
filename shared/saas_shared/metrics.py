"""Unified Prometheus metrics for all SaaS Debug Lab services and workers.

Single source of truth — every Counter, Histogram, and Gauge is registered
here exactly once per process.  Services and workers import what they need:

    from saas_shared.metrics import http_requests_total, kafka_consumer_lag

IMPORTANT: never instantiate Prometheus instruments inside functions.
           Always import from this module at call sites.
"""
from prometheus_client import Counter, Gauge, Histogram

# ── HTTP ──────────────────────────────────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests processed.",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently in progress.",
    ["path"],
)

http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response body size in bytes.",
    ["path"],
    buckets=(64, 256, 1_024, 4_096, 16_384, 65_536, 262_144, 1_048_576),
)

# ── Upstream (api-gateway outbound calls) ─────────────────────────────────────

upstream_requests_total = Counter(
    "upstream_requests_total",
    "Requests forwarded to downstream services.",
    ["service", "status"],
)

upstream_request_duration_seconds = Histogram(
    "upstream_request_duration_seconds",
    "Latency of downstream (proxied) HTTP requests in seconds.",
    ["service"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# ── Kafka ─────────────────────────────────────────────────────────────────────

kafka_messages_consumed_total = Counter(
    "kafka_messages_consumed_total",
    "Kafka messages consumed.",
    ["topic"],
)

kafka_processing_duration_seconds = Histogram(
    "kafka_processing_duration_seconds",
    "Time to fully process a single Kafka message (decode + handler).",
    ["topic"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

kafka_consumer_lag = Gauge(
    "kafka_consumer_lag",
    "Estimated Kafka consumer lag (messages behind the latest offset).",
    ["topic", "partition", "group"],
)

kafka_processing_errors_total = Counter(
    "kafka_processing_errors_total",
    "Kafka messages that failed processing (parse errors or handler exceptions).",
    ["topic"],
)

kafka_partition_count = Gauge(
    "kafka_partition_count",
    "Number of partitions assigned to this consumer for a topic.",
    ["topic"],
)

# ── Webhooks ──────────────────────────────────────────────────────────────────

webhook_requests_total = Counter(
    "webhook_requests_total",
    "Outbound webhook delivery attempts.",
    ["status", "reason", "target"],
)

webhook_delivery_duration_seconds = Histogram(
    "webhook_delivery_duration_seconds",
    "Outbound webhook HTTP round-trip latency in seconds.",
    ["status"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

webhook_in_progress = Gauge(
    "webhook_in_progress",
    "Webhook delivery requests currently in flight.",
)

webhook_retries_total = Counter(
    "webhook_retries_total",
    "Webhook delivery retry attempts (does not count the first attempt).",
)

# ── DLQ ───────────────────────────────────────────────────────────────────────

dlq_size = Gauge(
    "dlq_size",
    "Current estimated number of messages in the webhook DLQ topic.",
)

dlq_messages_total = Counter(
    "dlq_messages_total",
    "Total messages written to the webhook DLQ.",
)

dlq_processed_total = Counter(
    "dlq_processed_total",
    "Messages read from the webhook DLQ for retry.",
)

# ── Emails ────────────────────────────────────────────────────────────────────

emails_total = Counter(
    "emails_total",
    "Email delivery attempts.",
    ["status", "provider"],
)

email_send_duration_seconds = Histogram(
    "email_send_duration_seconds",
    "SMTP send latency in seconds.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

email_retries_total = Counter(
    "email_retries_total",
    "Email delivery retry attempts.",
)

# ── Tasks (task-service business metrics) ─────────────────────────────────────

tasks_total = Counter(
    "tasks_total",
    "Task lifecycle events by status (created, in_progress, completed).",
    ["status"],
)

task_processing_duration_seconds = Histogram(
    "task_processing_duration_seconds",
    "Task CRUD operation latency in seconds.",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# ── Celery (scheduler-worker) ─────────────────────────────────────────────────

celery_tasks_total = Counter(
    "celery_tasks_total",
    "Celery task executions.",
    ["task_name", "status"],
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task wall-clock execution time in seconds.",
    ["task_name"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

celery_queue_size = Gauge(
    "celery_queue_size",
    "Estimated number of tasks waiting in the Celery queue (Redis list length).",
)

celery_active_tasks = Gauge(
    "celery_active_tasks",
    "Number of Celery tasks currently executing.",
)
