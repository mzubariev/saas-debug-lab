"""Event-contract paths. Producer modules run only for their own `--service`."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from saas_testkit.domain.events import Envelope

_PRODUCERS = {
    "task_service": "task-service",
    "webhook_receiver": "webhook-receiver",
}
_DIR = Path(__file__).resolve().parents[3] / "contracts" / "events"


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    try:
        parts = collection_path.relative_to(config.rootpath).parts
    except ValueError:
        return None
    if len(parts) < 4 or parts[:3] != ("tests", "contract", "events"):
        return None
    expected = _PRODUCERS.get(parts[3])
    if expected is None:
        return None
    service = config.getoption("service")
    if service == expected:
        return None
    return True


@pytest.fixture(scope="session")
def event_contract_dir() -> Path:
    return _DIR


@pytest.fixture
def event_schema_errors() -> Callable[[str, Envelope], list[str]]:
    def check(name: str, envelope: Envelope) -> list[str]:
        schema = json.loads((_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
        document = json.loads(json.dumps(envelope.model_dump(mode="json")))
        if not isinstance(schema, dict) or not isinstance(document, dict):
            raise RuntimeError(f"{name} schema or event is not an object")
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        return [error.message for error in validator.iter_errors(document)]

    return check
