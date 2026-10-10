"""HTTP contract checks. The app lifespan lives on the contract session."""

import asyncio
import os
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from hypothesis import HealthCheck, assume, given, settings
from schemathesis import Case
from schemathesis.checks import not_a_server_error, response_schema_conformance
from schemathesis.openapi import from_dict
from schemathesis.schemas import BaseSchema
from schemathesis.specs.openapi.schemas import OpenApiSchema
from tests.component.conftest import (  # noqa: F401
    _seed_factories,
    events,
    flush_redis,
    infra,
    run_context,
    run_id,
    service_env,
    worker_db,
)

_DEFAULT_EXAMPLES = 40
_GATEWAY_OPENAPI = "BUG-6: duplicate operationIds fail OpenAPI validation"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("service") != "api-gateway":
        return
    marker = pytest.mark.xfail(strict=True, reason=_GATEWAY_OPENAPI)
    for item in items:
        if item.name == "test_openapi_document_is_valid":
            item.add_marker(marker)


@pytest.fixture
async def client(service_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=service_app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        service_app.dependency_overrides.clear()


def schema_examples() -> int:
    """PR-sized default. `SCHEMA_EXAMPLES` overrides it (40 on a PR, 500 nightly)."""
    raw = os.environ.get("SCHEMA_EXAMPLES", "").strip()
    if not raw:
        return _DEFAULT_EXAMPLES
    if not raw.isdecimal() or int(raw) < 1:
        raise RuntimeError(f"SCHEMA_EXAMPLES must be a positive integer, got {raw!r}")
    return int(raw)


@pytest.fixture(scope="session")
def fuzz_schema(service_app: FastAPI) -> OpenApiSchema:
    """The served OpenAPI document. Calls stay on the session loop, same as the app engine."""
    document = asyncio.get_event_loop().run_until_complete(_fetch_openapi(service_app))
    return from_dict(document)


@pytest.fixture
def check_openapi(service_app: FastAPI) -> Callable[[BaseSchema], None]:
    examples = schema_examples()

    def run(schema: BaseSchema) -> None:
        @given(case=schema.as_strategy())
        @settings(
            max_examples=examples,
            deadline=None,
            database=None,
            suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        )
        def check(case: Case) -> None:
            # BUG-9: Postgres rejects 0x00 in text, and auth login returns 500.
            assume(not _contains_nul(case))
            response = asyncio.get_event_loop().run_until_complete(_send(service_app, case))
            case.validate_response(
                response,
                checks=[not_a_server_error, response_schema_conformance],
            )

        check()

    return run


async def _fetch_openapi(app: FastAPI) -> dict[str, object]:
    async with _http(app) as client:
        response = await client.get("/openapi.json")
    if response.status_code != 200:
        raise RuntimeError(f"openapi.json returned {response.status_code}")
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("openapi.json was not an object")
    return body


async def _send(app: FastAPI, case: Case) -> Response:
    kwargs = case.as_transport_kwargs(base_url="http://test")
    cookies = kwargs.pop("cookies", None)
    async with _http(app) as client:
        if isinstance(cookies, dict) and cookies:
            client.cookies.update(cookies)
        return await client.request(**kwargs)


def _contains_nul(case: Case) -> bool:
    parts = (case.body, case.query, case.headers, case.cookies, case.path_parameters)
    return any(_value_has_nul(part) for part in parts)


def _value_has_nul(value: object) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, bytes | bytearray):
        return b"\x00" in value
    if isinstance(value, dict):
        return any(_value_has_nul(key) or _value_has_nul(item) for key, item in value.items())
    if isinstance(value, list | tuple):
        return any(_value_has_nul(item) for item in value)
    return False


def _http(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )
