"""External webhook intake. The caller asserts; this flow only sends."""

from dataclasses import dataclass

from saas_testkit.adapters.http.simulator import HttpSimulatorApi
from saas_testkit.context import unique_title
from saas_testkit.domain.http import ApiResponse, SimulatorReceipt

_CUSTOM_STATUS = 503


@dataclass(frozen=True, slots=True, kw_only=True)
class Delivery:
    """One `/receive-webhook` call plus the key and body it sent."""

    response: ApiResponse[SimulatorReceipt]
    key: str
    payload: dict[str, object]


class ExternalReceiver:
    def __init__(self, api: HttpSimulatorApi) -> None:
        self._api = api

    async def receive(self) -> Delivery:
        """POST a unique body with a new idempotency key. Defaults store the key."""
        return await self._send()

    async def receive_again(self, first: Delivery) -> ApiResponse[SimulatorReceipt]:
        """POST the same key again. The caller asserts on the response."""
        return await self._api.receive(first.payload, key=first.key)

    async def fail(self, kind: str) -> Delivery:
        """POST a new key that the simulator must not store.

        `simulated` forces `fail_rate=1`. `custom` asks for a non-200 status.
        """
        match kind:
            case "simulated":
                return await self._send(fail_rate=1.0)
            case "custom":
                return await self._send(status_code=_CUSTOM_STATUS)
            case _:
                raise ValueError(f"unknown failure {kind}")

    async def _send(
        self,
        *,
        fail_rate: float | None = None,
        status_code: int | None = None,
    ) -> Delivery:
        key = unique_title("idem")
        payload: dict[str, object] = {"marker": unique_title("body")}
        response = await self._api.receive(
            payload,
            key=key,
            fail_rate=fail_rate,
            status_code=status_code,
        )
        return Delivery(response=response, key=key, payload=payload)
