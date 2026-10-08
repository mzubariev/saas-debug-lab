"""task-service events captured on Redpanda match the committed schema."""

from collections.abc import Callable

from saas_testkit.domain.events import Envelope
from saas_testkit.flows import TaskLifecycle


async def test_produced_task_created_matches_snapshot(
    lifecycle: TaskLifecycle,
    event_schema_errors: Callable[[str, Envelope], list[str]],
) -> None:
    task = await lifecycle.new_task()
    event = await lifecycle.task_created_event(task)

    assert event_schema_errors("task_created", event) == []


async def test_produced_task_updated_matches_snapshot(
    lifecycle: TaskLifecycle,
    event_schema_errors: Callable[[str, Envelope], list[str]],
) -> None:
    task = await lifecycle.new_task()
    started = await lifecycle.start(task)
    assert started.data is not None
    event = await lifecycle.task_updated_event(started.data)

    assert event_schema_errors("task_updated", event) == []
