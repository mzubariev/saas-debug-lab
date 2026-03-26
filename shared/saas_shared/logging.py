"""Structured JSON logging to stdout for Fluent Bit → Elasticsearch → Kibana.

Every line is a single JSON object with at least:
  - hostname      — host / pod identity (``HOSTNAME``, ``SERVER_NAME``, or socket hostname)
  - service_name  — logical service / worker name
  - event         — message / event name (structlog convention)
  - level         — log level (e.g. info, warning)
  - trace_id      — W3C trace id (32 hex) when OTEL has a span, or from ``traceparent`` /
                    :func:`bind_log_traceparent` (never copied from Datadog)
  - dd.trace_id   — only when ddtrace has an active span (kept separate from ``trace_id``)

No file handlers; ``PrintLoggerFactory`` writes to stdout only.
"""
from __future__ import annotations

import contextvars
import logging
import os
import socket
import sys
from typing import Any

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


def _add_hostname():
    name = _resolve_hostname()

    def processor(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
        event_dict["hostname"] = name
        return event_dict

    return processor


def _add_service_name(service_name: str):
    def processor(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
        event_dict["service_name"] = service_name
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
    except Exception as e:
        event_dict["dd_trace_error"] = str(e)
    return event_dict


def _add_level_name(_logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Required field ``level`` (e.g. info, warning)."""
    name = method_name.lower()
    if name == "warn":
        name = "warning"
    event_dict["level"] = name
    return event_dict


def _add_trace_id(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """W3C-style ``trace_id`` (32 hex): OTEL current span, then bound/context ``traceparent``.

    Datadog ids stay under ``dd.*`` only; they are never copied here.
    The raw ``traceparent`` bound key is dropped from output (``trace_id`` is canonical).
    """
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
    except Exception as e:
        event_dict["logging_error"] = str(e)

    tp = _traceparent_ctx.get() or event_dict.pop("traceparent", None)
    event_dict.pop("traceparent", None)
    if tp:
        parsed = _parse_trace_id_from_traceparent(tp)
        if parsed:
            event_dict["trace_id"] = parsed
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
    """Configure structlog → strict JSON on stdout. Call once per process (or per Celery fork)."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Stdlib logs (libraries only — app code uses structlog) → stdout, message-only.
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
            _add_service_name(service_name),
            _inject_dd_trace_context,
            _add_trace_id,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
