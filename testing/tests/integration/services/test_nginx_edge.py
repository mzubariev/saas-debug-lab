"""Nginx edge. The module shares one xdist group so these tests stay on one worker."""

from collections.abc import AsyncIterator

import httpx
import pytest

from saas_testkit.adapters.http import HttpAuthApi
from saas_testkit.context import RunContext
from saas_testkit.domain import StatusBody
from saas_testkit.flows import AuthFlow

_BURST = 10
_HOST = "lab.example"
_FORWARDED_FOR = "203.0.113.10"
_FORWARDED_PROTO = "https"


@pytest.fixture
async def edge(nginx_url: str) -> AsyncIterator[httpx.AsyncClient]:
    """Real nginx, with no `Authorization` header (an empty limit-req key)."""
    async with httpx.AsyncClient(base_url=nginx_url, timeout=30) as http:
        yield http


@pytest.fixture
def edge_auth(edge: httpx.AsyncClient, run_context: RunContext) -> AuthFlow:
    return AuthFlow(HttpAuthApi(edge, run_context))


@pytest.mark.xdist_group("serial")
async def test_login_burst_without_a_bearer_is_not_limited(edge_auth: AuthFlow) -> None:
    # BUG-1: the auth zone is 5 r/min, keyed by Authorization. A login sends none.
    statuses = [
        (await edge_auth.login(username="admin", password="admin123")).status for _ in range(_BURST)
    ]

    assert statuses == [200] * _BURST


@pytest.mark.xdist_group("serial")
async def test_foreign_host_with_forwarded_headers_reaches_the_gateway(
    edge: httpx.AsyncClient, run_context: RunContext
) -> None:
    # characterization: Host, X-Forwarded-For, and X-Forwarded-Proto are not on the
    # response. A foreign Host still proxies, and the gateway echoes X-Request-ID.
    status, body, request_id = await _proxied_health(edge, run_context)

    assert status == 200
    assert body == "ok"
    assert request_id == run_context.test_id


async def _proxied_health(
    client: httpx.AsyncClient, ctx: RunContext
) -> tuple[int, str | None, str | None]:
    response = await client.get(
        "/health",
        headers={
            **ctx.headers(),
            "Host": _HOST,
            "X-Forwarded-For": _FORWARDED_FOR,
            "X-Forwarded-Proto": _FORWARDED_PROTO,
        },
    )
    body = None
    if response.status_code == 200:
        body = StatusBody.model_validate(response.json()).status
    return response.status_code, body, response.headers.get("x-request-id")
