"""WireMock stubs and the request journal. The stack publishes the admin API on :8089."""

from dataclasses import dataclass
from typing import cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

# Dispatcher and scheduler both POST the task payload here (WEBHOOK_URL).
_PATH = "/external/receive-webhook"


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordedCall:
    """One journal entry whose body or Idempotency-Key carries `payload_id`."""

    body: str
    idempotency_key: str | None
    status: int


class WireMockSink:
    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def install_catch_all(self) -> None:
        """Low-priority 200 for every other test's webhook."""
        self._post_mapping(
            {
                "priority": 10,
                "request": {"method": "POST", "urlPath": _PATH},
                "response": {"status": 200},
            }
        )

    async def stub_for_payload(self, payload_id: str, *, scenario: str, status: int = 200) -> None:
        """Match this test's `payload.id` inside `scenario`. Higher priority than the catch-all."""
        await self._post_mapping_async(
            {
                "priority": 1,
                "scenarioName": scenario,
                "request": {
                    "method": "POST",
                    "urlPath": _PATH,
                    "bodyPatterns": [{"matchesJsonPath": f"$[?(@.id == '{payload_id}')]"}],
                },
                "response": {"status": status},
            }
        )

    async def calls_for(self, payload_id: str) -> tuple[RecordedCall, ...]:
        """Journal entries for this payload id."""
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{self._base}/__admin/requests")
        response.raise_for_status()
        journal = _Journal.model_validate(cast(object, response.json()))
        found: list[RecordedCall] = []
        for entry in journal.requests:
            key = entry.request.header("Idempotency-Key")
            body = entry.request.body
            if key == payload_id or payload_id in body:
                found.append(
                    RecordedCall(body=body, idempotency_key=key, status=entry.response.status)
                )
        return tuple(found)

    def _post_mapping(self, document: dict[str, object]) -> None:
        response = httpx.post(f"{self._base}/__admin/mappings", json=document, timeout=5)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"wiremock mapping failed: {response.status_code} {response.text}")

    async def _post_mapping_async(self, document: dict[str, object]) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(f"{self._base}/__admin/mappings", json=document)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"wiremock mapping failed: {response.status_code} {response.text}")


class _Request(BaseModel):
    model_config = ConfigDict(extra="ignore")

    body: str = ""
    headers: dict[str, str] = Field(default_factory=dict)

    def header(self, name: str) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: int = 0


class _Entry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request: _Request = Field(default_factory=_Request)
    response: _Response = Field(default_factory=_Response)


def _no_requests() -> list[_Entry]:
    return []


class _Journal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requests: list[_Entry] = Field(default_factory=_no_requests)
