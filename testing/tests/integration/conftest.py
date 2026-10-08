"""Integration fixtures. The controller starts the stack; workers read the session file."""

from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import httpx
import pytest
from polyfactory.factories.base import BaseFactory

from saas_testkit.adapters.http import HttpAuthApi, HttpTaskApi
from saas_testkit.adapters.kafka import KafkaEventReader
from saas_testkit.adapters.mail import MailHogInbox
from saas_testkit.adapters.wiremock import WireMockSink
from saas_testkit.context import RunContext, using_context
from saas_testkit.flows import AuthFlow, TaskLifecycle
from saas_testkit.infra import KAFKA_TOPICS, read_session

_factories_seeded = False


@pytest.fixture(scope="session", autouse=True)
def _seed_factories(pytestconfig: pytest.Config) -> None:
    """One seed per run, so the pytest-randomly number reproduces factory data too."""
    global _factories_seeded
    if _factories_seeded:
        return
    seed = pytestconfig.getoption("randomly_seed")
    if not isinstance(seed, int):
        raise RuntimeError("pytest-randomly did not provide an integer seed")
    BaseFactory.seed_random(seed)
    _factories_seeded = True


@pytest.fixture(scope="session")
def base_url() -> str:
    return read_session().base_url


@pytest.fixture(scope="session")
def nginx_url() -> str:
    return read_session().nginx_url


@pytest.fixture(scope="session")
def admin_token() -> str:
    return read_session().access_token


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid4().hex


@pytest.fixture(autouse=True)
def run_context(run_id: str, request: pytest.FixtureRequest) -> Iterator[RunContext]:
    """Bind `RunContext` for `unique_title` and for the headers on task calls."""
    ctx = RunContext.create(run_id=run_id, test_id=request.node.nodeid)
    with using_context(ctx):
        yield ctx


@pytest.fixture
async def client(base_url: str, admin_token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Real network client. The bearer token is the seeded admin login."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30) as http:
        yield http


@pytest.fixture
def auth(client: httpx.AsyncClient, run_context: RunContext) -> AuthFlow:
    return AuthFlow(HttpAuthApi(client, run_context))


@pytest.fixture
def lifecycle(client: httpx.AsyncClient, run_context: RunContext) -> TaskLifecycle:
    return TaskLifecycle(HttpTaskApi(client, run_context))


@pytest.fixture
async def events(worker_id: str) -> AsyncIterator[KafkaEventReader]:
    """Stack broker on the published external listener. One group per worker."""
    reader = KafkaEventReader("127.0.0.1:9093", group_id=f"integration-{worker_id}-{uuid4().hex}")
    await reader.start(*KAFKA_TOPICS)
    try:
        yield reader
    finally:
        await reader.stop()


@pytest.fixture
def mail() -> MailHogInbox:
    return MailHogInbox("http://127.0.0.1:8025")


@pytest.fixture
def wiremock() -> WireMockSink:
    return WireMockSink("http://127.0.0.1:8089")
