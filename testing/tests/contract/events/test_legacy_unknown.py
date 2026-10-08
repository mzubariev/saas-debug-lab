"""A message that is not a v1 envelope becomes `unknown` (SUT_MAP)."""

import pytest
from saas_shared.kafka_envelope import parse_envelope_message

_LEGACY = {"id": "legacy"}
_PAYLOAD_NOT_OBJECT = {"event_type": "task.created", "payload": "x", "version": "v1"}


@pytest.mark.parametrize(
    ("message", "payload"),
    [
        pytest.param(_LEGACY, _LEGACY, id="legacy-object"),
        pytest.param(_PAYLOAD_NOT_OBJECT, _PAYLOAD_NOT_OBJECT, id="payload-not-object"),
        pytest.param(b"{", {}, id="invalid-json"),
        pytest.param(b"\xff", {}, id="not-utf8"),
        pytest.param("[]", {}, id="non-dict-json"),
        pytest.param(None, {}, id="not-a-message"),
    ],
)
def test_legacy_message_maps_to_unknown(message: object, payload: dict[str, object]) -> None:
    event_type, body, trace_id = parse_envelope_message(message)

    assert event_type == "unknown"
    assert body == payload
    assert trace_id is None
