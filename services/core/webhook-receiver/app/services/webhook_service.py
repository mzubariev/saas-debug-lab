"""Inbound webhook flow: receive HTTP call → publish to Kafka."""

import sentry_sdk
import structlog
from fastapi import Request

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
