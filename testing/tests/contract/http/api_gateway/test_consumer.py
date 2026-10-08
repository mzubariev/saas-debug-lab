"""The proxied JSON body matches the consumer model."""

from saas_testkit.domain import ProxiedBody
from saas_testkit.flows import GatewayFlow


async def test_proxied_body_matches_consumer_model(gateway: GatewayFlow) -> None:
    routed = await gateway.through("tasks")

    assert routed.response.status == 200
    ProxiedBody.model_validate(routed.response.document)
