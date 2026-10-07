"""External simulator HTTP API. The injected client's transport selects the layer."""

from typing import cast

import httpx

from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, SimulatorReceipt


class HttpSimulatorApi:
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None:
        self._client = client
        self._ctx = ctx

    async def receive(
        self,
        payload: dict[str, object],
        *,
        key: str,
        fail_rate: float | None = None,
        status_code: int | None = None,
    ) -> ApiResponse[SimulatorReceipt]:
        """POST `/receive-webhook`. `key` is the `Idempotency-Key` header."""
        headers = dict(self._ctx.headers())
        headers["Idempotency-Key"] = key
        response = await self._client.post(
            "/receive-webhook",
            headers=headers,
            params=_query(fail_rate=fail_rate, status_code=status_code),
            json=payload,
        )
        return _read(response)


def _query(*, fail_rate: float | None, status_code: int | None) -> dict[str, str] | None:
    params: dict[str, str] = {}
    if fail_rate is not None:
        params["fail_rate"] = str(fail_rate)
    if status_code is not None:
        params["status"] = str(status_code)
    if not params:
        return None
    return params


def _read(response: httpx.Response) -> ApiResponse[SimulatorReceipt]:
    """Every outcome is the simulator's own JSON, including 500 and a custom status."""
    parsed = cast(object, response.json())
    elapsed = response.elapsed.total_seconds()
    headers = {key: value for key, value in response.headers.items()}
    return ApiResponse(
        status=response.status_code,
        data=SimulatorReceipt.model_validate(parsed),
        error=None,
        headers=headers,
        elapsed=elapsed,
        document=parsed,
    )
