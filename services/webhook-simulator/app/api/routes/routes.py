import asyncio
import random
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from ...core.config import settings

router = APIRouter()

logger = structlog.get_logger()


class InboundTrigger(BaseModel):
    event: str
    data: dict[str, Any] = {}


@router.post("/receive-webhook")
async def receive_webhook(
    payload: dict[str, Any],
    response: Response,
    fail_rate: float | None = Query(default=None, ge=0.0, le=1.0),
    delay: float | None = Query(default=None, ge=0.0),
    status: int | None = Query(default=None),
) -> dict[str, Any]:
    """
    Acts as the external system receiving outbound webhooks from webhook-dispatcher.
    Supports per-request fail_rate, delay, and status overrides for chaos testing.
    """
    effective_fail_rate = fail_rate if fail_rate is not None else settings.default_fail_rate
    effective_delay = delay if delay is not None else settings.default_delay
    effective_status = status if status is not None else settings.default_status

    if effective_delay > 0:
        await asyncio.sleep(effective_delay)

    logger.info(
        "outbound_webhook_received",
        fail_rate=effective_fail_rate,
        delay=effective_delay,
        requested_status=effective_status,
    )

    if random.random() < effective_fail_rate:
        logger.warning("outbound_webhook_simulated_failure")
        response.status_code = 500
        return {"status": "error", "reason": "simulated_failure"}

    if effective_status != 200:
        response.status_code = effective_status
        return {"status": "custom_status", "code": effective_status}

    return {"status": "received", "payload": payload}


@router.post("/trigger-event", status_code=202)
async def trigger_event(
    body: InboundTrigger,
    retry: int = Query(default=0, ge=0),
    delay: float = Query(default=1.0, ge=0.0),
) -> dict[str, Any]:
    """
    Simulates an external system sending a webhook event inbound to integration-service (via api-gateway or direct URL).
    Retries on failure with exponential backoff.
    """
    asyncio.create_task(
        _send_with_retry(
            body.model_dump(),
            settings.integration_service_webhook_url,
            retry,
            delay,
        )
    )
    logger.info("inbound_trigger_queued", event=body.event, retry=retry, delay=delay)
    return {"status": "triggered", "event": body.event}


async def _send_with_retry(payload: dict[str, Any], url: str, retries: int, delay: float) -> None:
    async with httpx.AsyncClient() as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.post(url, json=payload, timeout=10.0)
                logger.info(
                    "inbound_trigger_sent",
                    url=url,
                    attempt=attempt,
                    status_code=resp.status_code,
                )
                if resp.is_success:
                    return
            except Exception as exc:
                logger.warning(
                    "inbound_trigger_attempt_failed",
                    url=url,
                    attempt=attempt,
                    error=str(exc),
                )
            if attempt < retries:
                await asyncio.sleep(delay * (2**attempt))

    logger.error("inbound_trigger_failed_permanently", url=url)
