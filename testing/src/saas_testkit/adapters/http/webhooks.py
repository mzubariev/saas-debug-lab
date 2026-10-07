"""Inbound webhook HTTP API. The injected client's transport selects the layer."""

from typing import cast

import httpx

from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, InboundReceipt, ProblemBody


class HttpWebhookApi:
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None:
        self._client = client
        self._ctx = ctx

    async def receive(self, event: str, data: dict[str, object]) -> ApiResponse[InboundReceipt]:
        return await self.submit({"event": event, "data": data})

    async def submit(self, payload: dict[str, object]) -> ApiResponse[InboundReceipt]:
        """POST `/webhooks/inbound` with a caller-built JSON object (validation cases)."""
        response = await self._client.post(
            "/webhooks/inbound",
            headers=self._ctx.headers(),
            json=payload,
        )
        return _read(response)


def _read(response: httpx.Response) -> ApiResponse[InboundReceipt]:
    parsed = cast(object, response.json())
    elapsed = response.elapsed.total_seconds()
    headers = {key: value for key, value in response.headers.items()}
    if response.is_success:
        return ApiResponse(
            status=response.status_code,
            data=InboundReceipt.model_validate(parsed),
            error=None,
            headers=headers,
            elapsed=elapsed,
            document=parsed,
        )
    return ApiResponse(
        status=response.status_code,
        data=None,
        error=ProblemBody.model_validate(parsed),
        headers=headers,
        elapsed=elapsed,
        document=parsed,
    )
