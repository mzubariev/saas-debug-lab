import uuid

import sentry_sdk
import structlog

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..dependencies import get_db
from ..models.task import Task, TaskStatus
from ..schemas.task import TaskCreate, TaskOut
from ..kafka import publish_event
from ..cache import cache_get, cache_set, cache_delete


router = APIRouter(prefix="/tasks")

logger = structlog.get_logger()

_CACHE_TTL_LIST   = 60    # seconds
_CACHE_TTL_SINGLE = 120   # seconds
_LIST_KEY = "tasks:list"


def _task_key(task_id: uuid.UUID) -> str:
    return f"tasks:{task_id}"


async def _get_task_or_404(task_id: uuid.UUID, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=list[TaskOut])
async def list_tasks(request: Request, db: AsyncSession = Depends(get_db)):
    redis = request.app.state.redis

    cached = await cache_get(redis, _LIST_KEY)
    if cached is not None:
        logger.debug("cache_hit", key=_LIST_KEY)
        return cached

    result = await db.execute(select(Task).order_by(Task.created_at.desc()))
    tasks = result.scalars().all()

    serialized = [TaskOut.model_validate(t).model_dump(mode="json") for t in tasks]
    await cache_set(redis, _LIST_KEY, serialized, ttl=_CACHE_TTL_LIST)

    return tasks


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    task = Task(title=payload.title)

    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Tag the Sentry scope so any exception raised after this point carries
    # the task ID — useful for correlating errors with specific records.
    sentry_sdk.set_tag("task_id", str(task.id))
    sentry_sdk.set_extra("task_title", task.title)

    await publish_event(
        request.app.state.kafka,
        topic="task_created",
        payload={"id": str(task.id), "title": task.title, "status": task.status.value},
    )

    await cache_delete(request.app.state.redis, _LIST_KEY)

    logger.info("task_created", task_id=str(task.id), title=task.title)

    return task


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    sentry_sdk.set_tag("task_id", str(task_id))

    redis = request.app.state.redis
    key = _task_key(task_id)

    cached = await cache_get(redis, key)
    if cached is not None:
        logger.debug("cache_hit", key=key)
        return cached

    task = await _get_task_or_404(task_id, db)

    serialized = TaskOut.model_validate(task).model_dump(mode="json")
    await cache_set(redis, key, serialized, ttl=_CACHE_TTL_SINGLE)

    return task


@router.patch("/{task_id}/start", response_model=TaskOut)
async def start_task(
    task_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    sentry_sdk.set_tag("task_id", str(task_id))

    task = await _get_task_or_404(task_id, db)

    if task.status != TaskStatus.created:
        # Capture a breadcrumb so the state at the time of rejection is visible
        # in Sentry without turning a normal 409 into a full error event.
        sentry_sdk.add_breadcrumb(
            category="task_lifecycle",
            message=f"Invalid transition: start() called on task in state '{task.status.value}'",
            level="warning",
            data={"task_id": str(task_id), "current_status": task.status.value},
        )
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start task in status '{task.status.value}'. Expected 'created'.",
        )

    task.status = TaskStatus.in_progress
    await db.commit()
    await db.refresh(task)

    await publish_event(
        request.app.state.kafka,
        topic="task_updated",
        payload={"id": str(task.id), "title": task.title, "status": task.status.value},
    )

    await cache_delete(request.app.state.redis, _LIST_KEY, _task_key(task_id))

    logger.info("task_started", task_id=str(task.id))

    return task


@router.patch("/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    sentry_sdk.set_tag("task_id", str(task_id))

    task = await _get_task_or_404(task_id, db)

    if task.status != TaskStatus.in_progress:
        sentry_sdk.add_breadcrumb(
            category="task_lifecycle",
            message=f"Invalid transition: complete() called on task in state '{task.status.value}'",
            level="warning",
            data={"task_id": str(task_id), "current_status": task.status.value},
        )
        raise HTTPException(
            status_code=409,
            detail=f"Cannot complete task in status '{task.status.value}'. Expected 'in_progress'.",
        )

    task.status = TaskStatus.completed
    await db.commit()
    await db.refresh(task)

    await publish_event(
        request.app.state.kafka,
        topic="task_updated",
        payload={"id": str(task.id), "title": task.title, "status": task.status.value},
    )

    await cache_delete(request.app.state.redis, _LIST_KEY, _task_key(task_id))

    logger.info("task_completed", task_id=str(task.id))

    return task
