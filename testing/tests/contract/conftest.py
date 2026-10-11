"""Fixtures for the contract layer. One app lifespan per worker, from the shared plugin."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from saas_testkit.adapters.http import (
    GatewayUpstream,
    HttpAuthApi,
    HttpGatewayApi,
    HttpSimulatorApi,
    HttpTaskApi,
    HttpWebhookApi,
)
from saas_testkit.adapters.kafka import KafkaEventReader
from saas_testkit.adapters.redis import TaskCache, UserCache
from saas_testkit.context import RunContext
from saas_testkit.flows import (
    AuthFlow,
    ExternalReceiver,
    GatewayFlow,
    InboundWebhook,
    TaskLifecycle,
    WebhookDelivery,
)
from saas_testkit.infra import needs_infra

# Captured-event directories keep their own filter. HTTP producer dirs match `--service`.
_HTTP_SERVICES = {
    "task_service": "task-service",
    "auth_service": "auth-service",
    "webhook_receiver": "webhook-receiver",
    "external_service_simulator": "external-service-simulator",
    "api_gateway": "api-gateway",
}


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    try:
        parts = collection_path.relative_to(config.rootpath).parts
    except ValueError:
        return None
    if len(parts) < 3 or parts[:2] != ("tests", "contract") or parts[2] != "http":
        return None
    service = config.getoption("service")
    if not isinstance(service, str) or not service:
        return True
    if len(parts) < 4:
        return None
    expected = _HTTP_SERVICES.get(parts[3])
    if expected is None or service == expected:
        return None
    return True


@pytest.fixture(scope="session", autouse=True)
def _seed_factories(seed_factories: None) -> None:
    """One Polyfactory seed per run."""


@pytest.fixture(autouse=True)
def _flush_redis(request: pytest.FixtureRequest) -> None:
    """FLUSHDB before each in-process test.

    A contract session without ``--service`` collects schema checks only and
    does not start Redis. Resolve the async fixture from this sync wrapper so
    setup does not call ``Runner.run`` on an already running loop.
    """
    if not needs_infra(request.config):
        return
    request.getfixturevalue("flush_redis")


@pytest.fixture(autouse=True)
def _run_context(run_context: RunContext) -> RunContext:
    """Bind `RunContext` for `unique_title` and for the headers on task calls."""
    return run_context


@pytest.fixture(scope="session")
def service_app(open_app_lifespan: object) -> FastAPI:
    """The selected service, lifespan already open for this worker."""
    if not isinstance(open_app_lifespan, FastAPI):
        raise RuntimeError("service did not expose a FastAPI app")
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


@pytest.fixture
def gateway(client: httpx.AsyncClient, run_context: RunContext) -> Iterator[GatewayFlow]:
    upstream = GatewayUpstream()
    upstream.start()
    try:
        yield GatewayFlow(HttpGatewayApi(client, run_context), upstream, run_context)
    finally:
        upstream.stop()


@pytest.fixture
def inbound(
    client: httpx.AsyncClient,
    run_context: RunContext,
    events: KafkaEventReader,
) -> InboundWebhook:
    return InboundWebhook(HttpWebhookApi(client, run_context), WebhookDelivery(events))


@pytest.fixture
def simulator(client: httpx.AsyncClient, run_context: RunContext) -> ExternalReceiver:
    return ExternalReceiver(HttpSimulatorApi(client, run_context))
