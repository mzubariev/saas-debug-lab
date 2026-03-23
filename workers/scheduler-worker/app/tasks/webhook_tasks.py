from ..core.celery import celery_app
from ..services import webhook_retry_service


@celery_app.task(name="app.tasks.webhook_tasks.retry_failed_webhooks")
def retry_failed_webhooks() -> dict:
    """Celery entrypoint — delegates to webhook DLQ service."""
    return webhook_retry_service.process_dlq()
