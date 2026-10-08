"""Smoke fixtures. `SMOKE_BASE_URL` is probed once before any test runs."""

import json
import os
from collections.abc import AsyncIterator, Iterator
from typing import cast
from uuid import uuid4

import httpx
import pytest

from saas_testkit.adapters.http import HttpAuthApi, HttpTaskApi
from saas_testkit.config import KitSettings
from saas_testkit.context import RunContext, using_context
from saas_testkit.factories import seed_factories_once
from saas_testkit.flows import AuthFlow, TaskLifecycle

_TIMEOUT = httpx.Timeout(10.0, connect=2.0)
_HEALTH = "/health"


def pytest_sessionstart(session: pytest.Session) -> None:
    """Wrong or unset `SMOKE_BASE_URL` stops the run before the catalogue."""
    if not _collects_smoke(session):
        return
    url = os.environ.get("SMOKE_BASE_URL", "").strip().rstrip("/")
    if not url:
        pytest.exit("SMOKE_BASE_URL is not set", returncode=1)
    try:
        response = httpx.get(f"{url}{_HEALTH}", timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        pytest.exit(f"SMOKE_BASE_URL {url} is not reachable: {exc}", returncode=1)
    body = _body_status(response)
    if response.status_code != 200 or body != "ok":
        pytest.exit(
            f"SMOKE_BASE_URL {url} is not the stack: "
            f"{_HEALTH} returned {response.status_code} {body!r}",
            returncode=1,
        )


def _collects_smoke(session: pytest.Session) -> bool:
    """Initial conftest load is the smoke path. Do not probe when a wider run imports this file."""
    return any("smoke" in arg.replace("\\", "/") for arg in session.config.args)


@pytest.fixture(scope="session", autouse=True)
def _seed_factories(pytestconfig: pytest.Config) -> None:
    seed_factories_once(pytestconfig.getoption("randomly_seed"))


@pytest.fixture(scope="session")
def smoke_base_url() -> str:
    return os.environ["SMOKE_BASE_URL"].strip().rstrip("/")


@pytest.fixture(scope="session")
def ui_url() -> str:
    return KitSettings().ui_url


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid4().hex


@pytest.fixture(autouse=True)
def run_context(run_id: str, request: pytest.FixtureRequest) -> Iterator[RunContext]:
    ctx = RunContext.create(run_id=run_id, test_id=request.node.nodeid)
    with using_context(ctx):
        yield ctx


@pytest.fixture
async def client(smoke_base_url: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=smoke_base_url, timeout=_TIMEOUT) as http:
        yield http


@pytest.fixture
def auth(client: httpx.AsyncClient, run_context: RunContext) -> AuthFlow:
    return AuthFlow(HttpAuthApi(client, run_context))


@pytest.fixture
async def lifecycle(smoke_base_url: str, run_context: RunContext) -> AsyncIterator[TaskLifecycle]:
    """Admin login is a precondition. The test asserts create and read."""
    async with httpx.AsyncClient(base_url=smoke_base_url, timeout=_TIMEOUT) as http:
        token = await AuthFlow(HttpAuthApi(http, run_context)).logged_in(
            username="admin", password="admin123"
        )
        http.headers["Authorization"] = f"Bearer {token.access_token}"
        yield TaskLifecycle(HttpTaskApi(http, run_context))


@pytest.fixture
async def service_health(
    client: httpx.AsyncClient, request: pytest.FixtureRequest
) -> tuple[int, str | None]:
    response = await client.get(str(request.param))
    return response.status_code, _body_status(response)


@pytest.fixture
async def metrics_status(client: httpx.AsyncClient) -> int:
    response = await client.get("/metrics")
    return response.status_code


@pytest.fixture
async def frontend_status(ui_url: str) -> int:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        response = await http.get(ui_url)
    return response.status_code


def _body_status(response: httpx.Response) -> str | None:
    try:
        parsed = cast(object, response.json())
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    status = cast(dict[object, object], parsed).get("status")
    if isinstance(status, str):
        return status
    return None
