"""Component layer opts into the shared in-process fixtures."""

import pytest

from saas_testkit.context import RunContext


@pytest.fixture(scope="session", autouse=True)
def _seed_factories(seed_factories: None) -> None:
    """One Polyfactory seed per run."""


@pytest.fixture(autouse=True)
async def _flush_redis(flush_redis: None) -> None:
    """FLUSHDB on this worker's Redis index before each test."""


@pytest.fixture(autouse=True)
async def _clean_db(clean_db: None) -> None:
    """Truncate tables listed in ``_touched`` when the test is marked ``clean_db``."""


@pytest.fixture(autouse=True)
def _run_context(run_context: RunContext) -> RunContext:
    """Bind `RunContext` for `unique_title` and for the headers on task calls."""
    return run_context
