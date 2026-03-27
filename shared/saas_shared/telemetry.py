"""OpenTelemetry: W3C propagation, OTLP export to Jaeger and optionally Datadog Agent.

* **Jaeger** — set ``otlp_endpoint`` (gRPC), e.g. ``http://jaeger:4317``.
* **Datadog** — either APM via ``ddtrace-run`` (default in this lab) **or** OTLP to the
  Agent: set ``otlp_datadog_endpoint`` (e.g. ``http://datadog-agent:4317``) after enabling
  the Agent OTLP receiver. When using OTLP to Datadog, set ``DD_TRACE_ENABLED=false`` to
  avoid duplicate traces in Datadog.
"""
from __future__ import annotations

import logging
from opentelemetry import trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_log = logging.getLogger(__name__)


def _install_propagators() -> None:
    set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),
                W3CBaggagePropagator(),
            ]
        )
    )


def _nonempty_endpoints(otlp_endpoint: str, otlp_datadog_endpoint: str) -> list[str]:
    out: list[str] = []
    for raw in (otlp_endpoint, otlp_datadog_endpoint):
        ep = (raw or "").strip()
        if ep:
            out.append(ep)
    return out


def setup_tracer_provider(
    *,
    service_name: str,
    otlp_endpoint: str,
    otlp_datadog_endpoint: str = "",
) -> None:
    """Configure global propagators and ``TracerProvider`` with one or two OTLP exporters."""
    _install_propagators()

    endpoints = _nonempty_endpoints(otlp_endpoint, otlp_datadog_endpoint)
    if not endpoints:
        _log.warning("no_otlp_endpoints_configured service=%s", service_name)
        return

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    for ep in endpoints:
        try:
            exporter = OTLPSpanExporter(endpoint=ep)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception:  # noqa: BLE001
            _log.exception("otlp_exporter_init_failed endpoint=%s", ep)

    trace.set_tracer_provider(provider)


def setup_telemetry(
    app,
    service_name: str,
    otlp_endpoint: str,
    otlp_datadog_endpoint: str = "",
) -> None:
    """FastAPI services: OTLP export + ``FastAPIInstrumentor``."""
    setup_tracer_provider(
        service_name=service_name,
        otlp_endpoint=otlp_endpoint,
        otlp_datadog_endpoint=otlp_datadog_endpoint,
    )
    FastAPIInstrumentor.instrument_app(app)


def setup_worker_telemetry(
    service_name: str,
    otlp_endpoint: str,
    otlp_datadog_endpoint: str = "",
) -> None:
    """Workers / asyncio consumers: OTLP only (no ASGI instrumentation)."""
    setup_tracer_provider(
        service_name=service_name,
        otlp_endpoint=otlp_endpoint,
        otlp_datadog_endpoint=otlp_datadog_endpoint,
    )
