"""external-service-simulator component fixtures. The app keeps keys in memory."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from saas_testkit.adapters.http import HttpSimulatorApi
from saas_testkit.config import SERVICES
from saas_testkit.context import RunContext
from saas_testkit.flows import ExternalReceiver
from saas_testkit.infra import import_service_app, open_app_lifespan


@pytest.fixture(scope="session")
async def service_app(service_env: None) -> AsyncIterator[FastAPI]:
    app = import_service_app(SERVICES["external-service-simulator"])
    if not isinstance(app, FastAPI):
        raise RuntimeError("external-service-simulator did not expose a FastAPI app")
    async with open_app_lifespan(app):
        yield app


@pytest.fixture
async def client(service_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=service_app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        service_app.dependency_overrides.clear()


@pytest.fixture
def simulator(client: httpx.AsyncClient, run_context: RunContext) -> ExternalReceiver:
    return ExternalReceiver(HttpSimulatorApi(client, run_context))
