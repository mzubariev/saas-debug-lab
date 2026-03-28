import sentry_sdk
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from saas_shared.tracing_env import is_otel_sdk_enabled

from ..core.celery import celery_app
from ..services import cleanup_service

_tracer = trace.get_tracer(__name__)


@celery_app.task(
    name="app.tasks.cleanup_tasks.cleanup_old_tasks",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_old_tasks(self) -> dict:
    """Celery entrypoint — delegates to cleanup service; retries on DB errors."""
    try:
        if is_otel_sdk_enabled():
            with _tracer.start_as_current_span(
                "celery.job.cleanup_old_tasks",
                kind=SpanKind.INTERNAL,
            ):
                return cleanup_service.cleanup()
        return cleanup_service.cleanup()
    except Exception as exc:
        sentry_sdk.set_tag("task", "cleanup_old_tasks")
        sentry_sdk.set_extra("retry_attempt", self.request.retries)
        raise self.retry(exc=exc)
