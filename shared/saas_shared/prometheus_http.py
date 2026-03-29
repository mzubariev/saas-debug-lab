"""Prometheus HTTP metrics for Starlette / FastAPI (async ``BaseHTTPMiddleware``).

Registers **global** ``prometheus_client`` instruments once per process:

* ``http_requests_total`` — labels ``method``, ``path``, ``status``
* ``http_request_duration_seconds`` — label ``path`` (histogram)

``path`` uses the matched route template (e.g. ``/tasks/{task_id}``) when available to
limit label cardinality; otherwise the request URL path is used.

Scrapes of ``/metrics`` are not recorded (avoids self-noise). Add this middleware **last**
so it wraps the application outermost and captures full request latency.
"""
from __future__ import annotations

import time
from typing import Callable

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total count of HTTP requests processed.",
    ("method", "path", "status"),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ("path",),
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
    ),
)


def _skip_metrics(request: Request) -> bool:
    if request.scope.get("type") != "http":
        return True
    path = request.url.path
    return path == "/metrics" or path.startswith("/metrics/")


def _path_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        template = getattr(route, "path", None)
        if isinstance(template, str) and template:
            root = request.scope.get("root_path") or ""
            return f"{root}{template}" if root else template
    return request.url.path


class PrometheusHttpMetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and latency after the response is ready (status known)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _skip_metrics(request):
            return await call_next(request)

        start = time.perf_counter()
        status_label = "500"
        try:
            response = await call_next(request)
            status_label = str(response.status_code)
            return response
        finally:
            elapsed = time.perf_counter() - start
            path = _path_label(request)
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path=path,
                status=status_label,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(path=path).observe(elapsed)


def install_http_metrics_middleware(app: object) -> None:
    """Attach :class:`PrometheusHttpMetricsMiddleware` (call **after** other middleware)."""
    add_middleware = getattr(app, "add_middleware", None)
    if add_middleware is None:
        msg = "app must implement add_middleware (e.g. FastAPI / Starlette)"
        raise TypeError(msg)
    add_middleware(PrometheusHttpMetricsMiddleware)
