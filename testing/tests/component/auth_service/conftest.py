"""auth-service component fixtures. The app builds its engine from the environment."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from saas_testkit.adapters.http import HttpAuthApi
from saas_testkit.adapters.redis import UserCache
from saas_testkit.config import SERVICES
from saas_testkit.context import RunContext
from saas_testkit.flows import AuthFlow
from saas_testkit.infra import import_service_app

# Distinct from the 30-minute default so a hardcoded lifetime fails.
_TOKEN_EXPIRE_MINUTES = "45"


@pytest.fixture(scope="session")
async def service_app(service_env: None) -> AsyncIterator[FastAPI]:
    patch = pytest.MonkeyPatch()
    patch.setenv("TOKEN_EXPIRE_MINUTES", _TOKEN_EXPIRE_MINUTES)
    try:
        app = import_service_app(SERVICES["auth-service"])
        if not isinstance(app, FastAPI):
            raise RuntimeError("auth-service did not expose a FastAPI app")
        async with app.router.lifespan_context(app):
            yield app
    finally:
        patch.undo()


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
