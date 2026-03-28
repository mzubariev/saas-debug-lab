"""Tracing backend selection — **one** primary tracer per process.

**Mode A — OpenTelemetry → Jaeger (lab default)**  
Set ``DD_TRACE_ENABLED=false`` (or unset). Applications configure ``otlp_endpoint``
(e.g. ``http://otel-collector:4317``) and use the OTEL SDK + auto-instrumentation.

**Mode B — Datadog APM**  
Set ``DD_TRACE_ENABLED=true``. The OTEL SDK export and OTEL auto-instrumentation in
this repo are **skipped**; ``ddtrace-run`` in Docker CMD owns FastAPI, httpx, Redis,
SQLAlchemy, Celery, etc. Use the Datadog UI for traces (avoid duplicate spans vs OTLP).

See ``README.md`` / ``infra/.env.example`` for full-stack examples.
"""
from __future__ import annotations

import os


def is_datadog_apm_enabled() -> bool:
    """``True`` when Datadog ddtrace should be the only APM tracer (OTEL export off)."""
    return os.environ.get("DD_TRACE_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_otel_sdk_enabled() -> bool:
    """``True`` when this repo should register the OTEL ``TracerProvider`` and exporters."""
    return not is_datadog_apm_enabled()
