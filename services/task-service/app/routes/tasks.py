import structlog

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..dependencies import get_db
from ..models.task import Task
from ..schemas.task import TaskCreate, TaskOut
from ..kafka import publish_event


router = APIRouter(prefix="/tasks")

logger = structlog.get_logger()


@router.get("", response_model=list[TaskOut])
async def list_tasks(db: AsyncSession = Depends(get_db)):

    result = await db.execute(select(Task))

    return result.scalars().all()


@router.post("", response_model=TaskOut)
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
        payload={"id": task.id, "title": task.title},
    )

    logger.info("task_created", task_id=task.id, title=task.title)

    return task