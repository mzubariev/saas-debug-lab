import uuid

from fastapi import APIRouter, status

from ...dependencies import TaskServiceDep
from ...schemas.task import TaskCreate, TaskOut

router = APIRouter(prefix="/tasks")


@router.get("", response_model=list[TaskOut])
async def list_tasks(service: TaskServiceDep):
    return await service.list_tasks()


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    service: TaskServiceDep,
):
    return await service.create_task(payload.title)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    service: TaskServiceDep,
):
    return await service.get_task(task_id)


@router.patch("/{task_id}/start", response_model=TaskOut)
async def start_task(
    task_id: uuid.UUID,
    service: TaskServiceDep,
):
    return await service.start_task(task_id)


@router.patch("/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: uuid.UUID,
    service: TaskServiceDep,
):
    return await service.complete_task(task_id)
