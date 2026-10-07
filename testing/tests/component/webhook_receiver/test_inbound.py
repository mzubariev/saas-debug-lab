"""Characterised webhook-receiver behaviour. The flow returns the response; the test decides."""

import pytest
from pytest_mock import MockerFixture

from saas_testkit.context import RunContext
from saas_testkit.domain import WebhookInboundPayload
from saas_testkit.flows import InboundWebhook


@pytest.mark.xfail(
    strict=True,
    reason="BUG-5: the success log passes event= and the route returns 500",
)
async def test_inbound_returns_received(inbound: InboundWebhook) -> None:
    accepted = await inbound.accept()

    assert accepted.response.status == 200
    assert accepted.response.data is not None
    assert accepted.response.data.status == "received"
    assert accepted.response.data.event == accepted.event


async def test_inbound_publishes_webhook_inbound(inbound: InboundWebhook) -> None:
    accepted = await inbound.accept()

    envelope = await inbound.published(accepted.event)
    payload = WebhookInboundPayload.model_validate(envelope.payload)
    assert envelope.event_type == "webhook.inbound"
    assert payload.event == accepted.event
    assert payload.data == accepted.data


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("missing-event", id="missing-event"),
        pytest.param("event-type", id="wrong-type-event"),
        pytest.param("data-type", id="wrong-type-data"),
    ],
)
async def test_inbound_rejects_an_invalid_body(inbound: InboundWebhook, case: str) -> None:
    response = await inbound.submit(case)

    assert response.status == 422


async def test_publish_failure_returns_server_error(
    inbound: InboundWebhook, mocker: MockerFixture
) -> None:
    mocker.patch(
        "app.services.webhook_service.publish_json",
        autospec=True,
        side_effect=RuntimeError("kafka down"),
    )

    accepted = await inbound.accept()

    assert accepted.response.status == 500
    assert accepted.response.error is not None
    assert accepted.response.error.detail == "Internal server error"


async def test_inbound_envelope_keeps_the_request_trace(
    inbound: InboundWebhook, run_context: RunContext
) -> None:
    accepted = await inbound.accept()

    envelope = await inbound.published(accepted.event)

    assert envelope.trace_id == run_context.trace_id
