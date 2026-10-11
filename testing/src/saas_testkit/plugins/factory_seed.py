"""One Polyfactory seed for a pytest session. Layers opt in from their conftest."""

import pytest

from saas_testkit.factories import seed_factories_once


@pytest.fixture(scope="session")
def seed_factories(pytestconfig: pytest.Config) -> None:
    """Seed factories from the pytest-randomly number. No infra and no database."""
    seed_factories_once(pytestconfig.getoption("randomly_seed"))
