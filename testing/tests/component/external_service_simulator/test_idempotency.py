"""Characterised simulator idempotency. The flow returns the response; the test decides."""

import pytest

from saas_testkit.flows import ExternalReceiver

_CUSTOM_STATUS = 503


async def test_same_key_twice_returns_duplicate(simulator: ExternalReceiver) -> None:
    first = await simulator.receive()
    second = await simulator.receive_again(first)

    assert first.response.status == 200
    assert first.response.data is not None
    assert first.response.data.status == "received"
    assert first.response.data.payload == first.payload
    assert second.status == 200
    assert second.data is not None
    assert second.data.status == "duplicate"
    assert second.data.idempotency_key == first.key


@pytest.mark.parametrize(
    ("kind", "http_status", "body_status", "reason", "code"),
    [
        pytest.param("simulated", 500, "error", "simulated_failure", None, id="simulated-failure"),
        pytest.param(
            "custom", _CUSTOM_STATUS, "custom_status", None, _CUSTOM_STATUS, id="custom-status"
        ),
    ],
)
async def test_failed_attempt_is_not_recorded(
    simulator: ExternalReceiver,
    kind: str,
    http_status: int,
    body_status: str,
    reason: str | None,
    code: int | None,
) -> None:
    failed = await simulator.fail(kind)
    retry = await simulator.receive_again(failed)

    assert failed.response.status == http_status
    assert failed.response.data is not None
    assert failed.response.data.status == body_status
    assert failed.response.data.reason == reason
    assert failed.response.data.code == code
    assert retry.status == 200
    assert retry.data is not None
    assert retry.data.status == "received"
    assert retry.data.payload == failed.payload
