"""Shared Sentry SDK initialisation for services and workers (DRY).

Call the appropriate helper once per process after ``setup_logging``. No-op when
``dsn`` is empty.

Workers without ASGI/Celery use :func:`setup_sentry_worker` so default SDK
integrations stay enabled (do not pass ``integrations=[]``).

**Trace ID correlation — two mechanisms working together:**

1. *Bridge middleware* (FastAPI services only): a thin ``BaseHTTPMiddleware`` added
   to the ``FastAPI`` app by :func:`setup_sentry_fastapi` when called with ``app=``.
   It runs while the OTel/DD span is still live (the OTel middleware is outer/LIFO),
   reads the active trace ID, and stamps the Sentry *isolation scope* for that request.
   This covers both error events **and** performance transactions.

2. *``before_send`` / ``before_send_transaction`` hooks* (fallback for workers and
   any event not covered by the bridge): attach the trace ID directly to the event
   dict.  For workers there is no ASGI middleware stack, so only these hooks apply.

When OpenTelemetry is active (``saas_shared.telemetry``), tag ``otel_trace_id``
(32 lowercase hex) matches Jaeger / Kibana / OTLP.

When Datadog APM is active (``DD_TRACE_ENABLED`` / ``ddtrace``), tag ``dd_trace_id``
(decimal string, same as ``dd.trace_id`` in logs) correlates with the Datadog trace UI.

**Observability context — clickable links in every Sentry event:**

Each event includes an "observability" context block with direct links to:
  - Jaeger: the exact trace by ``trace_id``
  - Kibana: the pre-saved Discover view filtered to ``trace_id``
  - Grafana: Service Drilldown dashboard filtered to ``service.name``
"""
from __future__ import annotations

import os
from typing import Any

import sentry_sdk

# ---------------------------------------------------------------------------
# Observability tool base URLs.
# Read from environment so a single change to infra/.env propagates everywhere.
# Localhost defaults work for the standard docker-compose setup.
# ---------------------------------------------------------------------------
_JAEGER_BASE = os.getenv("JAEGER_BASE_URL", "http://localhost:16686")
_GRAFANA_BASE = os.getenv("GRAFANA_BASE_URL", "http://localhost:3000")
_KIBANA_BASE = os.getenv("KIBANA_BASE_URL", "http://localhost:5601")

# Kibana Discover settings.
# Rison-encoded column list (no spaces).  Edit here to change visible fields.
_KIBANA_COLUMNS = (
    "'@timestamp',log_source,service.name,event_name,method,path"
    "level,status,upstream,message,exception,trace_id,request_id"
)

# Set once by each setup_sentry_* function so link builders know the service name.
_sentry_service_name: str = "unknown"


# ---------------------------------------------------------------------------
# Observability context builder
# ---------------------------------------------------------------------------

def _observability_context(trace_id: str) -> dict[str, str]:
    """Return a dict of deep-links to Jaeger / Kibana / Grafana for *trace_id*.

    Attached as ``sentry_sdk.set_context("observability", ...)`` so Sentry renders
    it as a collapsible "OBSERVABILITY" block with clickable URLs on every event.

    The Kibana URL uses the raw ``#/?_a=`` Discover format with explicit columns so
    the table layout is always preserved.
    """
    kibana = (
        f"{_KIBANA_BASE}/app/discover#/"
        f"?_a=("
        f"columns:!({_KIBANA_COLUMNS})"
        f",filters:!()"
        f",interval:auto"
        f",query:(language:kuery,query:'trace_id:\"{trace_id}\"')"
        f",sort:!(!('@timestamp',desc))"
        f")"
        f"&_g=("
        f"filters:!()"
        f",refreshInterval:(pause:!t,value:60000)"
        f",time:(from:now-1h,to:now)"
        f")"
    )
    return {
        "jaeger": f"{_JAEGER_BASE}/trace/{trace_id}",
        "kibana": kibana,
        "grafana": (
            f"{_GRAFANA_BASE}/d/service-drilldown-v2"
            f"?var-job={_sentry_service_name}&from=now-1h&to=now"
        ),
    }


# ---------------------------------------------------------------------------
# Low-level helpers — read current span and write to either an event dict or
# the live Sentry scope.
# ---------------------------------------------------------------------------

def _inject_otel_trace_id_tag(event: dict[str, Any]) -> None:
    """Attach current OTel trace id to a Sentry event ``tags`` dict (before_send hook)."""
    try:
        from opentelemetry import trace
    except ImportError:
        return
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return
    event.setdefault("tags", {})["otel_trace_id"] = format(ctx.trace_id, "032x")


def _inject_dd_trace_id_tag(event: dict[str, Any]) -> None:
    """Attach current Datadog trace id to a Sentry event ``tags`` dict (before_send hook)."""
    try:
        from ddtrace import tracer  # type: ignore[import-untyped]
    except ImportError:
        return
    span = tracer.current_span()
    if span is None or span.context is None:
        return
    tid = span.context.trace_id
    if not tid:
        return
    event.setdefault("tags", {})["dd_trace_id"] = str(tid)


def _inject_otel_trace_id_to_scope() -> None:
    """Set ``otel_trace_id`` tag and ``observability`` context on the current Sentry scope."""
    try:
        from opentelemetry import trace
    except ImportError:
        return
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return
    trace_id = format(ctx.trace_id, "032x")
    sentry_sdk.set_tag("otel_trace_id", trace_id)
    sentry_sdk.set_context("observability", _observability_context(trace_id))


