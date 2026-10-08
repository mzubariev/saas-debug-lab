"""OpenAPI document is valid, and the committed snapshot is exact (ADR-17)."""

import difflib
import json
from pathlib import Path
from typing import cast

import pytest
from httpx import AsyncClient
from openapi_spec_validator import validate

_DIR = Path(__file__).resolve().parents[3] / "contracts" / "openapi"


@pytest.fixture(scope="session")
def openapi_contract_dir() -> Path:
    return _DIR


async def test_openapi_document_is_valid(client: AsyncClient) -> None:
    document = await _document(client)

    validate(document)


async def test_openapi_matches_snapshot(
    client: AsyncClient,
    openapi_contract_dir: Path,
    pytestconfig: pytest.Config,
) -> None:
    service = pytestconfig.getoption("service")
    if not isinstance(service, str) or not service:
        raise RuntimeError("contract/http needs --service")
    path = openapi_contract_dir / f"{service}.json"
    live = _canonical(_normalise(await _document(client)))
    if pytestconfig.getoption("update_contracts"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(live, encoding="utf-8")
        return
    committed = path.read_text(encoding="utf-8")
    assert live == committed, "".join(
        difflib.unified_diff(
            committed.splitlines(keepends=True),
            live.splitlines(keepends=True),
            fromfile="committed",
            tofile="live",
        )
    )


async def _document(client: AsyncClient) -> dict[str, object]:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("openapi.json was not an object")
    return cast(dict[str, object], body)


_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put", "trace"})


def _normalise(document: dict[str, object]) -> dict[str, object]:
    """Drop `servers`. Rewrite duplicate operationIds; FastAPI's suffix is not stable (BUG-6)."""
    cleaned = cast(dict[str, object], json.loads(json.dumps(document)))
    cleaned.pop("servers", None)
    _rewrite_duplicate_operation_ids(cleaned)
    return cleaned


def _rewrite_duplicate_operation_ids(document: dict[str, object]) -> None:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return
    counts: dict[str, int] = {}
    for item in paths.values():
        for operation in _operations(item).values():
            operation_id = operation.get("operationId")
            if isinstance(operation_id, str):
                counts[operation_id] = counts.get(operation_id, 0) + 1
    for path, item in paths.items():
        if not isinstance(path, str):
            continue
        for method, operation in _operations(item).items():
            operation_id = operation.get("operationId")
            if isinstance(operation_id, str) and counts.get(operation_id, 0) > 1:
                operation["operationId"] = f"{method} {path}"


def _operations(item: object) -> dict[str, dict[str, object]]:
    if not isinstance(item, dict):
        return {}
    found: dict[str, dict[str, object]] = {}
    for method, operation in item.items():
        if isinstance(method, str) and method in _METHODS and isinstance(operation, dict):
            found[method] = cast(dict[str, object], operation)
    return found


def _canonical(document: dict[str, object]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"
