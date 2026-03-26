"""Kafka envelope ``trace_id`` ↔ runtime context for logs and OpenTelemetry.

* **Producers** call :func:`current_trace_id_for_kafka_envelope` when encoding v1 envelopes.
* **Consumers** wrap handling in :func:`attach_kafka_message_trace` so structlog JSON includes
  ``trace_id`` and OTEL ``get_current_span()`` carries the propagated trace (when
  ``opentelemetry-api`` is installed).
"""
from __future__ import annotations

import secrets
from contextlib import contextmanager
from typing import Iterator

import structlog.contextvars


def normalize_kafka_trace_id(raw: str | None) -> str | None:
    """Return lowercase 32-hex trace id, or ``None`` if missing / invalid."""
    if not raw or not isinstance(raw, str):
        return None
    h = raw.strip().lower().replace("-", "")
    if len(h) != 32:
        return None
    for c in h:
        if c not in "0123456789abcdef":
            return None
    return h


def current_trace_id_for_kafka_envelope() -> str | None:
    """W3C trace id from the active OTEL span, else from Sentry ``traceparent``, else ``None``."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is not None and getattr(ctx, "is_valid", False):
            return format(ctx.trace_id, "032x")
    except Exception:  # noqa: BLE001
        pass

    try:
        import sentry_sdk

        tp = sentry_sdk.get_traceparent()
        if not tp:
            return None
        parts = tp.split("-")
        if len(parts) >= 2 and len(parts[1]) >= 16:
            return normalize_kafka_trace_id(parts[1])
    except Exception:  # noqa: BLE001
        pass

    return None


def _otel_attach_remote_trace(trace_id_hex: str) -> object | None:
    """Attach a remote trace as the current OTEL context; returns detach token or ``None``."""
    try:
        from opentelemetry import context as otel_context
        from opentelemetry import trace
        from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
    except ImportError:
        return None

    try:
        trace_id_int = int(trace_id_hex, 16)
    except ValueError:
        return None
    if trace_id_int == 0:
        return None

    span_id_int = secrets.randbits(64)
    sc = SpanContext(
        trace_id=trace_id_int,
        span_id=span_id_int,
        is_remote=True,
        trace_flags=TraceFlags.SAMPLED,
    )
    span = NonRecordingSpan(sc)
    ctx = trace.set_span_in_context(span, otel_context.get_current())
    return otel_context.attach(ctx)


@contextmanager
def attach_kafka_message_trace(envelope_trace_id: str | None) -> Iterator[None]:
    """Bind envelope ``trace_id`` for structlog and OTEL for the duration of the block."""
    normalized = normalize_kafka_trace_id(envelope_trace_id)
    otel_token = None
    try:
        if normalized:
            structlog.contextvars.bind_contextvars(trace_id=normalized)
            otel_token = _otel_attach_remote_trace(normalized)
        yield
    finally:
        if normalized:
            structlog.contextvars.unbind_contextvars("trace_id")
        if otel_token is not None:
            try:
                from opentelemetry import context as otel_context

                otel_context.detach(otel_token)
            except Exception:  # noqa: BLE001
                pass
