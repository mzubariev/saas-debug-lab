from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, task_success, worker_process_init
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from prometheus_client import start_http_server
from saas_shared.logging import setup_logging
from saas_shared.sentry_setup import setup_sentry_celery
from saas_shared.telemetry import instrument_sqlalchemy_sync_engine, setup_worker_telemetry

from .config import settings


setup_logging(service_name=settings.service_name, log_level=settings.log_level)
# Sentry at import (beat/parent) and again in worker_process_init after fork.
setup_sentry_celery(service_name=settings.service_name, dsn=settings.sentry_dsn)
# OTLP + HTTPX/Redis patches before Celery hooks so task spans use a real TracerProvider.
setup_worker_telemetry(
    settings.service_name,
    settings.otlp_endpoint,
    settings.otlp_datadog_endpoint,
)

CeleryInstrumentor().instrument()

celery_app = Celery(
    settings.service_name,
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.webhook_tasks",
        "app.tasks.cleanup_tasks",
    ],
)


def _task_name(sender) -> str:
    if sender is None:
        return "unknown"
    return getattr(sender, "name", None) or getattr(sender, "__name__", "unknown")


@task_success.connect
def _on_celery_task_success(sender=None, **kwargs) -> None:
    from ..metrics import celery_tasks_total

    celery_tasks_total.labels(task_name=_task_name(sender)).inc()


@task_failure.connect
def _on_celery_task_failure(sender=None, **kwargs) -> None:
    from ..metrics import celery_failures_total

    celery_failures_total.labels(task_name=_task_name(sender)).inc()


celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Beat schedule — embedded in the worker process (single instance lab).
    beat_schedule={
        "retry-failed-webhooks-every-60s": {
            "task": "app.tasks.webhook_tasks.retry_failed_webhooks",
            "schedule": 60.0,
        },
        "cleanup-old-tasks-daily": {
            "task": "app.tasks.cleanup_tasks.cleanup_old_tasks",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)


@worker_process_init.connect
def init_worker_process(**kwargs) -> None:
    """Configure structlog, OpenTelemetry, and Sentry in each forked worker process."""
    setup_logging(service_name=settings.service_name, log_level=settings.log_level)
    setup_worker_telemetry(
        settings.service_name,
        settings.otlp_endpoint,
        settings.otlp_datadog_endpoint,
    )
    setup_sentry_celery(service_name=settings.service_name, dsn=settings.sentry_dsn)
    from ..infrastructure.db.session import get_sync_engine

    instrument_sqlalchemy_sync_engine(get_sync_engine(settings.postgres_dsn))
    start_http_server(settings.metrics_port)
