"""Self-tests for event payload models and envelope factories. No Docker."""

from uuid import uuid4

import pytest
from pydantic import BaseModel

from saas_testkit.domain import (
    Envelope,
    TaskCreatedPayload,
    TaskUpdatedPayload,
    WebhookDlqPayload,
    WebhookInboundPayload,
)
from saas_testkit.factories import (
    TaskCreatedEnvelopeFactory,
    TaskUpdatedEnvelopeFactory,
    WebhookDlqEnvelopeFactory,
    WebhookInboundEnvelopeFactory,
)
from saas_testkit.flows import matches_task_id

_CASES = [
    (TaskCreatedEnvelopeFactory, "task.created", TaskCreatedPayload),
    (TaskUpdatedEnvelopeFactory, "task.updated", TaskUpdatedPayload),
    (WebhookInboundEnvelopeFactory, "webhook.inbound", WebhookInboundPayload),
    (WebhookDlqEnvelopeFactory, "webhook.dlq", WebhookDlqPayload),
]


@pytest.mark.parametrize(("factory", "event_type", "model"), _CASES)
def test_envelope_factory_builds_v1_payload(
    factory: type[TaskCreatedEnvelopeFactory],
    event_type: str,
    model: type[BaseModel],
) -> None:
    envelope = factory.build()

    assert envelope.version == "v1"
    assert envelope.event_type == event_type
    model.model_validate(envelope.payload)


def test_matches_task_id_accepts_string_payload_for_uuid() -> None:
    task_id = uuid4()
    envelope = Envelope(event_type="task.created", payload={"id": str(task_id)})

    assert matches_task_id(task_id, "task.created")(envelope)
