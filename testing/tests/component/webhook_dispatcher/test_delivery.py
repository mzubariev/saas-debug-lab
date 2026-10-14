"""Dispatcher delivery. Call ``process_consumed_message``; do not start the consumer."""

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aiokafka import AIOKafkaProducer
from pytest_mock import MockerFixture
from saas_shared.kafka_envelope import encode_envelope_bytes
from structlog.testing import capture_logs

from saas_testkit.adapters.kafka import KafkaEventReader
from saas_testkit.domain import TaskCreatedPayload, WebhookDlqPayload
from saas_testkit.flows import WebhookDelivery

type Deliver = Callable[..., Awaitable[tuple[httpx.Request, ...]]]

_FAILURES = [
    pytest.param(httpx.Response(500), "500", id="5xx"),
    pytest.param(httpx.RequestError("network down"), "network down", id="request-error"),
]


async def test_webhook_posts_once_when_receiver_returns_2xx(
    deliver: Deliver,
    _task: tuple[TaskCreatedPayload, dict[str, object]],
    backoff: tuple[AsyncMock, MagicMock],
) -> None:
    task, body = _task
    sleep, _uniform = backoff

    requests = await deliver(
        value=encode_envelope_bytes("task.created", body),
        outcome=httpx.Response(200),
    )

    assert len(requests) == 1
    assert requests[0].headers["Idempotency-Key"] == str(task.id)
    assert json.loads(requests[0].content) == body
    sleep.assert_not_called()


@pytest.mark.parametrize(("outcome", "marker"), _FAILURES)
async def test_webhook_retries_with_backoff_when_delivery_fails(
    deliver: Deliver,
    _task: tuple[TaskCreatedPayload, dict[str, object]],
    _settings: tuple[str, int, float],
    backoff: tuple[AsyncMock, MagicMock],
    outcome: httpx.Response | Exception,
    marker: str,
) -> None:
    task, body = _task
    sleep, uniform = backoff
    _url, retries, base = _settings
    _ = marker

    requests = await deliver(
        value=encode_envelope_bytes("task.created", body),
        outcome=outcome,
    )

    assert retries == 3
    assert base == 1.0
    assert len(requests) == retries
    assert [request.headers["Idempotency-Key"] for request in requests] == [str(task.id)] * 3
    assert [json.loads(request.content) for request in requests] == [body, body, body]
    assert [item.args for item in uniform.call_args_list] == [(0, 0.1), (0, 0.2)]
    assert [item.args[0] for item in sleep.await_args_list] == [1.0 + 0.05, 2.0 + 0.15]


@pytest.mark.parametrize(("outcome", "marker"), _FAILURES)
async def test_webhook_dead_letters_when_retries_are_exhausted(
    deliver: Deliver,
    _task: tuple[TaskCreatedPayload, dict[str, object]],
    _settings: tuple[str, int, float],
    events: KafkaEventReader,
    outcome: httpx.Response | Exception,
    marker: str,
) -> None:
    task, body = _task
    _url, retries, _base = _settings

    await deliver(
        value=encode_envelope_bytes("task.created", body),
        outcome=outcome,
    )

    letter = await WebhookDelivery(events).dead_letter(task.id)
    dlq = WebhookDlqPayload.model_validate(letter.payload)
    assert letter.event_type == "webhook.dlq"
    assert letter.version == "v1"
    assert dlq.id == task.id
    assert dlq.title == task.title
    assert dlq.status == task.status
    assert dlq.attempts == retries
    assert marker in dlq.error
    assert datetime.fromisoformat(dlq.timestamp).tzinfo is not None


async def test_webhook_dead_letters_without_retry_when_receiver_returns_4xx(
    deliver: Deliver,
    _task: tuple[TaskCreatedPayload, dict[str, object]],
    events: KafkaEventReader,
    backoff: tuple[AsyncMock, MagicMock],
) -> None:
    task, body = _task
    sleep, uniform = backoff

    requests = await deliver(
        value=encode_envelope_bytes("task.created", body),
        outcome=httpx.Response(400),
    )

    assert len(requests) == 1
    assert requests[0].headers["Idempotency-Key"] == str(task.id)
    sleep.assert_not_called()
    uniform.assert_not_called()

    letter = await WebhookDelivery(events).dead_letter(task.id)
    dlq = WebhookDlqPayload.model_validate(letter.payload)
    assert letter.event_type == "webhook.dlq"
    assert dlq.id == task.id
    assert dlq.title == task.title
    assert dlq.status == task.status
    assert dlq.attempts == 1
    assert "400" in dlq.error
    assert datetime.fromisoformat(dlq.timestamp).tzinfo is not None


async def test_webhook_posts_raw_json_when_message_is_legacy(
    deliver: Deliver,
    _task: tuple[TaskCreatedPayload, dict[str, object]],
    backoff: tuple[AsyncMock, MagicMock],
) -> None:
    task, body = _task
    sleep, _uniform = backoff

    requests = await deliver(
        value=json.dumps(body).encode(),
        outcome=httpx.Response(200),
    )

    assert len(requests) == 1
    assert requests[0].headers["Idempotency-Key"] == str(task.id)
    assert json.loads(requests[0].content) == body
    sleep.assert_not_called()


@pytest.mark.parametrize(
    "raw",
    [pytest.param(b"{", id="invalid-json"), pytest.param(b"\xff", id="not-utf8")],
)
async def test_consumer_returns_when_message_is_poison(
    deliver: Deliver,
    kafka_producer: AIOKafkaProducer,
    mocker: MockerFixture,
    raw: bytes,
) -> None:
    produced = mocker.spy(kafka_producer, "send_and_wait")

    requests = await deliver(value=raw, outcome=httpx.Response(200))

    assert requests == ()
    produced.assert_not_called()


async def test_consumer_logs_and_returns_when_dlq_produce_fails(
    deliver: Deliver,
    _task: tuple[TaskCreatedPayload, dict[str, object]],
    mocker: MockerFixture,
    backoff: tuple[AsyncMock, MagicMock],
) -> None:
    task, body = _task
    sleep, _uniform = backoff
    broken = mocker.create_autospec(AIOKafkaProducer, instance=True)
    broken.send_and_wait.side_effect = RuntimeError("broker down")

    with capture_logs() as logs:
        requests = await deliver(
            value=encode_envelope_bytes("task.created", body),
            outcome=httpx.Response(400),
            producer=broken,
        )

    assert len(requests) == 1
    assert requests[0].headers["Idempotency-Key"] == str(task.id)
    sleep.assert_not_called()
    failed = [entry for entry in logs if entry.get("event") == "kafka_produce_failed"]
    assert len(failed) == 1
    assert failed[0]["topic"] == "webhook_dlq"
    assert failed[0]["error"] == "broker down"
