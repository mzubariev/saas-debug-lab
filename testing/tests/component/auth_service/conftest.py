"""auth-service component fixtures. The app builds its engine from the environment."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from saas_testkit.adapters.http import HttpAuthApi
from saas_testkit.adapters.redis import UserCache
from saas_testkit.context import RunContext
from saas_testkit.flows import AuthFlow


@pytest.fixture(scope="session")
def service_app(open_app_lifespan: object) -> FastAPI:
    if not isinstance(open_app_lifespan, FastAPI):
        raise RuntimeError("auth-service did not expose a FastAPI app")
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
def user_cache(service_app: FastAPI) -> UserCache:
    client = service_app.state.redis
    if not isinstance(client, Redis):
        raise RuntimeError("auth-service did not attach a Redis client")
    return UserCache(client)


@pytest.fixture
def auth(
    client: httpx.AsyncClient,
    run_context: RunContext,
    user_cache: UserCache,
) -> AuthFlow:
    return AuthFlow(HttpAuthApi(client, run_context), user_cache)
