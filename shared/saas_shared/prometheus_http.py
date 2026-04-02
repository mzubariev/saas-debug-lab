"""Prometheus HTTP metrics middleware for Starlette / FastAPI.

Instruments registered in ``saas_shared.metrics`` (single source of truth):
  * ``http_requests_total``          — labels: method, path, status
  * ``http_request_duration_seconds`` — label: path (histogram)
  * ``http_requests_in_progress``    — label: path (gauge, inc before / dec after)
  * ``http_response_size_bytes``     — label: path (histogram, from content-length header)

``path`` is resolved to the matched route template (e.g. ``/tasks/{task_id}``) to
limit label cardinality; falls back to the raw URL path when no template exists.

Scrapes of ``/metrics`` are excluded to avoid self-noise.
"""
from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .metrics import (
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    http_response_size_bytes,
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
    """Record request count, latency, in-flight gauge, and response size."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _skip_metrics(request):
            return await call_next(request)

        path = _path_label(request)
        http_requests_in_progress.labels(path=path).inc()

        start = time.perf_counter()
        status_label = "500"
        try:
            response = await call_next(request)
            status_label = str(response.status_code)
            size = int(response.headers.get("content-length", 0))
            http_response_size_bytes.labels(path=path).observe(size)
            return response
        finally:
            elapsed = time.perf_counter() - start
            http_requests_total.labels(
                method=request.method,
                path=path,
                status=status_label,
            ).inc()
            http_request_duration_seconds.labels(path=path).observe(elapsed)
            http_requests_in_progress.labels(path=path).dec()


def install_http_metrics_middleware(app: object) -> None:
    """Attach :class:`PrometheusHttpMetricsMiddleware` to the app."""
    add_middleware = getattr(app, "add_middleware", None)
    if add_middleware is None:
        msg = "app must implement add_middleware (e.g. FastAPI / Starlette)"
        raise TypeError(msg)
    add_middleware(PrometheusHttpMetricsMiddleware)
