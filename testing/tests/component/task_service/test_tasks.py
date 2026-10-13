"""Characterised task-service behaviour. The flow returns the response; the test decides."""

import asyncio
import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pytest_mock import MockerFixture

from saas_testkit.context import unique_title
from saas_testkit.domain import Task, TaskCreatedPayload, TaskStatus, TaskUpdatedPayload
from saas_testkit.flows import TaskLifecycle

_TITLE_LIMIT = 255
_OVERSIZE = 10_000
_HTTP_STATUS_500 = re.compile(r'http_requests_total\{[^}]*status="500"')


async def test_create_task_returns_created_status(lifecycle: TaskLifecycle) -> None:
    response = await lifecycle.create()

    assert response.status == 201
    assert response.data is not None
    assert response.data.status == TaskStatus.created


async def test_create_task_publishes_task_created(lifecycle: TaskLifecycle) -> None:
    task = await lifecycle.new_task()

    event = await lifecycle.task_created_event(task)
    payload = TaskCreatedPayload.model_validate(event.payload)
    assert payload.id == task.id
    assert payload.title == task.title
    assert payload.status == TaskStatus.created


@pytest.mark.parametrize(
    "title",
    [
        pytest.param("", id="empty"),
        pytest.param("x" * (_TITLE_LIMIT + 1), id="over-limit"),
        pytest.param("x" * _OVERSIZE, id="oversize"),
        pytest.param(1, id="wrong-type"),
    ],
)
async def test_create_rejects_a_bad_title(lifecycle: TaskLifecycle, title: object) -> None:
    response = await lifecycle.submit_title(title)

    assert response.status == 422


async def test_create_accepts_a_title_at_the_length_limit(lifecycle: TaskLifecycle) -> None:
    response = await lifecycle.submit_title("x" * _TITLE_LIMIT)

    assert response.status == 201


async def test_get_returns_the_task(lifecycle: TaskLifecycle) -> None:
    task = await lifecycle.new_task()

    response = await lifecycle.get(task.id)

    assert response.status == 200
    assert response.data == task


async def test_unknown_task_returns_404(lifecycle: TaskLifecycle) -> None:
    response = await lifecycle.get(uuid4())

    assert response.status == 404
    assert response.error is not None
    assert response.error.detail == "Task not found"


async def test_get_rejects_a_bad_id(lifecycle: TaskLifecycle) -> None:
    response = await lifecycle.get("not-a-uuid")

    assert response.status == 422


@pytest.mark.parametrize(
    ("status", "action", "code", "detail", "result"),
    [
        pytest.param(
            TaskStatus.created, "start", 200, None, TaskStatus.in_progress, id="start-created"
        ),
        pytest.param(
            TaskStatus.in_progress,
            "complete",
            200,
            None,
            TaskStatus.completed,
            id="complete-in-progress",
        ),
        pytest.param(
            TaskStatus.created,
            "complete",
            409,
            "Cannot complete task in status 'created'. Expected 'in_progress'.",
            None,
            id="complete-created",
        ),
        pytest.param(
            TaskStatus.in_progress,
            "start",
            409,
            "Cannot start task in status 'in_progress'. Expected 'created'.",
            None,
            id="start-in-progress",
        ),
        pytest.param(
            TaskStatus.completed,
            "start",
            409,
            "Cannot start task in status 'completed'. Expected 'created'.",
            None,
            id="start-completed",
        ),
        pytest.param(
            TaskStatus.completed,
            "complete",
            409,
            "Cannot complete task in status 'completed'. Expected 'in_progress'.",
            None,
            id="complete-completed",
        ),
    ],
)
async def test_task_transition(
    lifecycle: TaskLifecycle,
    status: TaskStatus,
    action: str,
    code: int,
    detail: str | None,
    result: TaskStatus | None,
) -> None:
    task = await lifecycle.at_status(status)

    response = await lifecycle.move(action, task)

    assert response.status == code
    if code == 409:
        assert response.error is not None
        assert response.error.detail == detail
        fresh = await lifecycle.get(task.id)
        assert fresh.data is not None
        assert fresh.data.status == status
        return
    assert response.data is not None
    assert response.data.status == result
    event = await lifecycle.task_updated_event(response.data)
    payload = TaskUpdatedPayload.model_validate(event.payload)
    assert payload.id == task.id
    assert payload.title == task.title
    assert payload.status == result


@pytest.mark.parametrize("action", ["start", "complete"])
async def test_transition_unknown_task_returns_404(lifecycle: TaskLifecycle, action: str) -> None:
    response = await lifecycle.move_missing(action)

    assert response.status == 404
    assert response.error is not None
    assert response.error.detail == "Task not found"


async def test_second_get_is_served_from_redis(lifecycle: TaskLifecycle) -> None:
    task = await lifecycle.new_task()
    first = await lifecycle.get(task.id)
    assert first.data is not None
    assert first.data.title == task.title
    stamped = unique_title("cached")

    await lifecycle.replace_cached_title(task, stamped)
    second = await lifecycle.get(task.id)

    assert second.status == 200
    assert second.data is not None
    assert second.data.id == task.id
    assert second.data.title == stamped


