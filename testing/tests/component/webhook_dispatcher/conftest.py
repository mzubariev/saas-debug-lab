"""webhook-dispatcher has no ASGI app. Import after service_env; do not open a lifespan."""

import importlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from types import ModuleType
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
import respx
from aiokafka import AIOKafkaProducer
from pytest_mock import MockerFixture

from saas_testkit.adapters.kafka import KafkaEventReader
from saas_testkit.context import unique_title
from saas_testkit.domain import TaskCreatedPayload
from saas_testkit.factories import TaskCreatedPayloadFactory
from saas_testkit.infra import Infra

# Pinned inside the 0..10% window so the sleep args are exact, not wall-clock.
_JITTERS = (0.05, 0.15)


@dataclass(frozen=True, slots=True)
class _Message:
    value: bytes
    topic: str = "task_created"
    partition: int = 0
    offset: int = 0
    headers: tuple[tuple[str, bytes], ...] | None = None


@pytest.fixture(scope="session", autouse=True)
def worker_module(service_env: None) -> ModuleType:
    """Import ``app.run`` only after this worker's environment is set."""
    return importlib.import_module("app.run")


@pytest.fixture
def flush_redis() -> None:
    """Dispatcher does not use Redis. Leave the shared block alone."""


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    """The client ``process_consumed_message`` posts with. respx answers it."""
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture(scope="session")
async def kafka_producer(
    infra: Infra,
    events: KafkaEventReader,
) -> AsyncIterator[AIOKafkaProducer]:
    """Real producer. ``events`` is already subscribed, so a DLQ record is not missed."""
    _ = events
    producer = AIOKafkaProducer(bootstrap_servers=infra.kafka_bootstrap)
    await producer.start()
    try:
        yield producer
    finally:
        await producer.stop()


@pytest.fixture(autouse=True)
def backoff(
    mocker: MockerFixture,
    worker_module: ModuleType,
) -> tuple[AsyncMock, MagicMock]:
    """Patch the two clocks the retry loop actually calls. No real wait."""
    _ = worker_module
    sleep = cast(
        AsyncMock,
        mocker.patch("app.services.dispatcher_service.asyncio.sleep", autospec=True),
    )
    uniform = cast(
        MagicMock,
        mocker.patch(
            "app.services.dispatcher_service.random.uniform",
            autospec=True,
            side_effect=list(_JITTERS),
        ),
    )
    return sleep, uniform


@pytest.fixture
def _task() -> tuple[TaskCreatedPayload, dict[str, object]]:
    task = TaskCreatedPayloadFactory.build(id=uuid4(), title=unique_title("hook"))
    return task, dict(task.model_dump(mode="json"))


@pytest.fixture
def _settings(worker_module: ModuleType) -> tuple[str, int, float]:
    """``WEBHOOK_URL``, ``MAX_RETRIES``, ``WEBHOOK_BACKOFF_BASE`` after ``service_env``."""
    _ = worker_module
    settings = importlib.import_module("app.core.config").settings
    return (
        cast(str, settings.webhook_url),
        cast(int, settings.max_retries),
        cast(float, settings.webhook_backoff_base),
    )


@pytest.fixture
def deliver(
    http_client: httpx.AsyncClient,
    kafka_producer: AIOKafkaProducer,
    _settings: tuple[str, int, float],
) -> Callable[..., Awaitable[tuple[httpx.Request, ...]]]:
    """Post one consumed record. ``producer`` overrides the real one."""
    webhook_url = _settings[0]

    async def _deliver(
        *,
        value: bytes,
        outcome: httpx.Response | Exception,
        producer: AIOKafkaProducer | MagicMock | None = None,
    ) -> tuple[httpx.Request, ...]:
        loaded = importlib.import_module("app.services.dispatcher_service")
        process = cast(
            Callable[[object, httpx.AsyncClient, AIOKafkaProducer], Awaitable[None]],
            loaded.process_consumed_message,
        )
        target = kafka_producer if producer is None else cast(AIOKafkaProducer, producer)
        async with respx.mock(assert_all_called=False) as router:
            route = router.post(webhook_url)
            if isinstance(outcome, Exception):
                route.mock(side_effect=outcome)
            else:
                route.mock(return_value=outcome)
            await process(_Message(value), http_client, target)
            return tuple(call.request for call in route.calls)

    return _deliver
