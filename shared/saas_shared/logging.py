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

Optional when available (contextvars / OTEL):
    - ``trace_id``, ``span_id`` — W3C / OTEL
    - ``request_id`` — HTTP middleware or worker-bound correlation id
    - ``hostname`` — see processors below

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

# Set by setup_logging; used by _catch_all for its direct-stdout fallback so
# service identity is correct without any context-variable propagation.
_current_service_name: str = "unknown"

# Fluent Bit's parser filter has an internal buffer limit (~4 KB by default).
# Tracebacks with deep FastAPI/Starlette call stacks can easily exceed this,
# causing silent parse failure → the `level` field is never extracted →
# the `grep level` filter drops the whole record before it reaches Elasticsearch.
# 3 KB leaves enough room for all other JSON fields to stay well under 4 KB.
_MAX_EXCEPTION_CHARS = 3_000


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
    """Single ECS-compatible timestamp (millisecond precision matches Fluent Bit %L parser)."""
    now = datetime.now(timezone.utc)
    # Use 3-digit milliseconds: Fluent Bit's structlog_json parser uses %L which expects ms.
    # Six-digit microseconds cause the time-key parse to fail (timestamp falls back to
    # ingest time), and on strict parsers the whole record can be skipped.
    s = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
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


def _truncate_exception(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """Keep the tail of the ``exception`` field produced by ``format_exc_info``.

    Fluent Bit's ``parser`` filter has an internal per-record buffer (~4 KB).  A deep
    FastAPI/Starlette traceback can exceed this, causing a silent parse failure that
    drops the entire log record before it reaches Elasticsearch.

    The *tail* is kept (not the head) because the actionable information — the exact
    file, line number, and exception message — is always at the end of a Python traceback.
    """
    exc = event_dict.get("exception")
    if exc and isinstance(exc, str) and len(exc) > _MAX_EXCEPTION_CHARS:
        event_dict["exception"] = "...(truncated)\n" + exc[-_MAX_EXCEPTION_CHARS:]
        event_dict["exception_truncated"] = True
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
    global _current_service_name
    _current_service_name = service_name

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
            _add_trace_id,
            _utc_iso_timestamp,
            _event_to_ecs,
            _auto_exc_info,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _truncate_exception,
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

            tp = request.headers.get("traceparent")
            tp_token = bind_log_traceparent(tp)
            tid = _parse_trace_id_from_traceparent(tp) if tp else None

            # Store on request.state so any code that receives the Request object
            # (exception handlers, dependencies, route handlers) can read them
            # directly without relying on contextvars propagation through
            # BaseHTTPMiddleware's call_next (which creates an anyio task group
            # that does NOT reliably copy contextvars in all Starlette versions).
            request.state.request_id = rid
            request.state.trace_id = tid

            ctx_extras: dict = {"request_id": rid}
            if tid:
                ctx_extras["trace_id"] = tid

            response: Response
            try:
                with bound_contextvars(**ctx_extras):
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
        import json
        import traceback as _tb

        # ── 1. Resolve trace / request IDs from the request object directly ────
        # All context-variable mechanisms (bound_contextvars, _traceparent_ctx,
        # trace.get_current_span) are unreliable here because BaseHTTPMiddleware
        # spawns an anyio task group whose context inheritance varies by Starlette
        # version.  request.state and request.headers are always correct.
        tid = getattr(request.state, "trace_id", None) or (
            _parse_trace_id_from_traceparent(request.headers.get("traceparent", ""))
        )
        rid = getattr(request.state, "request_id", None)

        extra: dict = {}
        if tid:
            extra["trace_id"] = tid
        if rid:
            extra["request_id"] = rid

        # ── 2. structlog path (best-effort, rich output) ─────────────────────
        # exc_info must be passed explicitly: FastAPI exception handlers are
        # called outside an except block so sys.exc_info() is (None, None, None).
        try:
            _log.error(
                "unhandled_exception",
                path=str(request.url.path),
                method=request.method,
                exc_info=exc,
                **extra,
            )
        except Exception:  # noqa: BLE001
            pass

        # ── 3. Guaranteed fallback: write JSON directly to stdout ─────────────
        # This record is structurally identical to what structlog would produce
        # and passes all Fluent Bit filters (level field present, JSON parseable).
        # It is always emitted — even if structlog fails or its processors swallow
        # the event — ensuring the error always reaches Kibana with trace_id.
        try:
            now = datetime.now(timezone.utc)
            ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
            raw_tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
            truncated = len(raw_tb) > _MAX_EXCEPTION_CHARS
            record: dict[str, Any] = {
                "@timestamp": ts,
                "level": "error",
                "service.name": _current_service_name,
                "message": "unhandled_exception",
                "event.name": "unhandled_exception",
                "path": str(request.url.path),
                "method": request.method,
                "exception": ("...(truncated)\n" + raw_tb[-_MAX_EXCEPTION_CHARS:]) if truncated else raw_tb,
                "log_source": "app",
            }
            if truncated:
                record["exception_truncated"] = True
            record.update(extra)
            sys.stdout.write(json.dumps(record) + "\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass

        # ── 4. Sentry (optional) ─────────────────────────────────────────────
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
