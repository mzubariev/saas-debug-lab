"""Exact JSON-schema snapshots for the v1 envelope and each payload (ADR-17)."""

import difflib
import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from saas_testkit.domain.events import (
    Envelope,
    TaskCreatedPayload,
    TaskUpdatedPayload,
    WebhookDlqPayload,
    WebhookInboundPayload,
)

_EVENTS: dict[str, tuple[str, type[BaseModel]]] = {
    "task_created": ("task.created", TaskCreatedPayload),
    "task_updated": ("task.updated", TaskUpdatedPayload),
    "webhook_inbound": ("webhook.inbound", WebhookInboundPayload),
    "webhook_dlq": ("webhook.dlq", WebhookDlqPayload),
}


@pytest.mark.parametrize("name", tuple(_EVENTS))
def test_event_schema_matches_snapshot(
    name: str,
    event_contract_dir: Path,
    pytestconfig: pytest.Config,
) -> None:
    path = event_contract_dir / f"{name}.schema.json"
    live = _canonical(_live_schema(name))
    if pytestconfig.getoption("update_contracts"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(live, encoding="utf-8")
        return
    committed = path.read_text(encoding="utf-8")
    assert live == committed, _diff(committed, live)


def _live_schema(name: str) -> dict[str, object]:
    event_type, payload_model = _EVENTS[name]
    envelope = _object(Envelope.model_json_schema())
    payload = _object(payload_model.model_json_schema())
    defs = payload.pop("$defs", None)
    properties = _object(envelope["properties"])
    properties["event_type"] = {"const": event_type, "type": "string"}
    properties["version"] = {"const": "v1", "type": "string"}
    properties["trace_id"] = {"type": "string"}
    properties["timestamp"] = {"type": "string"}
    properties["payload"] = payload
    envelope["required"] = ["event_type", "version", "trace_id", "timestamp", "payload"]
    envelope["title"] = name
    if defs is not None:
        envelope["$defs"] = defs
    return envelope


def _canonical(schema: dict[str, object]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _diff(committed: str, live: str) -> str:
    return "".join(
        difflib.unified_diff(
            committed.splitlines(keepends=True),
            live.splitlines(keepends=True),
            fromfile="committed",
            tofile="live",
        )
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("expected a JSON object")
    return cast(dict[str, object], value)
