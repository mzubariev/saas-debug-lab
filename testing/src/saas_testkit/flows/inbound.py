"""Inbound webhook steps. The caller asserts; this flow only sends and waits."""

from dataclasses import dataclass

from saas_testkit.adapters.http.webhooks import HttpWebhookApi
from saas_testkit.context import unique_title
from saas_testkit.domain.events import Envelope
from saas_testkit.domain.http import ApiResponse, InboundReceipt
from saas_testkit.flows.webhook_delivery import WebhookDelivery


@dataclass(frozen=True, slots=True, kw_only=True)
class Accepted:
    """The inbound response plus the `event` and `data` this call sent."""

    response: ApiResponse[InboundReceipt]
    event: str
    data: dict[str, object]


class InboundWebhook:
    def __init__(self, api: HttpWebhookApi, delivery: WebhookDelivery) -> None:
        self._api = api
        self._delivery = delivery

    async def accept(self) -> Accepted:
        """POST a unique event and data. The caller asserts on the response."""
        event = unique_title("hook")
        data: dict[str, object] = {"marker": unique_title("data")}
        return Accepted(
            response=await self._api.receive(event, data),
            event=event,
            data=data,
        )

    async def submit(self, case: str) -> ApiResponse[InboundReceipt]:
        """POST a body that `WebhookPayload` rejects. `case` selects which field is wrong."""
        return await self._api.submit(_invalid(case))

    async def published(self, event: str) -> Envelope:
        """The `webhook.inbound` envelope for `event`. Does not assert."""
        return await self._delivery.inbound(event)


def _invalid(case: str) -> dict[str, object]:
    match case:
        case "missing-event":
            return {}
        case "event-type":
            return {"event": 1}
        case "data-type":
            return {"event": unique_title("hook"), "data": "not-a-dict"}
        case _:
            raise ValueError(f"unknown body {case}")
