from datetime import datetime, timedelta, timezone

import sentry_sdk
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ..celery import celery_app
from ..config import settings


logger = structlog.get_logger()

# Lazy singleton — avoids a DB connection at import time (which would happen
# when Celery discovers tasks). Created on first task execution instead.
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return _engine


@celery_app.task(
    name="app.tasks.cleanup.cleanup_old_tasks",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_old_tasks(self) -> dict:
    """
    Delete completed tasks whose updated_at is older than
    CLEANUP_COMPLETED_TASKS_DAYS days.

    Retries up to 3 times (60-second delay) on transient DB errors.
    Set CLEANUP_COMPLETED_TASKS_DAYS=0 to disable deletion entirely.
    """
    if settings.cleanup_completed_tasks_days == 0:
        logger.info("cleanup_skipped", reason="CLEANUP_COMPLETED_TASKS_DAYS=0")
        return {"deleted": 0, "skipped": True}

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.cleanup_completed_tasks_days
    )

    try:
        with Session(_get_engine()) as db:
            result = db.execute(
                text(
                    "DELETE FROM tasks "
                    "WHERE status = 'completed' AND updated_at < :cutoff"
                ),
                {"cutoff": cutoff},
            )
            db.commit()
            deleted = result.rowcount

        logger.info(
            "tasks_cleaned_up",
            deleted=deleted,
            cutoff=cutoff.isoformat(),
            older_than_days=settings.cleanup_completed_tasks_days,
        )
        return {"deleted": deleted}

    except Exception as exc:
        logger.error("cleanup_failed", error=str(exc))
        # Set rich context on the current scope so that if all retries are
        # exhausted and CeleryIntegration captures the final exception, the
        # Sentry event already carries the cutoff date and retry count.
        sentry_sdk.set_tag("task", "cleanup_old_tasks")
        sentry_sdk.set_extra("cutoff_iso", cutoff.isoformat())
        sentry_sdk.set_extra("older_than_days", settings.cleanup_completed_tasks_days)
        sentry_sdk.set_extra("retry_attempt", self.request.retries)
        raise self.retry(exc=exc)
