import structlog
import asyncio
from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..webhook import deliver

router = APIRouter()

logger = structlog.get_logger()


class WebhookPayload(BaseModel):
    event: str
    data: dict = {}


@router.post("/webhooks/inbound", status_code=200)
async def receive_inbound_webhook(payload: WebhookPayload):
    """
    Inbound webhook receiver — called by webhook-simulator's /trigger-event.
    Logs the received event and returns acknowledgement.
    """
    logger.info(
        "inbound_webhook_received",
        event=payload.event,
        data=payload.data,
    )
    return {"status": "received", "event": payload.event}


@router.post("/webhooks/send", status_code=202)
async def send_outbound_webhook(payload: WebhookPayload, request: Request):
    """
    Manually trigger an outbound webhook delivery to the configured WEBHOOK_URL.
    Useful for ad-hoc testing without waiting for a Kafka event.
    """

    asyncio.create_task(
        deliver(
            request.app.state.http_client,
            request.app.state.kafka_producer,
            {"event": payload.event, **payload.data},
        )
    )

    logger.info("outbound_webhook_triggered", event=payload.event)

    return {"status": "accepted", "event": payload.event}
