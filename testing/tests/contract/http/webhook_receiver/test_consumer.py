"""The inbound receipt matches the consumer model."""

from saas_testkit.domain import InboundReceipt
from saas_testkit.flows import InboundWebhook


async def test_inbound_receipt_matches_consumer_model(inbound: InboundWebhook) -> None:
    accepted = await inbound.accept()

    InboundReceipt.model_validate(accepted.response.document)
