"""Kafka envelope ``trace_id`` ↔ runtime context for logs and OpenTelemetry.

* **Producers** call :func:`otel_kafka_headers` (W3C ``traceparent`` / ``tracestate`` / ``baggage``)
  on each Kafka record **in addition to** the JSON envelope ``trace_id`` field.
* **Consumers** use :func:`attach_kafka_message_trace` to ``extract`` W3C context from message
  headers when present, else fall back to the envelope ``trace_id``.
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


def otel_kafka_headers() -> list[tuple[str, bytes]]:
    """W3C trace context for Kafka message headers (pairs OTEL Jaeger with envelope ``trace_id``)."""
    try:
        from opentelemetry.propagate import inject

        carrier: dict[str, str] = {}
        inject(carrier)
        return [(k, v.encode("utf-8")) for k, v in carrier.items()]
    except Exception:  # noqa: BLE001
        return []


def _kafka_headers_to_carrier(headers: object | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not headers:
        return out
    for item in headers:
        if not item or len(item) < 2:
            continue
        k, v = item[0], item[1]
        ks = k.decode("utf-8", errors="replace") if isinstance(k, bytes) else str(k)
        vs = v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)
        out[ks.lower()] = vs
    return out


def _carrier_has_w3c_trace(carrier: dict[str, str]) -> bool:
    return bool(carrier.get("traceparent"))


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
def attach_kafka_message_trace(
    envelope_trace_id: str | None,
    kafka_headers: object | None = None,
) -> Iterator[None]:
    """Restore W3C context from Kafka headers (preferred) or envelope ``trace_id``."""
    from opentelemetry import context as otel_context
    from opentelemetry import trace

    normalized = normalize_kafka_trace_id(envelope_trace_id)
    tokens: list[object] = []
    bound_trace_log = False
    try:
        carrier = _kafka_headers_to_carrier(kafka_headers)
        used_extract = False
        if _carrier_has_w3c_trace(carrier):
            try:
                from opentelemetry.propagate import extract

                ctx = extract(carrier)
                tokens.append(otel_context.attach(ctx))
                used_extract = True
                span = trace.get_current_span()
                sc = span.get_span_context() if span is not None else None
                if sc is not None and getattr(sc, "is_valid", False):
                    structlog.contextvars.bind_contextvars(trace_id=format(sc.trace_id, "032x"))
                    bound_trace_log = True
            except Exception:  # noqa: BLE001
                used_extract = False

        if not used_extract and normalized:
            structlog.contextvars.bind_contextvars(trace_id=normalized)
            bound_trace_log = True
            t = _otel_attach_remote_trace(normalized)
            if t is not None:
                tokens.append(t)

        yield
    finally:
        if bound_trace_log:
            structlog.contextvars.unbind_contextvars("trace_id")
        for tok in reversed(tokens):
            try:
                otel_context.detach(tok)
            except Exception:  # noqa: BLE001
                pass
