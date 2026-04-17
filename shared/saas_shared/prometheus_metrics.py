"""Unified Prometheus metrics for all SaaS Debug Lab services and workers.

Single source of truth — every Counter, Histogram, and Gauge is registered
here exactly once per process.  Services and workers import what they need:

    from saas_shared.prometheus_metrics import http_requests_total, kafka_messages_consumed_total

IMPORTANT: never instantiate Prometheus instruments inside functions.
           Always import from this module at call sites.

Exemplar helper
---------------
``otel_trace_id()`` returns the active OpenTelemetry trace ID as a 32-char hex
string (or ``None`` when no span is active).  Pass it to histogram ``.observe()``
calls so Grafana can link metric dots to the matching Jaeger trace:

    tid = otel_trace_id()
    exemplar = {"trace_id": tid} if tid else None
    my_histogram.labels(...).observe(value, exemplar)  # exemplar=None is a no-op
"""
from opentelemetry import trace as _otel_trace
from prometheus_client import Counter, Gauge, Histogram


def otel_trace_id() -> str | None:
    """Return the active OTel trace ID as a 32-char hex string, or None."""
    span = _otel_trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return None

# ── HTTP ──────────────────────────────────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests processed.",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
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

kafka_processing_errors_total = Counter(
    "kafka_processing_errors_total",
    "Kafka messages that failed processing (parse errors or handler exceptions).",
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

dlq_messages_total = Counter(
    "dlq_messages_total",
    "Total messages written to the webhook DLQ.",
)

dlq_processed_total = Counter(
    "dlq_processed_total",
    "Messages read from the webhook DLQ and dispatched as Celery retry tasks.",
)

dlq_retry_result_total = Counter(
    "dlq_retry_result_total",
    "Per-message DLQ delivery outcomes after all Celery retries.",
    ["result"],  # "success" | "failure"
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

# ── Host / container resource limits ──────────────────────────────────────────
# These two Gauges are set once at import time and let PromQL normalise
# process_cpu_seconds_total and process_resident_memory_bytes to saturation
# percentages without requiring an external cAdvisor / node_exporter.
# Prometheus adds the ``job`` label automatically, so dashboard queries can
# join on it:  process_resident_memory_bytes / container_memory_limit_bytes

import os as _os


def _cgroup_memory_limit_bytes() -> float:
    """Return the container memory limit in bytes, or 0 if unlimited / unknown.

    Supports cgroups v1 (memory.limit_in_bytes) and v2 (memory.max).
    Returns 0 when running outside a container or when no limit is set so
    callers can distinguish "not applicable" from a real limit.
    """
    _UNLIMITED_V1 = 9_223_372_036_854_771_712  # 2^63 - 4096 — Linux "no limit" sentinel
    for path in (
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",  # cgroups v1
        "/sys/fs/cgroup/memory.max",                     # cgroups v2
    ):
        try:
            raw = open(path).read().strip()  # noqa: WPS515
            if raw == "max":
                return 0  # v2 unlimited
            value = int(raw)
            return 0 if value >= _UNLIMITED_V1 else float(value)
        except (FileNotFoundError, ValueError, PermissionError):
            continue
    return 0


machine_cpu_cores = Gauge(
    "machine_cpu_cores",
    "Number of logical CPU cores visible to this process (os.cpu_count()). "
    "Used as the denominator for CPU saturation: rate(process_cpu_seconds_total) / machine_cpu_cores.",
)
machine_cpu_cores.set(float(_os.cpu_count() or 1))

container_memory_limit_bytes = Gauge(
    "container_memory_limit_bytes",
    "Container memory limit in bytes read from cgroups at startup. "
    "0 means no limit is configured or the metric is not applicable (e.g. macOS dev environment). "
    "Used as the denominator for memory saturation: process_resident_memory_bytes / container_memory_limit_bytes.",
)
container_memory_limit_bytes.set(_cgroup_memory_limit_bytes())