def _inject_dd_trace_id_to_scope() -> None:
    """Set ``dd_trace_id`` on the current Sentry isolation scope while span is live."""
    try:
        from ddtrace import tracer  # type: ignore[import-untyped]
    except ImportError:
        return
    span = tracer.current_span()
    if span is None or span.context is None:
        return
    tid = span.context.trace_id
    if not tid:
        return
    sentry_sdk.set_tag("dd_trace_id", str(tid))


# ---------------------------------------------------------------------------
# before_send / before_send_transaction hooks (workers + fallback)
# ---------------------------------------------------------------------------

# Logger name prefixes whose ERROR records must never become Sentry events.
# OTel/gRPC export failures ("Failed to export traces … DEADLINE_EXCEEDED") are
# infrastructure noise when the collector is unreachable — not application bugs.
_SUPPRESS_LOGGER_PREFIXES = ("opentelemetry", "grpc")


def _is_otel_infra_noise(hint: object) -> bool:
    """Return True when the event originates from an OTel/gRPC logger."""
    if not isinstance(hint, dict):
        return False
    log_record = hint.get("log_record")
    if log_record is None:
        return False
    return any(log_record.name.startswith(p) for p in _SUPPRESS_LOGGER_PREFIXES)


def _before_send_correlation(event: dict[str, Any], hint: object) -> dict[str, Any] | None:
    if _is_otel_infra_noise(hint):
        return None
    _inject_otel_trace_id_tag(event)
    _inject_dd_trace_id_tag(event)
    trace_id = event.get("tags", {}).get("otel_trace_id")
    if trace_id:
        event.setdefault("contexts", {})["observability"] = _observability_context(trace_id)
    return event


def _before_send_transaction_correlation(
    event: dict[str, Any], hint: object
) -> dict[str, Any] | None:
    _inject_otel_trace_id_tag(event)
    _inject_dd_trace_id_tag(event)
    return event


def _sentry_init_kwargs() -> dict[str, Any]:
    return {
        "before_send": _before_send_correlation,
        "before_send_transaction": _before_send_transaction_correlation,
    }


# ---------------------------------------------------------------------------
# Bridge middleware (FastAPI services only)
# ---------------------------------------------------------------------------

def _install_otel_bridge(app: object) -> None:
    """Add a middleware that stamps the Sentry scope with trace IDs on every request.

    **Call order matters (Starlette LIFO).**  This function must be called *before*
    ``setup_telemetry`` so that OTel's instrumentation middleware ends up outermost.
    Request flow then becomes:

        OTel middleware (creates span)
            → Bridge middleware (span already live → sets Sentry tag)
                → route handler

    The tag is written to the Sentry *isolation scope* for the current request, so
    it appears on both error events and performance transactions without relying on
    ``before_send_transaction`` (which fires after the span closes).
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class _TraceIdBridgeMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            _inject_otel_trace_id_to_scope()
            _inject_dd_trace_id_to_scope()
            return await call_next(request)

    app.add_middleware(_TraceIdBridgeMiddleware)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Public setup helpers
# ---------------------------------------------------------------------------

def setup_sentry_fastapi(
    *,
    service_name: str,
    dsn: str,
    httpx: bool = False,
    app: object = None,
) -> None:
    """Starlette + FastAPI Sentry init.

    Args:
        service_name: Value for the ``service`` Sentry tag.
        dsn:          Sentry DSN; pass an empty string to disable.
        httpx:        Set ``True`` for api-gateway to trace outbound HTTP calls.
        app:          The ``FastAPI`` instance.  When provided the OTel/DD bridge
                      middleware is installed.  Must be passed *before*
                      ``setup_telemetry`` is called so OTel ends up outer (LIFO).
    """
    global _sentry_service_name
    _sentry_service_name = service_name
    if not dsn:
        return
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    integrations: list = [
        StarletteIntegration(transaction_style="endpoint"),
        FastApiIntegration(transaction_style="endpoint"),
    ]
    if httpx:
        from sentry_sdk.integrations.httpx import HttpxIntegration

        integrations.append(HttpxIntegration())
    sentry_sdk.init(
        dsn=dsn,
        integrations=integrations,
        traces_sample_rate=0.1,
        send_default_pii=False,
        **_sentry_init_kwargs(),
    )
    sentry_sdk.set_tag("service", service_name)
    if app is not None:
        _install_otel_bridge(app)


def setup_sentry_worker(
    *,
    service_name: str,
    dsn: str,
    worker_name: str,
) -> None:
    """Minimal SDK (Kafka/async workers). No framework integrations; default integrations apply."""
    global _sentry_service_name
    _sentry_service_name = service_name
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
        **_sentry_init_kwargs(),
    )
    sentry_sdk.set_tag("service", service_name)
    sentry_sdk.set_tag("worker", worker_name)


def setup_sentry_celery(
    *,
    service_name: str,
    dsn: str,
) -> None:
    """Celery workers: ``CeleryIntegration`` for tasks and performance."""
    global _sentry_service_name
    _sentry_service_name = service_name
    if not dsn:
        return
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=dsn,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        **_sentry_init_kwargs(),
    )
    sentry_sdk.set_tag("service", service_name)
