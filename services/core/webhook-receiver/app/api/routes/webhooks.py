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
    Inbound webhook receiver — called by external-service-simulator's /trigger-event.
    Acknowledges the call and publishes the payload to Kafka for downstream consumers.
    Outbound delivery is handled exclusively by webhook-dispatcher consuming Kafka topics.
    """
    return await webhook_service.receive_inbound(
        request, event=payload.event, data=payload.data
    )
