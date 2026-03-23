"""Inbound + outbound webhook HTTP flows: publish to Kafka only (no HTTP delivery)."""

import asyncio

import structlog
from fastapi import Request

from ..core.config import settings
from ..infrastructure.messaging.producer import publish_json

logger = structlog.get_logger()


async def receive_inbound(request: Request, *, event: str, data: dict) -> dict:
    producer = request.app.state.kafka_producer
    await publish_json(
        producer,
        settings.topic_webhook_inbound,
        {"event": event, "data": data},
    )
    logger.info(
        "inbound_webhook_received",
        event=event,
        data=data,
        topic=settings.topic_webhook_inbound,
    )
    return {"status": "received", "event": event}


def accept_outbound_send(request: Request, *, event: str, data: dict) -> None:
    """Return immediately; publish to webhook_dispatch in the background."""
    producer = request.app.state.kafka_producer
    asyncio.create_task(_enqueue_outbound(producer, event=event, data=data))
    logger.info("outbound_webhook_accepted", event=event)


async def _enqueue_outbound(producer, *, event: str, data: dict) -> None:
    payload = {"event": event, **data}
    await publish_json(producer, settings.topic_webhook_dispatch, payload)
    logger.info(
        "outbound_webhook_queued",
        event=event,
        topic=settings.topic_webhook_dispatch,
    )
