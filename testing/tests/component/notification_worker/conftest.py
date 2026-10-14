"""notification-worker has no ASGI app. Import after service_env; do not open a lifespan."""

import importlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from types import ModuleType
from typing import NamedTuple, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from saas_testkit.context import unique_title
from saas_testkit.domain import TaskCreatedPayload
from saas_testkit.factories import TaskCreatedPayloadFactory


@dataclass(frozen=True, slots=True)
class _Record:
    value: bytes
    topic: str = "task_created"
    partition: int = 0
    offset: int = 0
    headers: tuple[tuple[str, bytes], ...] | None = None


class _Feed:
    """Stand-in consumer. Yields the given records, then ends so ``consume`` returns."""

    def __init__(self, records: tuple[_Record, ...]) -> None:
        self._records = records

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[_Record]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[_Record]:
        for record in self._records:
            yield record


@pytest.fixture(scope="session", autouse=True)
def worker_module(service_env: None) -> ModuleType:
    """Import ``app.worker`` only after this worker's environment is set."""
    return importlib.import_module("app.worker")


@pytest.fixture
def flush_redis() -> None:
    """Notification-worker does not use Redis. Leave the shared block alone."""


class MailSettings(NamedTuple):
    email_from: str
    email_to: str
    smtp_host: str


@pytest.fixture
def mail_settings(worker_module: ModuleType) -> MailSettings:
    """``email_from``, ``email_to``, ``smtp_host`` after ``service_env``."""
    _ = worker_module
    settings = importlib.import_module("app.config").settings
    return MailSettings(
        email_from=cast(str, settings.email_from),
        email_to=cast(str, settings.email_to),
        smtp_host=cast(str, settings.smtp_host),
    )


@pytest.fixture
def task_event() -> Callable[[], tuple[TaskCreatedPayload, dict[str, object]]]:
    def _build() -> tuple[TaskCreatedPayload, dict[str, object]]:
        task = TaskCreatedPayloadFactory.build(id=uuid4(), title=unique_title("mail"))
        return task, dict(task.model_dump(mode="json"))

    return _build


@pytest.fixture
def notify(
    mocker: MockerFixture,
    worker_module: ModuleType,
) -> Callable[..., Awaitable[tuple[MIMEMultipart, ...]]]:
    """Run ``consume`` over these records. ``aiosmtplib.send`` is patched; nothing is sent."""
    send = cast(AsyncMock, mocker.patch("app.worker.aiosmtplib.send", autospec=True))

    async def _notify(
        values: list[bytes],
        *,
        error: BaseException | None = None,
    ) -> tuple[MIMEMultipart, ...]:
        pending: list[BaseException | None] = [None] * len(values)
        if error is not None:
            pending[0] = error

        async def _send(*_args: object, **_kwargs: object) -> None:
            outcome = pending.pop(0)
            if outcome is not None:
                raise outcome

        send.side_effect = _send
        records = tuple(_Record(value=value, offset=index) for index, value in enumerate(values))
        mocker.patch("app.worker.AIOKafkaConsumer", return_value=_Feed(records))
        await worker_module.consume()
        return tuple(cast(MIMEMultipart, call.args[0]) for call in send.await_args_list)

    return _notify
