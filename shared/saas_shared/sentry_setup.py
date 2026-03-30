"""Shared Sentry SDK initialisation for services and workers (DRY).

Call the appropriate helper once per process after ``setup_logging``. No-op when
``dsn`` is empty.

Workers without ASGI/Celery use :func:`setup_sentry_worker` so default SDK
integrations stay enabled (do not pass ``integrations=[]``).

When OpenTelemetry is active (``saas_shared.telemetry``), errors and transactions
include tag ``otel_trace_id`` (32 lowercase hex), matching Jaeger / Kibana / OTLP
``trace_id`` so you can search the same id in Sentry.
"""
from __future__ import annotations

from typing import Any

import sentry_sdk


def _inject_otel_trace_id_tag(event: dict[str, Any]) -> None:
    """Attach current OTEL trace id to Sentry ``tags`` when a valid span exists."""
    try:
        from opentelemetry import trace
    except ImportError:
        return
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return
    event.setdefault("tags", {})["otel_trace_id"] = format(ctx.trace_id, "032x")


def _before_send_otel(event: dict[str, Any], hint: object) -> dict[str, Any] | None:
    _inject_otel_trace_id_tag(event)
    return event


def _before_send_transaction_otel(
    event: dict[str, Any], hint: object
) -> dict[str, Any] | None:
    _inject_otel_trace_id_tag(event)
    return event


def _sentry_init_kwargs() -> dict[str, Any]:
    return {
        "before_send": _before_send_otel,
        "before_send_transaction": _before_send_transaction_otel,
    }


def setup_sentry_fastapi(
    *,
    service_name: str,
    dsn: str,
    httpx: bool = False,
) -> None:
    """Starlette + FastAPI; set ``httpx=True`` for api-gateway (outbound trace headers)."""
    if not dsn:
        return
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    integrations: list = [
        StarletteIntegration(transaction_style="endpoint"),
        FastApiIntegration(transaction_style="endpoint"),
    ]
    if httpx:
        from sentry_sdk.integrations.httpx import HttpxIntegration

        integrations.append(HttpxIntegration())
    sentry_sdk.init(
        dsn=dsn,
        integrations=integrations,
        traces_sample_rate=0.1,
        send_default_pii=False,
        **_sentry_init_kwargs(),
    )
    sentry_sdk.set_tag("service", service_name)


def setup_sentry_worker(
    *,
    service_name: str,
    dsn: str,
    worker_name: str,
) -> None:
    """Minimal SDK (Kafka/async workers). No framework integrations; default integrations apply."""
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
        **_sentry_init_kwargs(),
    )
    sentry_sdk.set_tag("service", service_name)
    sentry_sdk.set_tag("worker", worker_name)


def setup_sentry_celery(
    *,
    service_name: str,
    dsn: str,
) -> None:
    """Celery workers: ``CeleryIntegration`` for tasks and performance."""
    if not dsn:
        return
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=dsn,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        **_sentry_init_kwargs(),
    )
    sentry_sdk.set_tag("service", service_name)
