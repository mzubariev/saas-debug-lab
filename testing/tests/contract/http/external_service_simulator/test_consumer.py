"""The received-webhook body matches the consumer model."""

from saas_testkit.domain import SimulatorReceipt
from saas_testkit.flows import ExternalReceiver


async def test_received_webhook_matches_consumer_model(simulator: ExternalReceiver) -> None:
    delivery = await simulator.receive()

    assert delivery.response.status == 200
    SimulatorReceipt.model_validate(delivery.response.document)
