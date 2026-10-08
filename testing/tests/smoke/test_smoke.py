"""Post-deploy gate. One failure blocks the pipeline."""

import pytest

from saas_testkit.flows import AuthFlow, TaskLifecycle


@pytest.mark.parametrize(
    "service_health",
    ["/health", "/external/health"],
    ids=["gateway", "simulator"],
    indirect=True,
)
async def test_health_through_the_edge_is_ok(service_health: tuple[int, str | None]) -> None:
    status_code, body_status = service_health

    assert status_code == 200
    assert body_status == "ok"


@pytest.mark.parametrize(
    ("username", "password", "role"),
    [("admin", "admin123", "admin"), ("user", "user123", "user")],
    ids=["admin", "user"],
)
async def test_login_for_a_seeded_role_returns_a_token(
    auth: AuthFlow, username: str, password: str, role: str
) -> None:
    response = await auth.login(username=username, password=password)

    assert response.status == 200
    assert response.data is not None
    assert response.data.token_type == "bearer"
    me = await auth.me(response.data.access_token)
    assert me.status == 200
    assert me.data is not None
    assert me.data.username == username
    assert me.data.role == role


async def test_created_task_is_readable(lifecycle: TaskLifecycle) -> None:
    created = await lifecycle.create()

    assert created.status == 201
    assert created.data is not None
    read = await lifecycle.get(created.data.id)
    assert read.status == 200
    assert read.data is not None
    assert read.data.id == created.data.id
    assert read.data.title == created.data.title


async def test_metrics_are_reachable(metrics_status: int) -> None:
    assert metrics_status == 200


async def test_frontend_returns_ok(frontend_status: int) -> None:
    assert frontend_status == 200
