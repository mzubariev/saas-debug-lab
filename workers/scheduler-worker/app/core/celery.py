import time
from threading import local

from celery import Celery
from celery.signals import task_postrun, task_prerun, worker_process_init
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from prometheus_client import start_http_server
from saas_shared.logging import setup_logging
from saas_shared.sentry_setup import setup_sentry_celery
from saas_shared.telemetry import instrument_sqlalchemy_sync_engine, setup_worker_telemetry

from .config import settings

setup_logging(service_name=settings.service_name, log_level=settings.log_level)
# Sentry at import so Beat and the main process capture startup errors.
setup_sentry_celery(service_name=settings.service_name, dsn=settings.sentry_dsn)
# Instrument Celery internals so task spans are created automatically.
# TracerProvider is NOT set here — Beat and the main process produce no spans
# and must not start a BatchSpanProcessor background thread.  Each forked
# worker subprocess sets up its own TracerProvider in worker_process_init.
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


# Thread-local store for per-task start timestamps (Celery workers are forked processes).
_task_start: local = local()


@task_prerun.connect
def _on_task_prerun(task_id: str = "", **kwargs) -> None:
    from saas_shared.prometheus_metrics import celery_active_tasks

    _task_start.__dict__[task_id] = time.perf_counter()
    celery_active_tasks.inc()


@task_postrun.connect
def _on_task_postrun(
    sender=None,
    task_id: str = "",
    state: str = "UNKNOWN",
    **kwargs,
) -> None:
    """Celery invokes this after every task; not called by application code directly."""
    from saas_shared.prometheus_metrics import (
        celery_active_tasks,
        celery_queue_size,
        celery_task_duration_seconds,
        celery_tasks_total,
    )

    name = _task_name(sender)
    status = "success" if state == "SUCCESS" else "failure"
    celery_tasks_total.labels(task_name=name, status=status).inc()
    celery_active_tasks.dec()

    start = _task_start.__dict__.pop(task_id, None)
    if start is not None:
        celery_task_duration_seconds.labels(task_name=name).observe(
            time.perf_counter() - start
        )

    # Update queue size using Redis list length (best-effort; never raises).
    try:
        from redis import Redis as SyncRedis

        r = SyncRedis.from_url(settings.celery_broker_url, socket_timeout=1)
        celery_queue_size.set(r.llen("celery"))
        r.close()
    except Exception:
        pass



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
        "cleanup-old-tasks-hourly": {
            "task": "app.tasks.cleanup_tasks.cleanup_old_tasks",
            "schedule": 3600.0,
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
    )
    setup_sentry_celery(service_name=settings.service_name, dsn=settings.sentry_dsn)
    from ..infrastructure.db.session import get_sync_engine

    instrument_sqlalchemy_sync_engine(get_sync_engine(settings.postgres_dsn))
    start_http_server(settings.metrics_port)
