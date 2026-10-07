"""Property test: allowed transitions succeed, illegal ones return 409 and change nothing."""

import asyncio
from collections.abc import Coroutine

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    rule,
    run_state_machine_as_test,
)

from saas_testkit.domain import Task, TaskStatus
from saas_testkit.flows import TaskLifecycle

_EXAMPLES = 5
_STEPS = 5


class TaskLifecycleMachine(RuleBasedStateMachine):
    def __init__(self, loop: asyncio.AbstractEventLoop, lifecycle: TaskLifecycle) -> None:
        super().__init__()
        self._loop = loop
        self._lifecycle = lifecycle
        self.task: Task | None = None
        self.status: TaskStatus | None = None

    def _run[T](self, step: Coroutine[object, object, T]) -> T:
        return asyncio.run_coroutine_threadsafe(step, self._loop).result()

    @initialize()
    def create(self) -> None:
        response = self._run(self._lifecycle.create())
        assert response.status == 201
        assert response.data is not None
        assert response.data.status == TaskStatus.created
        self.task = response.data
        self.status = TaskStatus.created

    @rule(action=st.sampled_from(["start", "complete"]))
    def transition(self, action: str) -> None:
        task = self.task
        status = self.status
        if task is None or status is None:
            return
        allowed = (action == "start" and status is TaskStatus.created) or (
            action == "complete" and status is TaskStatus.in_progress
        )
        response = self._run(self._lifecycle.move(action, task))
        if allowed:
            assert response.status == 200
            assert response.data is not None
            assert response.data.status is not status
            self.task = response.data
            self.status = response.data.status
            return
        assert response.status == 409
        current = self._run(self._lifecycle.get(task.id))
        assert current.data is not None
        assert current.data.status == status
        assert current.data.title == task.title

    @invariant()
    def service_status_matches(self) -> None:
        task = self.task
        status = self.status
        if task is None or status is None:
            return
        current = self._run(self._lifecycle.get(task.id))
        assert current.status == 200
        assert current.data is not None
        assert current.data.status == status


async def test_task_lifecycle_state_machine(lifecycle: TaskLifecycle) -> None:
    loop = asyncio.get_running_loop()

    def factory() -> TaskLifecycleMachine:
        return TaskLifecycleMachine(loop, lifecycle)

    await asyncio.to_thread(
        lambda: run_state_machine_as_test(
            factory,
            settings=settings(max_examples=_EXAMPLES, deadline=None, stateful_step_count=_STEPS),
        )
    )
