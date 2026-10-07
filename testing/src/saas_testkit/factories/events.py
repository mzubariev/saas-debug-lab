"""Event envelopes. `.build()` does no I/O."""

from datetime import UTC, datetime
from uuid import uuid4

from polyfactory import Use
from polyfactory.factories.pydantic_factory import ModelFactory

from saas_testkit.domain.events import (
    Envelope,
    TaskCreatedPayload,
    TaskUpdatedPayload,
    WebhookDlqPayload,
    WebhookInboundPayload,
)


class TaskCreatedPayloadFactory(ModelFactory[TaskCreatedPayload]):
    __model__ = TaskCreatedPayload


class TaskUpdatedPayloadFactory(ModelFactory[TaskUpdatedPayload]):
    __model__ = TaskUpdatedPayload


def _empty_data() -> dict[str, object]:
    return {}


class WebhookInboundPayloadFactory(ModelFactory[WebhookInboundPayload]):
    __model__ = WebhookInboundPayload

    data = Use(_empty_data)


class WebhookDlqPayloadFactory(ModelFactory[WebhookDlqPayload]):
    __model__ = WebhookDlqPayload

    timestamp = Use(lambda: datetime.now(UTC).isoformat())


class TaskCreatedEnvelopeFactory(ModelFactory[Envelope]):
    __model__ = Envelope

    event_type = "task.created"
    version = "v1"
    trace_id = Use(lambda: uuid4().hex)
    timestamp = Use(lambda: datetime.now(UTC).isoformat())
    payload = Use(lambda: TaskCreatedPayloadFactory.build().model_dump(mode="json"))


class TaskUpdatedEnvelopeFactory(ModelFactory[Envelope]):
    __model__ = Envelope

    event_type = "task.updated"
    version = "v1"
    trace_id = Use(lambda: uuid4().hex)
    timestamp = Use(lambda: datetime.now(UTC).isoformat())
    payload = Use(lambda: TaskUpdatedPayloadFactory.build().model_dump(mode="json"))


class WebhookInboundEnvelopeFactory(ModelFactory[Envelope]):
    __model__ = Envelope

    event_type = "webhook.inbound"
    version = "v1"
    trace_id = Use(lambda: uuid4().hex)
    timestamp = Use(lambda: datetime.now(UTC).isoformat())
    payload = Use(lambda: WebhookInboundPayloadFactory.build().model_dump(mode="json"))


class WebhookDlqEnvelopeFactory(ModelFactory[Envelope]):
    __model__ = Envelope

    event_type = "webhook.dlq"
    version = "v1"
    trace_id = Use(lambda: uuid4().hex)
    timestamp = Use(lambda: datetime.now(UTC).isoformat())
    payload = Use(lambda: WebhookDlqPayloadFactory.build().model_dump(mode="json"))
