"""Inbound + outbound webhook HTTP flows: publish to Kafka only (no HTTP delivery)."""

import asyncio

import sentry_sdk
import structlog
from fastapi import Request

from saas_shared.kafka_trace import current_trace_id_for_kafka_envelope

from ..core.config import settings
from ..infrastructure.messaging.producer import publish_json

logger = structlog.get_logger()


async def receive_inbound(request: Request, *, event: str, data: dict) -> dict:
    producer = request.app.state.kafka_producer
    try:
        await publish_json(
            producer,
            settings.topic_webhook_inbound,
            {"event": event, "data": data},
            event_type="webhook.inbound",
        )
    except Exception as exc:
        logger.error(
            "inbound_webhook_publish_failed",
            event=event,
            topic=settings.topic_webhook_inbound,
            error=str(exc)
        )
        sentry_sdk.capture_exception(exc)
        raise
    logger.info(
        "inbound_webhook_received",
        event=event,
        topic=settings.topic_webhook_inbound,
    )
    return {"status": "received", "event": event}


def accept_outbound_send(request: Request, *, event: str, data: dict) -> None:
    """Return immediately; publish to webhook_dispatch in the background."""
    producer = request.app.state.kafka_producer
    captured_trace_id = current_trace_id_for_kafka_envelope()
    asyncio.create_task(
        _enqueue_outbound(
            producer,
            event=event,
            data=data,
            trace_id=captured_trace_id,
        )
    )
    logger.info("outbound_webhook_accepted", event=event)


async def _enqueue_outbound(
    producer,
    *,
    event: str,
    data: dict,
    trace_id: str | None,
) -> None:
    payload = {"event": event, **data}
    try:
        await publish_json(
            producer,
            settings.topic_webhook_dispatch,
            payload,
            event_type="webhook.dispatch",
            trace_id=trace_id,
        )
    except Exception as exc:
        logger.error(
            "outbound_webhook_publish_failed",
            event=event,
            topic=settings.topic_webhook_dispatch,
            error=str(exc)
        )
        sentry_sdk.capture_exception(exc)
        return
    logger.info(
        "outbound_webhook_queued",
        event=event,
        topic=settings.topic_webhook_dispatch,
    )
