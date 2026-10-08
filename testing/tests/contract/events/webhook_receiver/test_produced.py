"""webhook-receiver events captured on Redpanda match the committed schema."""

from collections.abc import Callable

from saas_testkit.domain.events import Envelope
from saas_testkit.flows import InboundWebhook


async def test_produced_webhook_inbound_matches_snapshot(
    inbound: InboundWebhook,
    event_schema_errors: Callable[[str, Envelope], list[str]],
) -> None:
    accepted = await inbound.accept()
    event = await inbound.published(accepted.event)

    assert event_schema_errors("webhook_inbound", event) == []
