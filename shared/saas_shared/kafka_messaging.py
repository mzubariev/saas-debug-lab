"""Semantic Kafka spans for OpenTelemetry. Skipped when Datadog APM compose override is used."""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from structlog.contextvars import bound_contextvars

from saas_shared.kafka_trace import attach_kafka_message_trace
from saas_shared.tracing_env import is_otel_sdk_enabled

_TRACER = trace.get_tracer(__name__)


@asynccontextmanager
async def kafka_publish_span(topic: str) -> AsyncIterator[None]:
    """``SpanKind.PRODUCER`` around ``send_and_wait`` — inject runs inside active span."""
    if not is_otel_sdk_enabled():
        yield
        return
    with _TRACER.start_as_current_span(
        f"kafka.publish {topic}",
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": "kafka",
            "messaging.destination.name": topic,
            "messaging.operation": "publish",
        },
    ):
        yield


@contextmanager
def kafka_consume_span(
    topic: str,
    partition: int,
    offset: int,
    envelope_trace_id: str | None,
    kafka_headers: object | None,
) -> Iterator[None]:
    """Extract W3C context, bind per-message ``request_id``, and open a CONSUMER span.

    Every log emitted inside this context manager will carry:
    - ``trace_id``   — propagated from the producer via envelope/headers
    - ``request_id`` — ``kafka:<topic>:<partition>:<offset>`` for log correlation
    """
    msg_id = f"kafka:{topic}:{partition}:{offset}"
    with attach_kafka_message_trace(envelope_trace_id, kafka_headers):
        with bound_contextvars(request_id=msg_id):
            if not is_otel_sdk_enabled():
                yield
                return
            with _TRACER.start_as_current_span(
                f"kafka.receive {topic}",
                kind=SpanKind.CONSUMER,
                attributes={
                    "messaging.system": "kafka",
                    "messaging.destination.name": topic,
                    "messaging.operation": "receive",
                    "messaging.kafka.partition": partition,
                    "messaging.kafka.offset": offset,
                },
            ):
                yield


