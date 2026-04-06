"""Structured JSON logging to stdout for Fluent Bit → Elasticsearch → Kibana.

Why not double-encode JSON?
    If application code logs ``logger.info(json.dumps({"a": 1}))`` (or ``print(json.dumps(...))``),
    the *event* becomes a **string** that *looks* like JSON. ``JSONRenderer`` then escapes that
    string inside the outer JSON object, producing ``"event": "{\\"a\\": 1}"``. Downstream,
    Fluent Bit's ``parser`` with ``Format json`` yields a field ``event`` of type **string**, not
    nested JSON — Kibana cannot index structured fields inside that blob without another parse
    pass and fragile regex. Worse, Docker's json-file driver already wraps each line in an object
    with a ``log`` key; the *inner* payload must be **one** JSON object per line, not a string
    containing JSON.

Why emit structured logs directly (native JSON per line)?
    ``structlog`` + ``JSONRenderer`` writes a **single** JSON object per line to stdout. Fluent Bit
    tails the file, reads the ``log`` field from Docker's wrapper JSON, and parses it **once** with
    a JSON parser. Each key becomes a top-level field in Elasticsearch. No string-within-string,
    no custom regex parsers, and no risk of log injection breaking JSON boundaries.

Why this helps Elasticsearch / Kibana?
    Fields like ``@timestamp``, ``level``, ``service``, ``message``, ``trace_id``, and
    ``request_id`` are indexed as typed columns. You can filter, aggregate, and build dashboards
    (e.g. error rate by service, latency correlation with trace_id) without parsing raw strings.

Standard fields on every line:
    - ``@timestamp`` / ``timestamp`` — ISO8601 UTC (``...Z``)
    - ``level`` — e.g. ``info``, ``warning``, ``error``
    - ``service`` — logical service name (same value as ``service_name`` for compatibility)
    - ``message`` — human-oriented line (copy of structlog's ``event`` key)

Optional when available (contextvars / OTEL / ddtrace):
    - ``trace_id``, ``span_id`` — W3C / OTEL
    - ``request_id`` — HTTP middleware or worker-bound correlation id
    - ``hostname``, ``dd.*`` — see processors below

Application code should use only ``structlog.get_logger()`` — never ``print(json.dumps(...))``
for operational logs.
"""
from __future__ import annotations

import contextvars
import logging
import os
import socket
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import structlog
from structlog.typing import EventDict

_traceparent_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "saas_shared_log_traceparent", default=None
)


def bind_log_traceparent(traceparent: str | None) -> contextvars.Token | None:
    """Bind W3C ``traceparent`` for the current async/task context (e.g. from a request header).

    Returns a token for :func:`reset_log_traceparent`. When ``traceparent`` is falsy, returns
    ``None`` and does not change the context.
    """
    if not traceparent:
        return None
    return _traceparent_ctx.set(traceparent.strip())


def reset_log_traceparent(token: contextvars.Token | None) -> None:
    """Reset context after :func:`bind_log_traceparent` (e.g. in middleware ``finally``)."""
    if token is not None:
        _traceparent_ctx.reset(token)


def _parse_trace_id_from_traceparent(value: str) -> str | None:
    """Parse trace id from W3C ``traceparent`` (``00`` version): ``00-<trace_id>-<parent_id>-<flags>``."""
    parts = value.strip().split("-")
    if len(parts) != 4 or parts[0] != "00":
        return None
    tid = parts[1]
    if len(tid) != 32 or any(c not in "0123456789abcdefABCDEF" for c in tid):
        return None
    return tid.lower()


def _resolve_hostname() -> str:
    return (
        os.environ.get("SERVER_NAME")
        or os.environ.get("HOSTNAME")
        or socket.gethostname()
    )


