from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...services import webhook_service

router = APIRouter()


class WebhookPayload(BaseModel):
    event: str
    data: dict = {}


@router.post("/webhooks/inbound", status_code=200)
async def receive_inbound_webhook(payload: WebhookPayload, request: Request):
    """
    Inbound webhook receiver — called by webhook-simulator's /trigger-event.
    Acknowledges the call and publishes the payload to Kafka for downstream consumers.
    """
    return await webhook_service.receive_inbound(
        request, event=payload.event, data=payload.data
    )


@router.post("/webhooks/send", status_code=202)
async def send_outbound_webhook(payload: WebhookPayload, request: Request):
    """
    Queue an outbound webhook for delivery. webhook-dispatcher consumes the message
    and performs HTTP delivery with retries / DLQ — same path as task_* events.
    """
    webhook_service.accept_outbound_send(request, event=payload.event, data=payload.data)
    return {"status": "accepted", "event": payload.event}
