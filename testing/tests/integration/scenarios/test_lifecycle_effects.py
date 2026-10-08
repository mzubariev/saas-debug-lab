"""S1: a task's create, start, and complete show up in Kafka, mail, and the webhook."""

from uuid import UUID

from saas_testkit.adapters.mail import MailHogInbox, MailMessage
from saas_testkit.adapters.wiremock import RecordedCall, WireMockSink
from saas_testkit.context import unique_title
from saas_testkit.domain import TaskCreatedPayload, TaskStatus, TaskUpdatedPayload
from saas_testkit.flows import TaskLifecycle, WebhookDelivery
from saas_testkit.polling import eventually

_WEBHOOKS = 3


async def test_created_task_reaches_kafka_mail_and_webhooks(
    lifecycle: TaskLifecycle,
    delivery: WebhookDelivery,
    mail: MailHogInbox,
    wiremock: WireMockSink,
) -> None:
    title = unique_title("task")
    await wiremock.stub_for_title(title)

    created = await lifecycle.create(title=title)
    assert created.status == 201
    assert created.data is not None
    task = created.data
    assert task.status == TaskStatus.created

    created_event = await delivery.task_created(task.id)
    created_payload = TaskCreatedPayload.model_validate(created_event.payload)
    assert created_payload.id == task.id
    assert created_payload.title == title
    assert created_payload.status == TaskStatus.created

    message = await eventually(
        lambda: _mail(mail, title),
        timeout=15,
        message=f"no mail containing {title}",
    )
    assert message is not None
    assert title in message.subject

    calls = await _webhooks(wiremock, task.id, 1)
    assert [call.idempotency_key for call in calls] == [str(task.id)]

    started = await lifecycle.start(task)
    assert started.status == 200
    assert started.data is not None
    assert started.data.status == TaskStatus.in_progress
    started_event = await delivery.task_updated(task.id)
    assert TaskUpdatedPayload.model_validate(started_event.payload).status == TaskStatus.in_progress

    completed = await lifecycle.complete(started.data)
    assert completed.status == 200
    assert completed.data is not None
    assert completed.data.status == TaskStatus.completed
    completed_event = await delivery.task_updated(task.id)
    assert TaskUpdatedPayload.model_validate(completed_event.payload).status == TaskStatus.completed

    # BUG-7: created and both updates share one Idempotency-Key, the task id.
    calls = await _webhooks(wiremock, task.id, _WEBHOOKS)
    assert len(calls) == _WEBHOOKS
    assert {call.idempotency_key for call in calls} == {str(task.id)}


async def _mail(inbox: MailHogInbox, title: str) -> MailMessage | None:
    found = await inbox.containing(title)
    if not found:
        return None
    return found[0]


async def _webhooks(sink: WireMockSink, task_id: UUID, count: int) -> tuple[RecordedCall, ...]:
    found = await eventually(
        lambda: _enough(sink, str(task_id), count),
        timeout=15,
        message=f"fewer than {count} webhooks for {task_id}",
    )
    assert found is not None
    return found


async def _enough(
    sink: WireMockSink, payload_id: str, count: int
) -> tuple[RecordedCall, ...] | None:
    found = await sink.calls_for(payload_id)
    if len(found) < count:
        return None
    return found
