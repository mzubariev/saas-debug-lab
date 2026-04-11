"""Prometheus HTTP metrics middleware for Starlette / FastAPI.

Instruments registered in ``saas_shared.metrics`` (single source of truth):
  * ``http_requests_total``          — labels: method, path, status
  * ``http_request_duration_seconds`` — label: path (histogram)
  * ``http_requests_in_progress``    — label: path (gauge, inc before / dec after)
  * ``http_response_size_bytes``     — label: path (histogram, from content-length header)

Path label strategy — normalised actual URL path (not route template):

  Route templates (e.g. FastAPI's ``/tasks/{task_id}/complete``) look clean for a
  single service, but this middleware is shared across all services.  The api-gateway
  uses catch-all proxy routes (``/tasks/{path:path}``) so its template would be
  ``/tasks/{path}`` while task-service shows ``/tasks/{task_id}/complete`` for the
  exact same HTTP call — causing duplicate, confusing labels in Grafana.

  Instead, the *actual* request path is used with dynamic segments normalised:
    - UUIDs           → ``{id}``   ("/tasks/edfb37b9-.../complete" → "/tasks/{id}/complete")
    - Bare integers   → ``{id}``   ("/items/42/detail"             → "/items/{id}/detail")
    - Trailing slash  → stripped  ("/tasks/"                       → "/tasks")

  This produces identical, readable labels across all services for the same endpoint.

Exemplars:
  When an active OpenTelemetry span is present the two histograms
  (``http_request_duration_seconds``, ``http_response_size_bytes``) attach an
  exemplar ``{"TraceID": "<32-hex-trace-id>"}``.  Grafana reads these exemplar dots
  and links them directly to the matching Jaeger trace via the datasource configured
  in ``exemplarTraceIdDestinations``.

Scrapes of ``/metrics`` are excluded to avoid self-noise.
"""
from __future__ import annotations

import re
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .prometheus_metrics import (
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    http_response_size_bytes,
    otel_trace_id as _otel_trace_id,
)

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_INT_SEGMENT_RE = re.compile(r"(?<=/)\d+(?=/|$)")


def _skip_metrics(request: Request) -> bool:
    if request.scope.get("type") != "http":
        return True
    path = request.url.path
    return path == "/metrics" or path.startswith("/metrics/")


def _normalize_path(path: str) -> str:
    """Return a Prometheus-safe path label from the raw request URL path.

    Replaces dynamic segments (UUIDs, integers) with ``{id}`` and strips trailing
    slashes so functionally identical paths always map to the same label value.
    """
    if len(path) > 1:
        path = path.rstrip("/")
    path = _UUID_RE.sub("{id}", path)
    path = _INT_SEGMENT_RE.sub("{id}", path)
    return path


class PrometheusHttpMetricsMiddleware(BaseHTTPMiddleware):
    """Record request count, latency, in-flight gauge, and response size."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _skip_metrics(request):
            return await call_next(request)

        path = _normalize_path(request.url.path)
        http_requests_in_progress.labels(path=path).inc()

        start = time.perf_counter()
        status_label = "500"
        # Capture trace ID before call_next — the span context is reliable here
        # (inside BaseHTTPMiddleware.dispatch, before anyio task hand-off).
        trace_id = _otel_trace_id()
        exemplar = {"TraceID": trace_id} if trace_id else None
        try:
            response = await call_next(request)
            status_label = str(response.status_code)
            size = int(response.headers.get("content-length", 0))
            if exemplar:
                http_response_size_bytes.labels(path=path).observe(size, exemplar)
            else:
                http_response_size_bytes.labels(path=path).observe(size)
            return response
        finally:
            elapsed = time.perf_counter() - start
            http_requests_total.labels(
                method=request.method,
                path=path,
                status=status_label,
            ).inc()
            if exemplar:
                http_request_duration_seconds.labels(path=path).observe(elapsed, exemplar)
            else:
                http_request_duration_seconds.labels(path=path).observe(elapsed)
            http_requests_in_progress.labels(path=path).dec()


def install_http_metrics_middleware(app: object) -> None:
    """Attach :class:`PrometheusHttpMetricsMiddleware` to the app."""
    add_middleware = getattr(app, "add_middleware", None)
    if add_middleware is None:
        msg = "app must implement add_middleware (e.g. FastAPI / Starlette)"
        raise TypeError(msg)
    add_middleware(PrometheusHttpMetricsMiddleware)
