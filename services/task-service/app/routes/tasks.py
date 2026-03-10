from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..dependencies import get_db
from ..models.task import Task
from ..schemas.task import TaskCreate, TaskOut


router = APIRouter(prefix="/tasks")


@router.get("", response_model=list[TaskOut])
async def list_tasks(db: AsyncSession = Depends(get_db)):

    result = await db.execute(select(Task))

    tasks = result.scalars().all()

    return tasks


@router.post("", response_model=TaskOut)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db)
):

    task = Task(title=payload.title)

    db.add(task)

    await db.commit()
    await db.refresh(task)

    return task