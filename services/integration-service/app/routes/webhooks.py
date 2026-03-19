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


@router.post("/webhook/receive", status_code=200)
async def receive_webhook(payload: WebhookPayload):
    """
    Inbound webhook receiver — simulates an external system pushing events in.
    Logs the received event and returns acknowledgement.
    """
    logger.info(
        "webhook_received",
        event=payload.event,
        data=payload.data,
    )
    return {"status": "received", "event": payload.event}


@router.post("/external/send", status_code=202)
async def send_external(payload: WebhookPayload, request: Request):
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

    logger.info("external_send_triggered", event=payload.event)

    return {"status": "accepted", "event": payload.event}
