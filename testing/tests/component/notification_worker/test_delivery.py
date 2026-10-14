"""Notification mail. Call ``consume`` with a stand-in consumer; do not open SMTP."""

import json
from collections.abc import Awaitable, Callable
from email.message import Message
from email.mime.multipart import MIMEMultipart
from types import ModuleType
from typing import cast

import pytest
from saas_shared.kafka_envelope import encode_envelope_bytes
from saas_shared.prometheus_metrics import emails_total
from tests.component.notification_worker.conftest import MailSettings

from saas_testkit.domain import TaskCreatedPayload

type Notify = Callable[..., Awaitable[tuple[MIMEMultipart, ...]]]
type TaskEvent = Callable[[], tuple[TaskCreatedPayload, dict[str, object]]]

_SMTP_FAILURES = [
    pytest.param("smtp", "smtp_error", id="smtp"),
    pytest.param("connection", "connection_error", id="connection"),
]


def _emails(status: str, provider: str) -> float:
    for family in emails_total.collect():
        for sample in family.samples:
            if (
                sample.name == "emails_total"
                and sample.labels.get("status") == status
                and sample.labels.get("provider") == provider
            ):
                return float(sample.value)
    return 0.0


def _failure(worker_module: ModuleType, kind: str) -> BaseException:
    match kind:
        case "smtp":
            smtp = cast(ModuleType, worker_module.aiosmtplib)
            exc = cast(type[BaseException], smtp.SMTPException)
            return exc("smtp down")
        case "connection":
            return OSError("connection refused")
        case _:
            raise AssertionError(kind)


def _text(message: MIMEMultipart, content_type: str) -> str:
    payload = message.get_payload()
    assert isinstance(payload, list)
    bodies: list[bytes] = []
    for part in payload:
        if not isinstance(part, Message) or part.get_content_type() != content_type:
            continue
        body = part.get_payload(decode=True)
        assert isinstance(body, bytes)
        bodies.append(body)
    assert len(bodies) == 1
    return bodies[0].decode()


async def test_notification_sends_multipart_mail_when_a_task_is_created(
    notify: Notify,
    task_event: TaskEvent,
    mail_settings: MailSettings,
) -> None:
    task, body = task_event()
    before = _emails("success", mail_settings.smtp_host)

    messages = await notify([encode_envelope_bytes("task.created", body)])

    assert len(messages) == 1
    message = messages[0]
    assert message.get_content_type() == "multipart/alternative"
    assert message["Subject"] == f"[SaaS Debug Lab] Task created: {task.title}"
    assert message["From"] == mail_settings.email_from
    assert message["To"] == mail_settings.email_to
    assert task.title in _text(message, "text/plain")
    assert task.title in _text(message, "text/html")
    assert _emails("success", mail_settings.smtp_host) == before + 1


@pytest.mark.parametrize(("kind", "status"), _SMTP_FAILURES)
async def test_notification_sends_the_next_message_when_smtp_fails(
    notify: Notify,
    task_event: TaskEvent,
    worker_module: ModuleType,
    mail_settings: MailSettings,
    kind: str,
    status: str,
) -> None:
    first, first_body = task_event()
    second, second_body = task_event()
    before_error = _emails(status, mail_settings.smtp_host)
    before_ok = _emails("success", mail_settings.smtp_host)

    messages = await notify(
        [
            encode_envelope_bytes("task.created", first_body),
            encode_envelope_bytes("task.created", second_body),
        ],
        error=_failure(worker_module, kind),
    )

    assert len(messages) == 2
    assert messages[0]["Subject"] == f"[SaaS Debug Lab] Task created: {first.title}"
    assert messages[1]["Subject"] == f"[SaaS Debug Lab] Task created: {second.title}"
    assert second.title in _text(messages[1], "text/plain")
    assert second.title in _text(messages[1], "text/html")
    assert _emails(status, mail_settings.smtp_host) == before_error + 1
    assert _emails("success", mail_settings.smtp_host) == before_ok + 1


async def test_notification_sends_only_the_valid_mail_when_the_previous_message_is_poison(
    notify: Notify,
    task_event: TaskEvent,
) -> None:
    task, body = task_event()

    messages = await notify([b"{", encode_envelope_bytes("task.created", body)])

    assert len(messages) == 1
    assert messages[0]["Subject"] == f"[SaaS Debug Lab] Task created: {task.title}"
    assert task.title in _text(messages[0], "text/plain")
    assert task.title in _text(messages[0], "text/html")


async def test_notification_sends_mail_when_message_is_legacy(
    notify: Notify,
    task_event: TaskEvent,
) -> None:
    task, body = task_event()

    messages = await notify([json.dumps(body).encode()])

    assert len(messages) == 1
    assert messages[0]["Subject"] == f"[SaaS Debug Lab] Task created: {task.title}"
    assert task.title in _text(messages[0], "text/plain")
    assert task.title in _text(messages[0], "text/html")
