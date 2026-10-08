"""Auth chain through the gateway: login, create a task, read it back."""

from saas_testkit.domain import TaskStatus
from saas_testkit.flows import AuthFlow, TaskLifecycle


async def test_login_creates_a_task_and_reads_it(auth: AuthFlow, lifecycle: TaskLifecycle) -> None:
    logged_in = await auth.login(username="admin", password="admin123")
    assert logged_in.status == 200
    assert logged_in.data is not None

    created = await lifecycle.create()
    assert created.status == 201
    assert created.data is not None
    assert created.data.status == TaskStatus.created

    found = await lifecycle.get(created.data.id)
    assert found.status == 200
    assert found.data == created.data
