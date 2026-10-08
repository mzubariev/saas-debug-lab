"""S3: the simulator triggers an inbound webhook and the receiver publishes it."""

import pytest

from saas_testkit.context import unique_title
from saas_testkit.domain import WebhookInboundPayload
from saas_testkit.flows import ExternalReceiver, WebhookDelivery


async def test_triggered_event_is_published(
    simulator: ExternalReceiver, delivery: WebhookDelivery
) -> None:
    event = unique_title("hook")
    data: dict[str, object] = {"marker": unique_title("data")}

    await simulator.trigger(event, data)

    published = await delivery.inbound(event)
    payload = WebhookInboundPayload.model_validate(published.payload)
    assert payload.event == event
    assert payload.data == data


@pytest.mark.xfail(
    strict=True,
    reason="BUG-8: trigger_event logs event= and the route returns 500",
)
async def test_trigger_event_is_accepted(simulator: ExternalReceiver) -> None:
    triggered = await simulator.trigger(unique_title("hook"), {"marker": unique_title("data")})

    assert triggered.status == 202
    assert triggered.data is not None
    assert triggered.data.status == "triggered"
