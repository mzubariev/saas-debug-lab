"""S2: a webhook that fails, then the scheduler replay of a permanent failure."""

from uuid import UUID, uuid4

import pytest

from saas_testkit.adapters.wiremock import RecordedCall, WireMockSink
from saas_testkit.context import unique_title
from saas_testkit.domain import WebhookDlqPayload
from saas_testkit.flows import TaskLifecycle, WebhookDelivery
from saas_testkit.polling import eventually

_RETRY = (503, 503, 200)


async def test_webhook_retries_then_delivers(
    lifecycle: TaskLifecycle, wiremock: WireMockSink
) -> None:
    title = unique_title("task")
    await wiremock.stub_sequence(title, scenario=uuid4().hex, statuses=_RETRY)

    created = await lifecycle.create(title=title)
    assert created.status == 201
    assert created.data is not None

    calls = await _calls(wiremock, created.data.id, len(_RETRY))
    assert len(calls) == len(_RETRY)
    assert sorted(call.status for call in calls) == [200, 503, 503]


@pytest.mark.slow
async def test_permanent_failure_is_replayed_without_an_idempotency_key(
    lifecycle: TaskLifecycle, delivery: WebhookDelivery, wiremock: WireMockSink
) -> None:
    title = unique_title("task")
    await wiremock.stub_for_title(title, status=400)

    created = await lifecycle.create(title=title)
    assert created.status == 201
    assert created.data is not None
    task_id = created.data.id

    dead = await delivery.dead_letter(task_id)
    payload = WebhookDlqPayload.model_validate(dead.payload)
    assert payload.id == task_id
    assert payload.attempts == 1

    calls = await eventually(
        lambda: _replayed(wiremock, str(task_id)),
        timeout=30,
        message=f"no scheduler replay for {task_id}",
    )
    assert calls is not None
    assert any(call.idempotency_key == str(task_id) for call in calls)
    assert any(call.idempotency_key is None for call in calls)


async def _calls(sink: WireMockSink, task_id: UUID, count: int) -> tuple[RecordedCall, ...]:
    found = await eventually(
        lambda: _enough(sink, str(task_id), count),
        timeout=15,
        message=f"fewer than {count} webhooks for {task_id}",
    )
    assert found is not None
    return found


async def _enough(
    sink: WireMockSink, payload_id: str, count: int
) -> tuple[RecordedCall, ...] | None:
    found = await sink.calls_for(payload_id)
    if len(found) < count:
        return None
    return found


async def _replayed(sink: WireMockSink, payload_id: str) -> tuple[RecordedCall, ...] | None:
    found = await sink.calls_for(payload_id)
    keyed = any(call.idempotency_key == payload_id for call in found)
    replayed = any(call.idempotency_key is None for call in found)
    if keyed and replayed:
        return found
    return None
