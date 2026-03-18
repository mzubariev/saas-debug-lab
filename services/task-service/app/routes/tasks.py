import uuid

import structlog

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..dependencies import get_db
from ..models.task import Task, TaskStatus
from ..schemas.task import TaskCreate, TaskOut
from ..kafka import publish_event


router = APIRouter(prefix="/tasks")

logger = structlog.get_logger()

# Valid state transitions
_TRANSITIONS: dict[TaskStatus, TaskStatus] = {
    TaskStatus.created: TaskStatus.in_progress,
    TaskStatus.in_progress: TaskStatus.completed,
}


async def _get_task_or_404(task_id: uuid.UUID, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=list[TaskOut])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).order_by(Task.created_at.desc()))
    return result.scalars().all()


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

    await publish_event(
        request.app.state.kafka,
        topic="task_created",
        payload={"id": str(task.id), "title": task.title, "status": task.status.value},
    )

    logger.info("task_created", task_id=str(task.id), title=task.title)

    return task


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _get_task_or_404(task_id, db)


@router.patch("/{task_id}/start", response_model=TaskOut)
async def start_task(
    task_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task_or_404(task_id, db)

    if task.status != TaskStatus.created:
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

    logger.info("task_started", task_id=str(task.id))

    return task


@router.patch("/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task_or_404(task_id, db)

    if task.status != TaskStatus.in_progress:
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

    logger.info("task_completed", task_id=str(task.id))

    return task