"""Fixtures for the contract layer. One app lifespan per worker."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from saas_testkit.config import SERVICES
from saas_testkit.infra import import_service_app, open_app_lifespan

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


@pytest.fixture(scope="session")
async def service_app(
    service_env: None,
    pytestconfig: pytest.Config,
) -> AsyncIterator[FastAPI]:
    """Import after `service_env`. Event capture and HTTP checks share this lifespan."""
    service = pytestconfig.getoption("service")
    if not isinstance(service, str) or service not in SERVICES:
        raise RuntimeError("contract tests need --service")
    patch = pytest.MonkeyPatch()
    if service == "auth-service":
        patch.setenv("TOKEN_EXPIRE_MINUTES", "45")
    try:
        app = import_service_app(SERVICES[service])
        if not isinstance(app, FastAPI):
            raise RuntimeError(f"{service} did not expose a FastAPI app")
        async with open_app_lifespan(app):
            yield app
    finally:
        patch.undo()
