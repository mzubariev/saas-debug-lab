import sentry_sdk
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from sentry_sdk.integrations.celery import CeleryIntegration
from saas_shared.logging import setup_logging
from saas_shared.telemetry import setup_worker_telemetry

from .config import settings


def _setup_sentry() -> None:
    """Initialise Sentry with the CeleryIntegration. No-op when DSN is unset.

    CeleryIntegration automatically:
    - Wraps every task execution in a Sentry transaction (visible in Performance).
    - Captures exceptions that propagate out of a task (including those raised
      after max_retries is exceeded).
    - Tags each event with the task name, task id, and queue.

    This function is called:
    1. After setup_logging at import — covers the Beat scheduler / parent process.
    2. In worker_process_init — re-initialises the SDK in every forked Celery
       worker process so file descriptors are not shared across fork().
    """
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", settings.service_name)


setup_logging(service_name=settings.service_name, log_level=settings.log_level)
_setup_sentry()

celery_app = Celery(
    settings.service_name,
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.webhook_tasks",
        "app.tasks.cleanup_tasks",
    ],
)

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
    _setup_sentry()
