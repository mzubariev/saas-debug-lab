"""Task steps in business language. Preconditions check; the test checks the rest."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from saas_testkit.adapters.http.tasks import HttpTaskApi
from saas_testkit.adapters.kafka.reader import KafkaEventReader
from saas_testkit.adapters.redis.tasks import TaskCache
from saas_testkit.domain.events import Envelope
from saas_testkit.domain.http import ApiResponse
from saas_testkit.domain.tasks import Task, TaskStatus
from saas_testkit.factories.payloads import TaskCreateFactory
from saas_testkit.flows.webhook_delivery import WebhookDelivery


class TaskLifecycle:
    def __init__(
        self,
        tasks: HttpTaskApi,
        events: KafkaEventReader | None = None,
        cache: TaskCache | None = None,
    ) -> None:
        self._tasks = tasks
        self._events = events
        self._cache = cache

    async def create(self, *, title: str | None = None) -> ApiResponse[Task]:
        """Behaviour under test: the caller asserts on the response."""
        body = TaskCreateFactory.build() if title is None else TaskCreateFactory.build(title=title)
        return await self._tasks.create(body)

    async def submit_title(self, title: object) -> ApiResponse[Task]:
        """Behaviour under test: POST a title that may not be a string."""
        return await self._tasks.submit({"title": title})

    async def list_tasks(self) -> ApiResponse[tuple[Task, ...]]:
        """Behaviour under test: the caller asserts on its own ids."""
        return await self._tasks.list_tasks()

    async def new_task(self, *, title: str | None = None) -> Task:
        """Precondition. Raises if the service does not return 201."""
        response = await self.create(title=title)
        if response.status != 201 or response.data is None:
            raise AssertionError(f"expected 201, got {response.status}: {_detail(response)}")
        return response.data

    async def get(self, task_id: UUID | str) -> ApiResponse[Task]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._tasks.get(task_id)

    async def start(self, task: Task) -> ApiResponse[Task]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._tasks.start(task.id)

    async def complete(self, task: Task) -> ApiResponse[Task]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._tasks.complete(task.id)

    async def move(self, action: str, task: Task) -> ApiResponse[Task]:
        """`start` or `complete`. The caller asserts on the response."""
        if action == "start":
            return await self.start(task)
        if action == "complete":
            return await self.complete(task)
        raise ValueError(f"unknown transition {action}")

    async def move_missing(self, action: str) -> ApiResponse[Task]:
        """Start or complete a task id that was never created."""
        return await self.move(action, _missing_task())

    async def at_status(self, status: TaskStatus) -> Task:
        """Precondition: a task already in `status`. Consumes its own update events."""
        task = await self.new_task()
        if status is TaskStatus.created:
            return task
        started = await self.move("start", task)
        if started.status != 200 or started.data is None:
            raise AssertionError(f"expected start 200, got {started.status}: {_detail(started)}")
        await self.task_updated_event(started.data)
        if status is TaskStatus.in_progress:
            return started.data
        completed = await self.move("complete", started.data)
        if completed.status != 200 or completed.data is None:
            raise AssertionError(
                f"expected complete 200, got {completed.status}: {_detail(completed)}"
            )
        await self.task_updated_event(completed.data)
        return completed.data

    async def move_to_completed(self, task: Task) -> Task:
        """Precondition: start a `created` task, then complete it."""
        started = await self._tasks.start(task.id)
        if started.status != 200 or started.data is None:
            raise AssertionError(f"expected start 200, got {started.status}: {_detail(started)}")
        completed = await self._tasks.complete(started.data.id)
        if completed.status != 200 or completed.data is None:
            raise AssertionError(
                f"expected complete 200, got {completed.status}: {_detail(completed)}"
            )
        return completed.data

    async def task_created_event(self, task: Task) -> Envelope:
        """Delegates to `WebhookDelivery.task_created` (same topic, same id match)."""
        if self._events is None:
            raise RuntimeError("TaskLifecycle has no KafkaEventReader")
        return await WebhookDelivery(self._events).task_created(task.id)

    async def task_updated_event(self, task: Task) -> Envelope:
        """Delegates to `WebhookDelivery.task_updated`."""
        if self._events is None:
            raise RuntimeError("TaskLifecycle has no KafkaEventReader")
        return await WebhookDelivery(self._events).task_updated(task.id)

    async def replace_cached_title(self, task: Task, title: str) -> None:
        """Overwrite `tasks:{id}` so the next GET shows whether Redis served it."""
        cache = self._require_cache()
        cached = await cache.item(task.id)
        if cached is None:
            raise AssertionError(f"tasks:{task.id} is not cached")
        await cache.put_item(task.id, {**cached, "title": title})

    async def replace_cached_list(self, tasks: Sequence[Task]) -> None:
        """Overwrite `tasks:list` with these tasks."""
        body = [cast(dict[str, object], task.model_dump(mode="json")) for task in tasks]
        await self._require_cache().put_list(body)

    async def drop_cached_task(self, task_id: UUID) -> None:
        await self._require_cache().drop_item(task_id)

    async def drop_cached_list(self) -> None:
        await self._require_cache().drop_list()

    def _require_cache(self) -> TaskCache:
        if self._cache is None:
            raise RuntimeError("TaskLifecycle has no TaskCache")
        return self._cache


def _missing_task() -> Task:
    now = datetime.now(UTC)
    return Task(
        id=uuid4(),
        title="missing",
        status=TaskStatus.created,
        created_at=now,
        updated_at=now,
    )


def _detail(response: ApiResponse[Task]) -> object:
    if response.error is None:
        return None
    return response.error.detail
