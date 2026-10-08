"""The inbound receipt matches the consumer model."""

import pytest

from saas_testkit.domain import InboundReceipt
from saas_testkit.flows import InboundWebhook

pytestmark = pytest.mark.xfail(
    strict=True,
    reason="BUG-5: the success log passes event= and the route returns 500",
)


async def test_inbound_receipt_matches_consumer_model(inbound: InboundWebhook) -> None:
    accepted = await inbound.accept()

    InboundReceipt.model_validate(accepted.response.document)
