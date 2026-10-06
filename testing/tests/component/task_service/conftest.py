"""task-service component fixtures. The app builds its engine from the environment."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from saas_testkit.adapters.http.tasks import HttpTaskApi
from saas_testkit.config.services import SERVICES
from saas_testkit.context import RunContext
from saas_testkit.flows import TaskLifecycle
from saas_testkit.infra.app_loader import import_service_app


@pytest.fixture(scope="session")
async def service_app(service_env: None) -> AsyncIterator[FastAPI]:
    app = import_service_app(SERVICES["task-service"])
    if not isinstance(app, FastAPI):
        raise RuntimeError("task-service did not expose a FastAPI app")
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(service_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=service_app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        service_app.dependency_overrides.clear()


@pytest.fixture
def lifecycle(client: httpx.AsyncClient, run_context: RunContext) -> TaskLifecycle:
    return TaskLifecycle(HttpTaskApi(client, run_context))
