"""Webhook delivery steps. Waits only; retry timing and WireMock come later."""

from collections.abc import Callable
from uuid import UUID

from saas_testkit.adapters.kafka.reader import KafkaEventReader
from saas_testkit.domain.events import Envelope
from saas_testkit.polling import eventually

_TASK_CREATED = "task.created"
_TASK_UPDATED = "task.updated"
_WEBHOOK_INBOUND = "webhook.inbound"
_WEBHOOK_DLQ = "webhook.dlq"


def matches_task_id(task_id: UUID, event_type: str) -> Callable[[Envelope], bool]:
    """Kafka stores `payload.id` as a string. Compare with `str(task_id)`."""
    wanted = str(task_id)

    def match(envelope: Envelope) -> bool:
        return envelope.event_type == event_type and envelope.payload.get("id") == wanted

    return match


def matches_inbound_event(event: str) -> Callable[[Envelope], bool]:
    """`webhook.inbound` whose payload `event` is this call."""

    def match(envelope: Envelope) -> bool:
        return envelope.event_type == _WEBHOOK_INBOUND and envelope.payload.get("event") == event

    return match


class WebhookDelivery:
    def __init__(self, events: KafkaEventReader) -> None:
        self._events = events

    async def task_created(self, task_id: UUID) -> Envelope:
        """Wait for `task.created` whose payload id is this task. Does not assert."""
        reader = self._events
        return await eventually(
            lambda: reader.wait_for(
                "task_created",
                match=matches_task_id(task_id, _TASK_CREATED),
                timeout=0.2,
            ),
            timeout=10,
            interval=0,
            message=f"no {_TASK_CREATED} for {task_id}",
        )

    async def task_updated(self, task_id: UUID) -> Envelope:
        """Wait for `task.updated` whose payload id is this task. Does not assert."""
        reader = self._events
        return await eventually(
            lambda: reader.wait_for(
                "task_updated",
                match=matches_task_id(task_id, _TASK_UPDATED),
                timeout=0.2,
            ),
            timeout=10,
            interval=0,
            message=f"no {_TASK_UPDATED} for {task_id}",
        )

    async def inbound(self, event: str) -> Envelope:
        """Wait for `webhook.inbound` whose payload event is this call. Does not assert."""
        reader = self._events
        return await eventually(
            lambda: reader.wait_for(
                "webhook_inbound",
                match=matches_inbound_event(event),
                timeout=0.2,
            ),
            timeout=10,
            interval=0,
            message=f"no {_WEBHOOK_INBOUND} for {event}",
        )

    async def dead_letter(self, task_id: UUID) -> Envelope:
        """Wait for `webhook.dlq` whose payload id is this task. Does not assert."""
        reader = self._events
        return await eventually(
            lambda: reader.wait_for(
                "webhook_dlq",
                match=matches_task_id(task_id, _WEBHOOK_DLQ),
                timeout=0.2,
            ),
            timeout=10,
            interval=0,
            message=f"no {_WEBHOOK_DLQ} for {task_id}",
        )
