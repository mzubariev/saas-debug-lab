import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.task import Task


class TaskRepository:
    """All SQLAlchemy access for the tasks table lives here.

    Routes and the service layer never import sqlalchemy directly.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_all(self) -> list[Task]:
        result = await self._db.execute(select(Task).order_by(Task.created_at.desc()))
        return list(result.scalars().all())

    async def get_by_id(self, task_id: uuid.UUID) -> Task | None:
        result = await self._db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def create(self, title: str) -> Task:
        task = Task(title=title)
        self._db.add(task)
        await self._db.commit()
        await self._db.refresh(task)
        return task

    async def save(self, task: Task) -> Task:
        """Persist an in-memory change (status update etc.) and refresh the instance."""
        await self._db.commit()
        await self._db.refresh(task)
        return task
