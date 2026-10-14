"""Cleanup of completed tasks. Call ``cleanup_old_tasks``; do not start a worker."""

import importlib
from datetime import UTC, datetime, timedelta
from types import ModuleType
from uuid import UUID

import pytest
from saas_shared.models import Task as TaskRow
from saas_shared.models import TaskStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saas_testkit.factories import Rows


def _cleanup(monkeypatch: pytest.MonkeyPatch, minutes: int) -> dict[str, object]:
    settings = importlib.import_module("app.core.config").settings
    monkeypatch.setattr(settings, "cleanup_completed_tasks_minutes", minutes)
    loaded = importlib.import_module("app.tasks.cleanup_tasks")
    outcome = loaded.cleanup_old_tasks.apply()
    body = outcome.result
    assert isinstance(body, dict)
    return body


async def _present(
    session_maker: async_sessionmaker[AsyncSession],
    task_id: UUID,
) -> bool:
    async with session_maker() as session:
        return await session.get(TaskRow, task_id) is not None


@pytest.mark.clean_db
async def test_cleanup_deletes_only_completed_tasks_older_than_the_threshold(
    worker_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    rows: Rows,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _ = worker_module
    minutes = 5
    now = datetime.now(UTC)
    threshold = timedelta(minutes=minutes)
    inside = await rows.task.create_async(
        status=TaskStatus.completed,
        updated_at=now - threshold - timedelta(seconds=1),
    )
    outside = await rows.task.create_async(
        status=TaskStatus.completed,
        updated_at=now - threshold + timedelta(seconds=1),
    )
    started = await rows.task.create_async(
        status=TaskStatus.in_progress,
        updated_at=now - threshold - timedelta(hours=1),
    )
    created = await rows.task.create_async(
        status=TaskStatus.created,
        updated_at=now - threshold - timedelta(hours=1),
    )

    assert _cleanup(monkeypatch, minutes) == {"deleted": 1}
    assert await _present(session_maker, inside.id) is False
    assert await _present(session_maker, outside.id) is True
    assert await _present(session_maker, started.id) is True
    assert await _present(session_maker, created.id) is True


@pytest.mark.clean_db
async def test_cleanup_deletes_nothing_when_the_threshold_is_zero(
    worker_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    rows: Rows,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _ = worker_module
    old = await rows.task.create_async(
        status=TaskStatus.completed,
        updated_at=datetime.now(UTC) - timedelta(days=1),
    )

    assert _cleanup(monkeypatch, 0) == {"deleted": 0, "skipped": True}
    assert await _present(session_maker, old.id) is True
