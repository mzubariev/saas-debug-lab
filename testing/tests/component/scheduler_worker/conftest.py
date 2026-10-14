"""scheduler-worker has no ASGI app. Import after service_env; do not open a lifespan."""

import importlib
from types import ModuleType

import pytest


@pytest.fixture(scope="session", autouse=True)
def worker_module(service_env: None) -> ModuleType:
    """Import ``app.core.celery`` only after this worker's environment is set."""
    return importlib.import_module("app.core.celery")
