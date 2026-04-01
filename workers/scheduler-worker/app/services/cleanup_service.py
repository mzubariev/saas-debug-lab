import time
from datetime import datetime, timedelta, timezone

import sentry_sdk
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..infrastructure.db.session import get_sync_engine

logger = structlog.get_logger()


def cleanup() -> dict:
    """
    Delete completed tasks whose updated_at is older than
    CLEANUP_COMPLETED_TASKS_MINUTES minutes.

    Caller (Celery task) handles retries on raised exceptions.
    Set CLEANUP_COMPLETED_TASKS_MINUTES=0 to disable deletion entirely.
    """
    t0 = time.perf_counter()
    logger.info("cleanup_job_started")

    if settings.cleanup_completed_tasks_minutes == 0:
        duration = time.perf_counter() - t0
        logger.info(
            "cleanup_skipped",
            reason="CLEANUP_COMPLETED_TASKS_MINUTES=0",
            duration_seconds=round(duration, 3),
        )
        return {"deleted": 0, "skipped": True}

    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.cleanup_completed_tasks_minutes
    )

    try:
        with Session(get_sync_engine(settings.postgres_dsn)) as db:
            result = db.execute(
                text(
                    "DELETE FROM tasks "
                    "WHERE status = 'completed' AND updated_at < :cutoff"
                ),
                {"cutoff": cutoff},
            )
            db.commit()
            deleted = result.rowcount

    except Exception as exc:
        logger.error(
            "cleanup_failed",
            error=str(exc),
            cutoff=cutoff.isoformat(),
            older_than_minutes=settings.cleanup_completed_tasks_minutes
        )
        sentry_sdk.set_tag("task", "cleanup_old_tasks")
        sentry_sdk.set_extra("cutoff_iso", cutoff.isoformat())
        sentry_sdk.set_extra("older_than_minutes", settings.cleanup_completed_tasks_minutes)
        raise

    duration = time.perf_counter() - t0
    logger.info(
        "cleanup_job_finished",
        deleted=deleted,
        cutoff=cutoff.isoformat(),
        older_than_minutes=settings.cleanup_completed_tasks_minutes,
        duration_seconds=round(duration, 3),
    )
    return {"deleted": deleted}
