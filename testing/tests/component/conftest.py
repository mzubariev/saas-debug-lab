"""Fixtures for the component layer.

Workers have no ``config._infra``. They receive ``workerinput["infra"]``.
The controller holds an ``InfraHandle``; fixtures use ``handle.info``.
"""

import logging
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
from polyfactory.factories.base import BaseFactory
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from saas_testkit.adapters.kafka.reader import KafkaEventReader
from saas_testkit.context import RunContext, using_context
from saas_testkit.factories.rows import Rows, TaskRowFactory, UserRowFactory
from saas_testkit.infra.containers import Infra, InfraHandle
from saas_testkit.infra.template_db import (
    DbUrls,
    create_worker_database,
    drop_database,
    quote_ident,
    worker_database_name,
)
from saas_testkit.infra.xdist import is_worker, worker_index

logger = logging.getLogger("saas_testkit.component")

# Topic names from SUT_MAP (Kafka envelope table).
_TOPICS = ("task_created", "task_updated", "webhook_inbound", "webhook_dlq")
_DELETE_TOUCHED = text('DELETE FROM "_touched" RETURNING tbl')


def _infra(config: pytest.Config) -> Infra:
    if is_worker(config):
        raw = config.workerinput["infra"]  # type: ignore[attr-defined]
        return Infra.model_validate(raw)
    handle = getattr(config, "_infra", None)
    if not isinstance(handle, InfraHandle):
        raise RuntimeError("component infrastructure was not started")
    return handle.info


@pytest.fixture(scope="session")
def infra(pytestconfig: pytest.Config) -> Infra:
    return _infra(pytestconfig)


@pytest.fixture(scope="session")
def worker_db(infra: Infra, worker_id: str) -> Iterator[DbUrls]:
    """Clone ``test_<service>_<layer>_<worker>`` and drop it at session end."""
    name = worker_database_name(infra.service, infra.layer, worker_id)
    logger.info("creating worker database %s from %s", name, infra.template_db)
    urls = create_worker_database(infra.pg_admin_url, infra.template_db, name)
    try:
        yield urls
    finally:
        drop_database(infra.pg_admin_url, name)


@pytest.fixture(scope="session")
async def session_maker(
    worker_db: DbUrls,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(worker_db.async_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def db(session_maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session


@pytest.fixture(scope="session")
def service_env(infra: Infra, worker_db: DbUrls, worker_id: str) -> Iterator[None]:
    """Point the service at this worker. Import the app only after this runs."""
    patch = pytest.MonkeyPatch()
    try:
        for key, value in worker_db.postgres_env().items():
            patch.setenv(key, value)
        patch.setenv("REDIS_URL", infra.redis_url_for(worker_index(worker_id)))
        patch.setenv("KAFKA_BOOTSTRAP_SERVERS", infra.kafka_bootstrap)
        patch.setenv("SERVICE_NAME", infra.service)
        patch.setenv("OTLP_ENDPOINT", "")
        patch.setenv("SENTRY_DSN", "")
        yield
    finally:
        patch.undo()


@pytest.fixture(autouse=True)
async def flush_redis(infra: Infra, worker_id: str) -> None:
    """FLUSHDB on this worker's Redis index before each test."""
    client: Redis = Redis.from_url(infra.redis_url_for(worker_index(worker_id)))
    try:
        await client.flushdb()
    finally:
        await client.aclose()


@pytest.fixture(autouse=True)
async def clean_db(
    request: pytest.FixtureRequest,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Truncate tables listed in ``_touched``. Runs only for ``@pytest.mark.clean_db``."""
    if request.node.get_closest_marker("clean_db") is None:
        return
    async with session_maker() as session:
        rows = (await session.execute(_DELETE_TOUCHED)).scalars().all()
        names = [name for name in rows if isinstance(name, str)]
        if names:
            listed = ", ".join(quote_ident(name) for name in names)
            await session.execute(text(f"TRUNCATE {listed} RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
def _seed_factories(pytestconfig: pytest.Config) -> None:
    """One seed per run, so the pytest-randomly number reproduces factory data too."""
    seed = pytestconfig.getoption("randomly_seed")
    if not isinstance(seed, int):
        raise RuntimeError("pytest-randomly did not provide an integer seed")
    BaseFactory.seed_random(seed)


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
def rows(db: AsyncSession) -> Rows:
    """Per-test subclasses. The session is not stored on the shared factory."""

    class BoundTask(TaskRowFactory):
        __async_session__ = db

    class BoundUser(UserRowFactory):
        __async_session__ = db

    return Rows(task=BoundTask, user=BoundUser)


@pytest.fixture(scope="session")
async def events(infra: Infra, worker_id: str) -> AsyncIterator[KafkaEventReader]:
    """Subscribe before any test produces. Each worker has its own group."""
    group_id = f"{infra.service}-{infra.layer}-{worker_id}-{uuid4().hex}"
    reader = KafkaEventReader(infra.kafka_bootstrap, group_id=group_id)
    await reader.start(*_TOPICS)
    try:
        yield reader
    finally:
        await reader.stop()
