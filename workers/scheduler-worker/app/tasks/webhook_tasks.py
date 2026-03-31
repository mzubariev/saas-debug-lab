from opentelemetry import trace
from opentelemetry.trace import SpanKind
from structlog.contextvars import bound_contextvars

from saas_shared.tracing_env import is_otel_sdk_enabled

from ..core.celery import celery_app
from ..services import webhook_retry_service

_tracer = trace.get_tracer(__name__)


@celery_app.task(name="app.tasks.webhook_tasks.retry_failed_webhooks", bind=True)
def retry_failed_webhooks(self) -> dict:
    """Celery entrypoint — delegates to webhook DLQ service.

    Beat-scheduled runs are **not** linked to HTTP; explicit span names for Jaeger (Mode A).
    """
    with bound_contextvars(request_id=self.request.id, task="retry_failed_webhooks"):
        if is_otel_sdk_enabled():
            with _tracer.start_as_current_span(
                "celery.job.retry_failed_webhooks",
                kind=SpanKind.INTERNAL,
            ):
                return webhook_retry_service.process_dlq()
        return webhook_retry_service.process_dlq()
