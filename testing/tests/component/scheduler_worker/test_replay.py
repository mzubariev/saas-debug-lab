"""DLQ replay. Call ``retry_single_webhook``; do not drain Kafka."""

import importlib
import json
from types import ModuleType
from typing import cast
from uuid import uuid4

import httpx
import pytest
import respx

from saas_testkit.context import unique_title

_HTTP_ERRORS = [
    pytest.param(400, id="4xx"),
    pytest.param(500, id="5xx"),
]


def _post(outcome: httpx.Response | Exception) -> tuple[tuple[httpx.Request, ...], dict[str, str]]:
    settings = importlib.import_module("app.core.config").settings
    loaded = importlib.import_module("app.tasks.webhook_tasks")
    payload = {
        "id": str(uuid4()),
        "title": unique_title("replay"),
        "status": "created",
    }
    with respx.mock(assert_all_called=False) as router:
        route = router.post(cast(str, settings.webhook_url))
        if isinstance(outcome, Exception):
            route.mock(side_effect=outcome)
        else:
            route.mock(return_value=outcome)
        loaded.retry_single_webhook.apply(
            kwargs={
                "payload": payload,
                "event_type": "task.created",
                "task_id": payload["id"],
            }
        )
        return tuple(call.request for call in route.calls), payload


@pytest.mark.parametrize("status_code", _HTTP_ERRORS)
def test_replay_is_final_when_the_receiver_returns_an_http_error(
    worker_module: ModuleType,
    status_code: int,
) -> None:
    _ = worker_module
    requests, payload = _post(httpx.Response(status_code))

    assert len(requests) == 1
    assert "Idempotency-Key" not in requests[0].headers
    assert json.loads(requests[0].content) == payload


def test_replay_retries_when_the_request_fails(worker_module: ModuleType) -> None:
    _ = worker_module
    loaded = importlib.import_module("app.tasks.webhook_tasks")
    requests, payload = _post(httpx.RequestError("network down"))
    attempts = loaded.retry_single_webhook.max_retries + 1

    assert loaded.retry_single_webhook.max_retries == 5
    assert len(requests) == attempts
    assert ["Idempotency-Key" not in request.headers for request in requests] == [True] * attempts
    assert [json.loads(request.content) for request in requests] == [payload] * attempts


@pytest.mark.xfail(
    strict=True,
    reason="BUG-12: a 5xx replay is final; autoretry_for is only httpx.RequestError",
)
def test_replay_retries_when_the_receiver_returns_5xx(worker_module: ModuleType) -> None:
    _ = worker_module
    loaded = importlib.import_module("app.tasks.webhook_tasks")
    requests, _payload = _post(httpx.Response(500))

    assert len(requests) == loaded.retry_single_webhook.max_retries + 1
