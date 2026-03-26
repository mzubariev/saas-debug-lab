"""Standard Kafka event envelope for all lab producers/consumers.

Schema::

    {
        "event_type": "task.created | task.updated | webhook.failed | …",
        "version": "v1",
        "trace_id": "<32-char hex, W3C trace id; new messages use uuid4().hex>",
        "timestamp": "<iso8601>",
        "payload": { ... }
    }

Backward compatibility: messages that are not valid v1 envelopes are treated as
``event_type == "unknown"`` with the entire decoded object as ``payload``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

ENVELOPE_VERSION = "v1"


def build_envelope(
    event_type: str,
    payload: dict[str, Any],
    *,
    trace_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "version": ENVELOPE_VERSION,
        "trace_id": trace_id or uuid.uuid4().hex,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def encode_envelope_bytes(
    event_type: str,
    payload: dict[str, Any],
    *,
    trace_id: str | None = None,
) -> bytes:
    return json.dumps(
        build_envelope(event_type, payload, trace_id=trace_id),
        default=str,
    ).encode("utf-8")


def _is_v1_envelope(data: dict[str, Any]) -> bool:
    return (
        data.get("version") == ENVELOPE_VERSION
        and "event_type" in data
        and "payload" in data
        and isinstance(data.get("payload"), dict)
    )


def parse_envelope_message(data: Any) -> tuple[str, dict[str, Any], str | None]:
    """Parse a decoded Kafka JSON value into ``(event_type, business_payload, envelope_trace_id)``.

    ``envelope_trace_id`` is the top-level v1 ``trace_id`` field when present; use it with
    :func:`saas_shared.kafka_trace.attach_kafka_message_trace` on consumers.

    Accepts a ``dict`` (already parsed), or ``bytes``/``str`` JSON.
    Non-dict / invalid JSON → ``("unknown", {}, None)``.
    """
    parsed: Any
    if isinstance(data, dict):
        parsed = data
    elif isinstance(data, (bytes, bytearray)):
        try:
            parsed = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "unknown", {}, None
    elif isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return "unknown", {}, None
    else:
        return "unknown", {}, None

    if not isinstance(parsed, dict):
        return "unknown", {}, None

    if _is_v1_envelope(parsed):
        raw_tid = parsed.get("trace_id")
        tid = str(raw_tid) if raw_tid is not None else None
        return str(parsed["event_type"]), dict(parsed["payload"]), tid

    return "unknown", parsed, None
