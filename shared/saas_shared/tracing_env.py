"""Tracing backend selection — **one** primary tracer per process.

**OpenTelemetry (default)** — base ``docker-compose.yml`` + ``observability`` profile for
Jaeger and the Collector. Applications use ``otlp_endpoint`` (e.g. ``http://otel-collector:4317``)
with the OTEL SDK and auto-instrumentation. ``DD_TRACE_ENABLED`` is unset.

**Datadog APM** — use ``docker-compose.datadog.yml`` with the ``datadog`` profile. That file
sets ``DD_TRACE_ENABLED=true`` and ``ddtrace-run`` on service commands. The OTEL SDK export
and OTEL auto-instrumentation in this repo are **skipped**; use the Datadog UI for traces.

Switch modes **only** via compose files; never enable OTEL export and ddtrace together.

See ``README.md`` (Observability) and ``infra/docker-compose.datadog.yml``.
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
