"""The created task body matches the consumer model."""

from saas_testkit.domain import Task
from saas_testkit.flows import TaskLifecycle


async def test_created_task_matches_consumer_model(lifecycle: TaskLifecycle) -> None:
    response = await lifecycle.create()

    assert response.status == 201
    Task.model_validate(response.document)
