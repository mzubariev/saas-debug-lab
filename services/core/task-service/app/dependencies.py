from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .infrastructure.db.session import SessionLocal
from .services.task_service import TaskService


async def get_db():
    async with SessionLocal() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_task_service(request: Request, db: DbSession) -> TaskService:
    return TaskService(
        db=db,
        redis=request.app.state.redis,
        kafka=request.app.state.kafka,
    )


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
