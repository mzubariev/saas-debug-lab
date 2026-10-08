"""task-service component fixtures. The app builds its engine from the environment."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from saas_testkit.adapters.http import HttpTaskApi
from saas_testkit.adapters.kafka import KafkaEventReader
from saas_testkit.adapters.redis import TaskCache
from saas_testkit.config import SERVICES
from saas_testkit.context import RunContext
from saas_testkit.flows import TaskLifecycle
from saas_testkit.infra import import_service_app, open_app_lifespan


@pytest.fixture(scope="session")
async def service_app(service_env: None) -> AsyncIterator[FastAPI]:
    app = import_service_app(SERVICES["task-service"])
    if not isinstance(app, FastAPI):
        raise RuntimeError("task-service did not expose a FastAPI app")
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
def task_cache(service_app: FastAPI) -> TaskCache:
    client = service_app.state.redis
    if not isinstance(client, Redis):
        raise RuntimeError("task-service did not attach a Redis client")
    return TaskCache(client)


@pytest.fixture
def lifecycle(
    client: httpx.AsyncClient,
    run_context: RunContext,
    events: KafkaEventReader,
    task_cache: TaskCache,
) -> TaskLifecycle:
    return TaskLifecycle(HttpTaskApi(client, run_context), events, task_cache)
