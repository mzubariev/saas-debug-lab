from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from saas_shared.logging import setup_logging

from .config import settings


celery_app = Celery(
    settings.service_name,
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.webhooks",
        "app.tasks.cleanup",
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
            "task": "app.tasks.webhooks.retry_failed_webhooks",
            "schedule": 60.0,
        },
        "cleanup-old-tasks-daily": {
            "task": "app.tasks.cleanup.cleanup_old_tasks",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)


@worker_process_init.connect
def init_worker_process(**kwargs) -> None:
    """Configure structlog in each forked worker process."""
    setup_logging(settings.log_level, settings.service_name)
