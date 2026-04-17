from contextlib import nullcontext

import httpx
import sentry_sdk
import structlog
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from structlog.contextvars import bound_contextvars

from saas_shared.prometheus_metrics import dlq_retry_result_total
from saas_shared.tracing_env import is_otel_sdk_enabled

from ..core.celery import celery_app
from ..core.config import settings
from ..infrastructure.http.client import post_json_sync
from ..services import webhook_retry_service

_tracer = trace.get_tracer(__name__)


@celery_app.task(name="app.tasks.webhook_tasks.retry_failed_webhooks", bind=True)
def retry_failed_webhooks(self) -> dict:
    """Beat-scheduled fan-out producer — reads the webhook DLQ and dispatches
    one ``retry_single_webhook`` Celery task per message.

    Runs every 60 s. Caps at MAX_MESSAGES / MAX_RUNTIME so it always returns
    before the next Beat tick. Actual HTTP delivery happens in worker subprocesses.
    """
    with bound_contextvars(request_id=self.request.id, task="retry_failed_webhooks"):
        if is_otel_sdk_enabled():
            with _tracer.start_as_current_span(
                "celery.job.retry_failed_webhooks",
                kind=SpanKind.INTERNAL,
            ):
                return webhook_retry_service.process_dlq()
        return webhook_retry_service.process_dlq()


@celery_app.task(
    bind=True,
    name="app.tasks.webhook_tasks.retry_single_webhook",
    # Retry on network / timeout errors with exponential back-off.
    # httpx.HTTPStatusError is NOT in autoretry_for — a 4xx/5xx response from the
    # target endpoint is a permanent rejection; retrying would not help.
    autoretry_for=(httpx.RequestError,),
    retry_backoff=True,
    retry_backoff_max=300,      # cap back-off at 5 min; total window ~20 min across 10 retries
    max_retries=10,
    # Keep the message unacked until the task succeeds (or exhausts retries).
    # If the worker process crashes mid-execution the broker re-delivers the task.
    acks_late=True,
)
def retry_single_webhook(
    self,
    payload: dict,
    event_type: str,
    task_id: str | None,
) -> dict:
    """Deliver a single DLQ message to the webhook endpoint.

    Dispatched by ``retry_failed_webhooks`` (1 message = 1 task), enabling
    per-message retries, back-off, and visible queue depth in Celery / Redis.

    Failure modes and their observability:
    - httpx.RequestError  → auto-retried (up to 5×, exp back-off).
                            After max retries: task → FAILURE,
                            celery_tasks_total{status="failure"} increments.
    - httpx.HTTPStatusError → permanent failure (endpoint rejected the payload),
                              task → FAILURE immediately,
                              dlq_retry_result_total{result="failure"} increments.
    - Worker crash           → acks_late re-delivers the task to another worker.

    To simulate incidents:
    - Stop external-service-simulator → RequestError retries pile up, queue grows,
      celery_tasks_total{status="failure"} rises.
    - Return 500 from external-service-simulator → HTTPStatusError, immediate FAILURE.
    - Reduce --concurrency → queue depth and task duration p95 rise.
    """
    log = structlog.get_logger().bind(
        celery_task_id=self.request.id,
        dlq_task_id=task_id,
        event_type=event_type,
        attempt=self.request.retries + 1,
        max_attempts=self.max_retries + 1,
    )

    span_cm = (
        _tracer.start_as_current_span(
            "celery.dlq.retry_single_webhook",
            kind=SpanKind.INTERNAL,
            attributes={
                "dlq.task_id": str(task_id),
                "dlq.event_type": str(event_type),
                "dlq.attempt": self.request.retries + 1,
            },
        )
        if is_otel_sdk_enabled()
        else nullcontext()
    )

    with span_cm:
        try:
            resp = post_json_sync(
                settings.webhook_url,
                payload,
                timeout=settings.webhook_timeout,
            )
            resp.raise_for_status()

            dlq_retry_result_total.labels(result="success").inc()
            log.info("dlq_webhook_delivered", status_code=resp.status_code)
            return {"status": "delivered", "task_id": task_id}

        except httpx.HTTPStatusError as exc:
            # Endpoint rejected the payload — permanent failure, do not retry.
            dlq_retry_result_total.labels(result="failure").inc()
            log.warning(
                "dlq_webhook_rejected_permanently",
                status_code=exc.response.status_code,
                error=str(exc),
            )
            sentry_sdk.add_breadcrumb(
                category="dlq",
                message="DLQ webhook permanently rejected by endpoint",
                level="error",
                data={
                    "task_id": task_id,
                    "status_code": exc.response.status_code,
                    "webhook_url": settings.webhook_url,
                },
            )
            raise  # Celery marks task FAILURE → celery_tasks_total{status="failure"}++

        except httpx.RequestError as exc:
            # Connection / timeout — autoretry handles back-off and re-enqueue.
            # Only count as a final failure on the last attempt so the metric
            # reflects "messages permanently lost", not "retry storm volume".
            if self.request.retries >= self.max_retries:
                dlq_retry_result_total.labels(result="failure").inc()
            log.warning(
                "dlq_webhook_attempt_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                attempt=self.request.retries + 1,
                is_final=self.request.retries >= self.max_retries,
            )
            raise  # triggers autoretry; on MaxRetriesExceeded → task FAILURE