@pytest.mark.parametrize("action", ["start", "complete"])
async def test_transition_invalidates_the_cached_task(
    lifecycle: TaskLifecycle, action: str
) -> None:
    status = TaskStatus.created if action == "start" else TaskStatus.in_progress
    task = await lifecycle.at_status(status)
    assert (await lifecycle.get(task.id)).status == 200
    await lifecycle.replace_cached_title(task, unique_title("stale"))

    moved = await lifecycle.move(action, task)
    fresh = await lifecycle.get(task.id)

    assert moved.status == 200
    assert fresh.data is not None
    assert fresh.data.title == task.title
    assert fresh.data.id == task.id


async def test_create_invalidates_the_list_cache(lifecycle: TaskLifecycle) -> None:
    now = datetime.now(UTC)
    sentinel = Task(
        id=uuid4(),
        title=unique_title("list-cache"),
        status=TaskStatus.created,
        created_at=now,
        updated_at=now,
    )
    await lifecycle.replace_cached_list((sentinel,))
    cached = await lifecycle.list_tasks()
    assert cached.data is not None
    assert any(item.id == sentinel.id for item in cached.data)

    created = await lifecycle.new_task()
    fresh = await lifecycle.list_tasks()

    assert fresh.data is not None
    ids = {item.id for item in fresh.data}
    assert created.id in ids
    assert sentinel.id not in ids


async def test_get_reads_the_database_when_redis_is_down(
    lifecycle: TaskLifecycle,
    service_app: FastAPI,
    mocker: MockerFixture,
) -> None:
    task = await lifecycle.new_task()
    assert (await lifecycle.get(task.id)).status == 200
    await lifecycle.replace_cached_title(task, unique_title("cached"))
    mocker.patch.object(
        service_app.state.redis,
        "get",
        autospec=True,
        side_effect=ConnectionError("redis down"),
    )

    response = await lifecycle.get(task.id)

    assert response.status == 200
    assert response.data is not None
    assert response.data.title == task.title


async def test_create_publish_failure_is_a_logged_server_error(
    lifecycle: TaskLifecycle,
    client: httpx.AsyncClient,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    mocker.patch(
        "app.services.task_service.publish_event",
        autospec=True,
        side_effect=RuntimeError("kafka down"),
    )
    capfd.readouterr()

    response = await lifecycle.create(title=unique_title("kafka-error"))
    metrics = await client.get("/metrics")
    captured = capfd.readouterr()
    error_log = "\n".join(
        line
        for line in f"{captured.out}\n{captured.err}".splitlines()
        if "unhandled_exception" in line
    )

    assert response.status == 500
    assert _HTTP_STATUS_500.search(metrics.text)
    assert "request_id" in error_log


async def test_lifespan_closes_redis(service_app: FastAPI, mocker: MockerFixture) -> None:
    app_engine = mocker.Mock()
    app_engine.dispose = AsyncMock()
    mocker.patch("app.main.engine", app_engine)
    mocker.patch("app.main.start_kafka", new_callable=AsyncMock)
    mocker.patch("app.main.stop_kafka", new_callable=AsyncMock)
    mocker.patch("app.main.start_redis", new_callable=AsyncMock)
    stop_redis = mocker.patch("app.main.stop_redis", new_callable=AsyncMock)

    async with service_app.router.lifespan_context(service_app):
        pass

    stop_redis.assert_awaited_once_with(service_app)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-3: Kafka failure commits the task and returns 500 without deleting tasks:list",
)
async def test_create_publish_failure_stores_nothing(
    lifecycle: TaskLifecycle, mocker: MockerFixture
) -> None:
    mocker.patch(
        "app.services.task_service.publish_event",
        autospec=True,
        side_effect=RuntimeError("kafka down"),
    )
    title = unique_title("kafka-create")

    response = await lifecycle.create(title=title)

    if response.status == 201:
        assert response.data is not None
        event = await lifecycle.task_created_event(response.data)
        assert TaskCreatedPayload.model_validate(event.payload).title == title
        return
    await lifecycle.drop_cached_list()
    listed = await lifecycle.list_tasks()
    assert listed.data is not None
    assert all(item.title != title for item in listed.data)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-3: Kafka failure commits the transition and leaves the item cache",
)
async def test_start_publish_failure_keeps_the_previous_status(
    lifecycle: TaskLifecycle, mocker: MockerFixture
) -> None:
    task = await lifecycle.new_task()
    assert (await lifecycle.get(task.id)).status == 200
    mocker.patch(
        "app.services.task_service.publish_event",
        autospec=True,
        side_effect=RuntimeError("kafka down"),
    )

    response = await lifecycle.start(task)

    if response.status == 200:
        assert response.data is not None
        assert response.data.status == TaskStatus.in_progress
        event = await lifecycle.task_updated_event(response.data)
        assert TaskUpdatedPayload.model_validate(event.payload).status == TaskStatus.in_progress
        return
    await lifecycle.drop_cached_task(task.id)
    fresh = await lifecycle.get(task.id)
    assert fresh.data is not None
    assert fresh.data.status == TaskStatus.created


async def test_concurrent_start_succeeds_once(lifecycle: TaskLifecycle) -> None:
    task = await lifecycle.new_task()

    results = await asyncio.gather(*(lifecycle.start(task) for _ in range(8)))

    won = [result for result in results if result.status == 200]
    assert len(won) == 1
    assert all(result.status == 409 for result in results if result.status != 200)
