"""Fixtures for one service in-process. Component and contract share this plugin.

Layer conftests decide which of these run for every test.
"""

import logging
from collections.abc import AsyncIterator, Iterator
from typing import cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from saas_testkit.adapters.kafka import KafkaEventReader
from saas_testkit.config import SERVICES, redis_db_index, service_environment
from saas_testkit.context import RunContext, using_context
from saas_testkit.factories import Rows, TaskRowFactory, UserRowFactory
from saas_testkit.infra import (
    KAFKA_TOPICS,
    DbUrls,
    Infra,
    InfraHandle,
    create_worker_database,
    drop_database,
    import_service_app,
    is_worker,
    quote_ident,
    worker_database_name,
    worker_index,
)
from saas_testkit.infra import open_app_lifespan as enter_app_lifespan

logger = logging.getLogger(__name__)

_DELETE_TOUCHED = text('DELETE FROM "_touched" RETURNING tbl')
# Distinct from the 30-minute default so a hardcoded lifetime fails.
_AUTH_TOKEN_MINUTES = "45"


def _worker_redis_url(infra: Infra, worker_id: str) -> str:
    return infra.redis_url_for(redis_db_index(infra.service, worker_index(worker_id)))


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
    create_worker_database(infra.pg_admin_url, infra.template_db, name)
    urls = DbUrls.for_database(infra.pg_admin_url, name)
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
    redis_url = _worker_redis_url(infra, worker_id)
    try:
        for key, value in worker_db.postgres_env().items():
            patch.setenv(key, value)
        patch.setenv("REDIS_URL", redis_url)
        patch.setenv("KAFKA_BOOTSTRAP_SERVERS", infra.kafka_bootstrap)
        patch.setenv("SERVICE_NAME", infra.service)
        patch.setenv("OTLP_ENDPOINT", "")
        patch.setenv("SENTRY_DSN", "")
        for key, value in service_environment(infra.service, redis_url=redis_url).items():
            patch.setenv(key, value)
        yield
    finally:
        patch.undo()


@pytest.fixture(scope="session")
async def open_app_lifespan(
    service_env: None,
    pytestconfig: pytest.Config,
    worker_id: str,
) -> AsyncIterator[object]:
    """Import after ``service_env`` and enter the lifespan once per worker."""
    service = pytestconfig.getoption("service")
    if not isinstance(service, str) or service not in SERVICES:
        raise RuntimeError("in-process tests need --service")
    patch = pytest.MonkeyPatch()
    if service == "auth-service":
        patch.setenv("TOKEN_EXPIRE_MINUTES", _AUTH_TOKEN_MINUTES)
    try:
        app = import_service_app(SERVICES[service])
        logger.info("entering service lifespan worker=%s service=%s", worker_id, service)
        async with enter_app_lifespan(app):
            yield app
    finally:
        patch.undo()


@pytest.fixture
async def flush_redis(infra: Infra, worker_id: str) -> None:
    """FLUSHDB on this worker's Redis index before each test."""
    client: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        _worker_redis_url(infra, worker_id)
    )
    try:
        await client.flushdb()  # pyright: ignore[reportUnknownMemberType]
    finally:
        await client.aclose()


@pytest.fixture
async def clean_db(
    request: pytest.FixtureRequest,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Truncate tables listed in ``_touched``. Runs only for ``@pytest.mark.clean_db``."""
    item = cast(pytest.Item, request.node)  # pyright: ignore[reportUnknownMemberType]
    if item.get_closest_marker("clean_db") is None:
        return
    async with session_maker() as session:
        rows = (await session.execute(_DELETE_TOUCHED)).scalars().all()
        names = [name for name in rows if isinstance(name, str)]
        if names:
            listed = ", ".join(quote_ident(name) for name in names)
            await session.execute(text(f"TRUNCATE {listed} RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid4().hex


@pytest.fixture
def run_context(run_id: str, request: pytest.FixtureRequest) -> Iterator[RunContext]:
    """Bind `RunContext` for `unique_title` and for the headers on task calls."""
    item = cast(pytest.Item, request.node)  # pyright: ignore[reportUnknownMemberType]
    ctx = RunContext.create(run_id=run_id, test_id=item.nodeid)
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
    await reader.start(*KAFKA_TOPICS)
    try:
        yield reader
    finally:
        await reader.stop()
