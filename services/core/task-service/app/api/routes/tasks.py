import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db
from ...schemas.task import TaskCreate, TaskOut
from ...services.task_service import TaskService

router = APIRouter(prefix="/tasks")


def get_task_service(request: Request, db: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(
        db=db,
        redis=request.app.state.redis,
        kafka=request.app.state.kafka,
    )


@router.get("", response_model=list[TaskOut])
async def list_tasks(service: TaskService = Depends(get_task_service)):
    return await service.list_tasks()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    service: TaskService = Depends(get_task_service),
):
    return await service.create_task(payload.title)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(get_task_service),
):
    return await service.get_task(task_id)


@router.patch("/{task_id}/start", response_model=TaskOut)
async def start_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(get_task_service),
):
    return await service.start_task(task_id)


@router.patch("/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(get_task_service),
):
    return await service.complete_task(task_id)
