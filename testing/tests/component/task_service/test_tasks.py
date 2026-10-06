"""Characterised task-service behaviour. The flow returns the response; the test decides."""

from uuid import uuid4

from saas_testkit.flows import TaskLifecycle


async def test_create_task_returns_created_status(lifecycle: TaskLifecycle) -> None:
    response = await lifecycle.create()

    assert response.status == 201


async def test_unknown_task_returns_404(lifecycle: TaskLifecycle) -> None:
    response = await lifecycle.get(uuid4())

    assert response.status == 404
    assert response.error is not None
    assert response.error.detail == "Task not found"
