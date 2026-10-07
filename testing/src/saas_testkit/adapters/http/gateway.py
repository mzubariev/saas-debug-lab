"""Gateway HTTP API. respx stands in for the three upstreams at component level."""

import json
import os
from collections.abc import Callable
from typing import cast

import httpx
import respx
from pydantic import ValidationError

from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, ProblemBody, ProxiedBody

_UPSTREAM_ENV = ("AUTH_SERVICE_URL", "TASK_SERVICE_URL", "INTEGRATION_SERVICE_URL")


class HttpGatewayApi:
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None:
        self._client = client
        self._ctx = ctx

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        token: str | None = None,
    ) -> ApiResponse[ProxiedBody]:
        """`token` is the full `Authorization` value. `None` omits the header."""
        merged = dict(self._ctx.headers())
        if headers is not None:
            merged.update(headers)
        if token is not None:
            merged["Authorization"] = token
        response = await self._client.request(method, path, headers=merged)
        return _read(response)

    async def preflight(self, origin: str) -> ApiResponse[ProxiedBody]:
        """CORS preflight. The middleware answers before the proxy route."""
        response = await self._client.request(
            "OPTIONS",
            "/auth/session",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        return _read(response)


class GatewayUpstream:
    """respx routes for auth, task, and webhook upstreams."""

    def __init__(self) -> None:
        self._router = respx.mock(assert_all_called=False)

    def start(self) -> None:
        self._router.start()

    def stop(self) -> None:
        self._router.stop()

    def respond(self, *, status: int, marker: str) -> None:
        self._router.reset()
        self._router.route().mock(return_value=httpx.Response(status, json={"marker": marker}))

    def fail(self, kind: str) -> None:
        """`timeout` raises `TimeoutException`; `down` raises `ConnectError`."""
        self._router.reset()
        self._router.route().mock(side_effect=_failure(kind))

    def last_request(self) -> httpx.Request | None:
        """The latest call to a configured upstream, or `None` when nothing was proxied."""
        found: httpx.Request | None = None
        for request in _upstream_requests(self._router):
            found = request
        return found


def _failure(kind: str) -> Callable[[httpx.Request], None]:
    def explode(request: httpx.Request) -> None:
        match kind:
            case "timeout":
                raise httpx.TimeoutException("timed out", request=request)
            case "down":
                raise httpx.ConnectError("connection refused", request=request)
            case _:
                raise ValueError(f"unknown upstream failure {kind}")

    return explode


def _upstream_requests(router: respx.MockRouter) -> list[httpx.Request]:
    # respx's call list is untyped.
    calls = cast(list[object], router.calls)  # pyright: ignore[reportUnknownMemberType]
    requests: list[httpx.Request] = []
    for call in calls:
        request = getattr(call, "request", None)
        if isinstance(request, httpx.Request) and _is_upstream(str(request.url)):
            requests.append(request)
    return requests


def _is_upstream(url: str) -> bool:
    return any(url.startswith(base) for base in _bases())


def _bases() -> tuple[str, ...]:
    return tuple(os.environ[name].rstrip("/") for name in _UPSTREAM_ENV)


def _read(response: httpx.Response) -> ApiResponse[ProxiedBody]:
    parsed = _json(response)
    return ApiResponse(
        status=response.status_code,
        data=_proxied(parsed),
        error=None if response.status_code < 400 else _problem(parsed),
        headers={key.lower(): value for key, value in response.headers.items()},
        elapsed=response.elapsed.total_seconds(),
        document=parsed,
    )


def _json(response: httpx.Response) -> object | None:
    try:
        return cast(object, response.json())
    except json.JSONDecodeError:
        return None


def _proxied(parsed: object | None) -> ProxiedBody | None:
    try:
        return ProxiedBody.model_validate(parsed)
    except ValidationError:
        return None


def _problem(parsed: object | None) -> ProblemBody | None:
    try:
        return ProblemBody.model_validate(parsed)
    except ValidationError:
        return None
