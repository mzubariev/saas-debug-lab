"""Task steps in business language. Preconditions check; the test checks the rest."""

from collections.abc import Callable
from uuid import UUID

from saas_testkit.adapters.http.tasks import HttpTaskApi
from saas_testkit.adapters.kafka.reader import KafkaEventReader
from saas_testkit.domain.events import Envelope
from saas_testkit.domain.http import ApiResponse
from saas_testkit.domain.tasks import Task
from saas_testkit.factories.payloads import TaskCreateFactory
from saas_testkit.polling import eventually

_TASK_CREATED = "task.created"


class TaskLifecycle:
    def __init__(self, tasks: HttpTaskApi, events: KafkaEventReader | None = None) -> None:
        self._tasks = tasks
        self._events = events

    async def create(self, *, title: str | None = None) -> ApiResponse[Task]:
        """Behaviour under test: the caller asserts on the response."""
        body = TaskCreateFactory.build() if title is None else TaskCreateFactory.build(title=title)
        return await self._tasks.create(body)

    async def new_task(self, *, title: str | None = None) -> Task:
        """Precondition. Raises if the service does not return 201."""
        response = await self.create(title=title)
        if response.status != 201 or response.data is None:
            raise AssertionError(f"expected 201, got {response.status}: {_detail(response)}")
        return response.data

    async def get(self, task_id: UUID) -> ApiResponse[Task]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._tasks.get(task_id)

    async def start(self, task: Task) -> ApiResponse[Task]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._tasks.start(task.id)

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
        if self._events is None:
            raise RuntimeError("TaskLifecycle has no KafkaEventReader")
        task_id = str(task.id)
        reader = self._events
        return await eventually(
            lambda: reader.wait_for("task_created", match=_task_id(task_id), timeout=0.2),
            timeout=10,
            interval=0,
            message=f"no {_TASK_CREATED} for {task_id}",
        )


def _detail(response: ApiResponse[Task]) -> object:
    if response.error is None:
        return None
    return response.error.detail


def _task_id(task_id: str) -> Callable[[Envelope], bool]:
    def match(envelope: Envelope) -> bool:
        return envelope.event_type == _TASK_CREATED and envelope.payload.get("id") == task_id

    return match
