import uuid

import sentry_sdk
import structlog
from fastapi import HTTPException
from redis.asyncio import Redis
from aiokafka import AIOKafkaProducer
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.task import Task, TaskStatus
from ..schemas.task import TaskOut
from ..repositories.task_repository import TaskRepository
from ..infrastructure.cache.client import cache_get, cache_set, cache_delete
from ..infrastructure.messaging.producer import publish_event

logger = structlog.get_logger()

_CACHE_TTL_LIST = 60    # seconds
_CACHE_TTL_SINGLE = 120  # seconds
_LIST_KEY = "tasks:list"


def _task_key(task_id: uuid.UUID) -> str:
    return f"tasks:{task_id}"


class TaskService:
    """Orchestrates the repository, cache, and Kafka producer.

    Routes call this service; the service never touches FastAPI primitives
    (Request, Response, HTTPException is the only exception — it's a
    framework-neutral way to signal HTTP-level errors upstream).
    """

    def __init__(self, db: AsyncSession, redis: Redis, kafka: AIOKafkaProducer) -> None:
        self._repo = TaskRepository(db)
        self._redis = redis
        self._kafka = kafka

    async def list_tasks(self) -> list[Task] | list:
        cached = await cache_get(self._redis, _LIST_KEY)
        if cached is not None:
            logger.info("cache_hit", key=_LIST_KEY, count=len(cached))
            return cached

        tasks = await self._repo.list_all()
        logger.info("tasks_listed", count=len(tasks), source="db")

        serialized = [TaskOut.model_validate(t).model_dump(mode="json") for t in tasks]
        await cache_set(self._redis, _LIST_KEY, serialized, ttl=_CACHE_TTL_LIST)

        return tasks

    async def get_task(self, task_id: uuid.UUID) -> Task | dict:
        key = _task_key(task_id)

        cached = await cache_get(self._redis, key)
        if cached is not None:
            logger.info("cache_hit", key=key, task_id=str(task_id))
            return cached

        task = await self._repo.get_by_id(task_id)
        if task is None:
            logger.warning("task_not_found", task_id=str(task_id))
            raise HTTPException(status_code=404, detail="Task not found")

        logger.info("task_fetched", task_id=str(task.id), status=task.status.value, source="db")
        serialized = TaskOut.model_validate(task).model_dump(mode="json")
        await cache_set(self._redis, key, serialized, ttl=_CACHE_TTL_SINGLE)

        return task

    async def create_task(self, title: str) -> Task:
        task = await self._repo.create(title)

        sentry_sdk.set_tag("task_id", str(task.id))
        sentry_sdk.set_extra("task_title", task.title)

        await publish_event(
            self._kafka,
            topic="task_created",
            payload={"id": str(task.id), "title": task.title, "status": task.status.value},
        )

        await cache_delete(self._redis, _LIST_KEY)

        logger.info("task_created", task_id=str(task.id), title=task.title)
        return task

    async def start_task(self, task_id: uuid.UUID) -> Task:
        sentry_sdk.set_tag("task_id", str(task_id))

        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status != TaskStatus.created:
            logger.warning(
                "invalid_task_transition",
                task_id=str(task_id),
                current_status=task.status.value,
                attempted_transition="start",
                expected_status="created",
            )
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
        task = await self._repo.save(task)

        await publish_event(
            self._kafka,
            topic="task_updated",
            payload={"id": str(task.id), "title": task.title, "status": task.status.value},
        )

        await cache_delete(self._redis, _LIST_KEY, _task_key(task_id))

        logger.info("task_started", task_id=str(task.id))
        return task

    async def complete_task(self, task_id: uuid.UUID) -> Task:
        sentry_sdk.set_tag("task_id", str(task_id))

        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status != TaskStatus.in_progress:
            logger.warning(
                "invalid_task_transition",
                task_id=str(task_id),
                current_status=task.status.value,
                attempted_transition="complete",
                expected_status="in_progress",
            )
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
        task = await self._repo.save(task)

        await publish_event(
            self._kafka,
            topic="task_updated",
            payload={"id": str(task.id), "title": task.title, "status": task.status.value},
        )

        await cache_delete(self._redis, _LIST_KEY, _task_key(task_id))

        logger.info("task_completed", task_id=str(task.id))
        return task
