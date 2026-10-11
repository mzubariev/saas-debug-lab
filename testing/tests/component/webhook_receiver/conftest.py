"""webhook-receiver component fixtures. The app starts a Kafka producer and no database."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from saas_testkit.adapters.http import HttpWebhookApi
from saas_testkit.adapters.kafka import KafkaEventReader
from saas_testkit.context import RunContext
from saas_testkit.flows import InboundWebhook, WebhookDelivery


@pytest.fixture(scope="session")
def service_app(open_app_lifespan: object) -> FastAPI:
    if not isinstance(open_app_lifespan, FastAPI):
        raise RuntimeError("webhook-receiver did not expose a FastAPI app")
    return open_app_lifespan


@pytest.fixture
async def client(service_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=service_app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        service_app.dependency_overrides.clear()


@pytest.fixture
def inbound(
    client: httpx.AsyncClient,
    run_context: RunContext,
    events: KafkaEventReader,
) -> InboundWebhook:
    return InboundWebhook(HttpWebhookApi(client, run_context), WebhookDelivery(events))