def _add_hostname() -> Callable[..., EventDict]:
    name = _resolve_hostname()

    def processor(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
        event_dict["hostname"] = name
        return event_dict

    return processor


def _add_service_fields(service_name: str) -> Callable[..., EventDict]:
    """ECS-compatible service field."""

    def processor(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
        event_dict["service.name"] = service_name
        return event_dict

    return processor


def _inject_dd_trace_context(
    _logger: Any, _method: str, event_dict: EventDict
) -> EventDict:
    """Datadog APM fields only when ddtrace has an active span (never merged into ``trace_id``)."""
    try:
        from ddtrace import tracer  # type: ignore[import-untyped]

        span = tracer.current_span()
        if span is None or span.context is None:
            return event_dict
        ctx = span.context
        dd_tid = str(ctx.trace_id)
        if not dd_tid:
            return event_dict
        event_dict["dd.trace_id"] = dd_tid
        event_dict["dd.span_id"] = str(span.span_id)
        if span.service:
            event_dict["dd.service"] = span.service
        env_tag = span.get_tag("env")
        if env_tag:
            event_dict["dd.env"] = env_tag
    except Exception as e:  # noqa: BLE001
        event_dict["dd_trace_error"] = str(e)
    return event_dict


def _add_level_name(_logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    name = method_name.lower()
    if name == "warn":
        name = "warning"
    event_dict["level"] = name
    return event_dict


def _add_trace_id(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """W3C-style ``trace_id`` (32 hex): OTEL current span, then bound/context ``traceparent``."""
    if "trace_id" in event_dict:
        event_dict.pop("traceparent", None)
        return event_dict
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is not None and getattr(ctx, "is_valid", False):
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
            event_dict.pop("traceparent", None)
            return event_dict
    except Exception as e:  # noqa: BLE001
        event_dict["logging_error"] = str(e)

    tp = _traceparent_ctx.get() or event_dict.pop("traceparent", None)
    event_dict.pop("traceparent", None)
    if tp:
        parsed = _parse_trace_id_from_traceparent(tp)
        if parsed:
            event_dict["trace_id"] = parsed
    return event_dict


def _utc_iso_timestamp(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """Single ECS-compatible timestamp."""
    now = datetime.now(timezone.utc)
    s = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}Z"
    event_dict["@timestamp"] = s
    return event_dict


def _auto_exc_info(_logger: Any, method: str, event_dict: EventDict) -> EventDict:
    """Auto-inject ``exc_info`` when an exception is active so developers don't have to remember it.

    Fires only for ``warning`` / ``error`` / ``critical`` / ``exception`` calls made inside an
    active ``except`` block (``sys.exc_info()[1] is not None``).  Outside exception handlers the
    processor is a no-op so regular warning/error calls are not affected.
    If ``exc_info`` is already set explicitly the existing value is preserved.
    """
    if (
        method in ("warning", "error", "critical", "exception")
        and "exc_info" not in event_dict
        and sys.exc_info()[1] is not None
    ):
        event_dict["exc_info"] = True
    return event_dict


def _event_to_ecs(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """Map structlog event → ECS fields safely."""
    ev = event_dict.get("event")

    if ev is not None:
        if "message" not in event_dict:
            event_dict["message"] = ev if isinstance(ev, str) else str(ev)

        event_dict["event.name"] = ev

    return event_dict


def _silence_noisy_stdlib_loggers() -> None:
    """Keep third-party noise down; application code should use structlog only."""
    for name in (
        "httpx",
        "httpcore",
        "aiokafka",
        "kafka",
        "asyncio",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_logging(*, service_name: str, log_level: str = "INFO") -> None:
    """Configure structlog → **one JSON object per line** on stdout (no nested JSON strings).

    Call once per process (or again after Celery fork in ``worker_process_init``).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Stdlib (libraries only): plain text message to stdout — avoids double-wrapping structlog JSON.
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    _silence_noisy_stdlib_loggers()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_level_name,
            _add_hostname(),
            _add_service_fields(service_name),
            _inject_dd_trace_context,
            _add_trace_id,
            _utc_iso_timestamp,
            _event_to_ecs,
            _auto_exc_info,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def install_request_context_middleware(app: object) -> None:
    """Bind ``request_id`` for each HTTP request (``X-Request-ID`` / ``X-Correlation-ID`` or generated).

    Starlette is imported lazily so workers without FastAPI do not need it on ``import saas_shared.logging``.
    Call **after** ``install_http_metrics_middleware`` so this layer is outermost: ``request_id`` is
    bound before Prometheus timing and all inner middleware/handlers.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    from structlog.contextvars import bound_contextvars

    class RequestContextMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            incoming = request.headers.get("x-request-id") or request.headers.get(
                "x-correlation-id"
            )
            rid = (incoming or "").strip() or uuid.uuid4().hex

            # Bind traceparent as a structlog fallback so _add_trace_id can
            # parse trace_id even when Starlette's BaseHTTPMiddleware breaks
            # OTel's contextvars span propagation between middleware layers.
            tp_token = bind_log_traceparent(request.headers.get("traceparent"))
            response: Response
            try:
                with bound_contextvars(request_id=rid):
                    response = await call_next(request)
            finally:
                reset_log_traceparent(tp_token)
            response.headers["X-Request-ID"] = rid
            return response

    app.add_middleware(RequestContextMiddleware)


def install_unhandled_exception_middleware(app: object) -> None:
    """Catch unhandled exceptions before FastAPI's plain-text ``ServerErrorMiddleware``.

    Without this, any exception that escapes a route handler is logged by uvicorn as
    plain text on **stderr** — invisible in Kibana (Fluent Bit's JSON parser drops it).
    This handler logs it as structured JSON to stdout (same pipeline as every other log)
    and optionally forwards to Sentry.

    Register **after** ``app = FastAPI(...)`` in each service ``main.py``.
    HTTPException and RequestValidationError have their own handlers and are not affected.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    _log = structlog.get_logger("saas_shared.exceptions")

    async def _catch_all(request: Request, exc: Exception) -> JSONResponse:
        _log.error(
            "unhandled_exception",
            path=str(request.url.path),
            method=request.method,
        )
        try:
            import sentry_sdk  # optional dependency

            sentry_sdk.capture_exception(exc)
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    app.add_exception_handler(Exception, _catch_all)
