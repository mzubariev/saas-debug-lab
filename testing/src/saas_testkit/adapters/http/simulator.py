"""External simulator HTTP API. The injected client's transport selects the layer."""

from typing import cast

import httpx
from pydantic import ValidationError

from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, ProblemBody, SimulatorReceipt


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

    async def trigger(self, event: str, data: dict[str, object]) -> ApiResponse[SimulatorReceipt]:
        """POST `/trigger-event`. `delay=0` so a retry does not sleep."""
        response = await self._client.post(
            "/trigger-event",
            headers=self._ctx.headers(),
            json={"event": event, "data": data},
            params={"retry": "2", "delay": "0"},
        )
        return _trigger(response)


def _query(*, fail_rate: float | None, status_code: int | None) -> dict[str, str] | None:
    params: dict[str, str] = {}
    if fail_rate is not None:
        params["fail_rate"] = str(fail_rate)
    if status_code is not None:
        params["status"] = str(status_code)
    if not params:
        return None
    return params


def _trigger(response: httpx.Response) -> ApiResponse[SimulatorReceipt]:
    """`/trigger-event` returns its receipt, or a problem body when the route raises."""
    parsed = _json(response)
    data: SimulatorReceipt | None
    try:
        data = SimulatorReceipt.model_validate(parsed)
    except ValidationError:
        data = None
    error = None if data is not None else _problem(parsed)
    return ApiResponse(
        status=response.status_code,
        data=data,
        error=error,
        headers={key: value for key, value in response.headers.items()},
        elapsed=response.elapsed.total_seconds(),
        document=parsed,
    )


def _json(response: httpx.Response) -> object:
    return cast(object, response.json())


def _problem(parsed: object) -> ProblemBody | None:
    try:
        return ProblemBody.model_validate(parsed)
    except ValidationError:
        return None


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
