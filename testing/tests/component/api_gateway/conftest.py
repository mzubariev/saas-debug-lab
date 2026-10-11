"""api-gateway component fixtures. Upstreams are respx; the app builds no engine."""

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI

from saas_testkit.adapters.http import GatewayUpstream, HttpGatewayApi
from saas_testkit.context import RunContext
from saas_testkit.flows import GatewayFlow


@pytest.fixture(scope="session")
def service_app(open_app_lifespan: object) -> FastAPI:
    if not isinstance(open_app_lifespan, FastAPI):
        raise RuntimeError("api-gateway did not expose a FastAPI app")
    return open_app_lifespan


@pytest.fixture
async def client(service_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=service_app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        service_app.dependency_overrides.clear()


@pytest.fixture
def gateway(client: httpx.AsyncClient, run_context: RunContext) -> Iterator[GatewayFlow]:
    upstream = GatewayUpstream()
    upstream.start()
    try:
        yield GatewayFlow(HttpGatewayApi(client, run_context), upstream, run_context)
    finally:
        upstream.stop()
