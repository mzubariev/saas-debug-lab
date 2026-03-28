"""OpenTelemetry: W3C propagation, OTLP export (Jaeger via Collector in Docker).

**Default (base ``docker-compose.yml``):** OpenTelemetry only — OTLP to ``otel-collector:4317``,
FastAPI/httpx/redis/sqlalchemy instrumentors. Use the ``observability`` profile for Jaeger + Collector.

**Datadog APM (``docker-compose.datadog.yml`` override):** Set only via that compose file:
``DD_TRACE_ENABLED=true`` and ``ddtrace-run`` on process commands. This module skips OTEL SDK
registration when ``saas_shared.tracing_env.is_datadog_apm_enabled()`` is true.

Do **not** run OTEL export and ddtrace in the same process.
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
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_log = logging.getLogger(__name__)


def _datadog_apm_only() -> bool:
    from saas_shared.tracing_env import is_datadog_apm_enabled

    return is_datadog_apm_enabled()


def _install_propagators() -> None:
    set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),
                W3CBaggagePropagator(),
            ]
        )
    )


def setup_tracer_provider(
    *,
    service_name: str,
    otlp_endpoint: str,
) -> None:
    """Configure global propagators and ``TracerProvider`` with an OTLP gRPC exporter."""
    if _datadog_apm_only():
        _log.info(
            "otel_sdk_skipped service=%s reason=DD_TRACE_ENABLED (Datadog APM / ddtrace-run)",
            service_name,
        )
        return

    _install_propagators()

    ep = (otlp_endpoint or "").strip()
    if not ep:
        _log.warning("no_otlp_endpoint_configured service=%s", service_name)
    else:
        try:
            resource = Resource.create({SERVICE_NAME: service_name})
            provider = TracerProvider(resource=resource, sampler=ALWAYS_ON)
            exporter = OTLPSpanExporter(endpoint=ep)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
        except Exception:  # noqa: BLE001
            _log.exception("otlp_exporter_init_failed endpoint=%s", ep)

    _instrument_client_libraries()


def _instrument_client_libraries() -> None:
    """HTTPX / Redis auto-instrumentation (services only install what they use)."""
    try:
        import httpx  # noqa: F401 — dependency of gateway, dispatcher, integration, …

        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception:  # noqa: BLE001
        _log.debug("otel_httpx_instrumentation_skipped", exc_info=True)

    try:
        import redis  # noqa: F401

        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception:  # noqa: BLE001
        _log.debug("otel_redis_instrumentation_skipped", exc_info=True)


def instrument_sqlalchemy_async_engine(async_engine: object) -> None:
    """Attach SQLAlchemy 2 async engine to OTEL (spans for DB statements)."""
    if _datadog_apm_only():
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        sync_engine = getattr(async_engine, "sync_engine", async_engine)
        SQLAlchemyInstrumentor().instrument(engine=sync_engine)
    except Exception:  # noqa: BLE001
        _log.exception("otel_sqlalchemy_instrumentation_failed")


def instrument_sqlalchemy_sync_engine(engine: object) -> None:
    """Attach a sync SQLAlchemy engine (e.g. Celery worker DB)."""
    if _datadog_apm_only():
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
    except Exception:  # noqa: BLE001
        _log.exception("otel_sqlalchemy_sync_instrumentation_failed")


def setup_telemetry(
    app,
    service_name: str,
    otlp_endpoint: str,
) -> None:
    """FastAPI services: OTLP export + ``FastAPIInstrumentor``."""
    setup_tracer_provider(service_name=service_name, otlp_endpoint=otlp_endpoint)
    if _datadog_apm_only():
        return
    FastAPIInstrumentor.instrument_app(app)


def setup_worker_telemetry(
    service_name: str,
    otlp_endpoint: str,
) -> None:
    """Workers / asyncio consumers: OTLP only (no ASGI instrumentation)."""
    setup_tracer_provider(service_name=service_name, otlp_endpoint=otlp_endpoint)
