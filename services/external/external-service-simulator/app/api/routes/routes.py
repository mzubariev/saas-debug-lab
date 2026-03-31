import asyncio
import random
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel

from ...core.config import settings

router = APIRouter()

logger = structlog.get_logger()

# In-memory deduplication store.  Keyed on the Idempotency-Key header sent by
# webhook-dispatcher.  Only successfully processed (HTTP 200) deliveries are
# recorded so transient failures can be safely retried.
_processed_keys: set[str] = set()


class InboundTrigger(BaseModel):
    event: str
    data: dict[str, Any] = {}


@router.post("/receive-webhook")
async def receive_webhook(
    payload: dict[str, Any],
    request: Request,
    response: Response,
    fail_rate: float | None = Query(default=None, ge=0.0, le=1.0),
    delay: float | None = Query(default=None, ge=0.0),
    status: int | None = Query(default=None),
) -> dict[str, Any]:
    """
    Acts as the external system receiving outbound webhooks from webhook-dispatcher.
    Supports per-request fail_rate, delay, and status overrides for chaos testing.

    Idempotency: if the same ``Idempotency-Key`` was already processed successfully,
    return HTTP 200 ``{"status": "duplicate"}`` immediately so the caller knows the
    event was already handled and won't retry.
    """
    idempotency_key = request.headers.get("Idempotency-Key")

    if idempotency_key and idempotency_key in _processed_keys:
        logger.info(
            "outbound_webhook_duplicate",
            idempotency_key=idempotency_key,
            task_id=payload.get("id"),
        )
        return {"status": "duplicate", "idempotency_key": idempotency_key}

    effective_fail_rate = fail_rate if fail_rate is not None else settings.default_fail_rate
    effective_delay = delay if delay is not None else settings.default_delay
    effective_status = status if status is not None else settings.default_status

    if effective_delay > 0:
        await asyncio.sleep(effective_delay)

    logger.info(
        "outbound_webhook_received",
        idempotency_key=idempotency_key,
        fail_rate=effective_fail_rate,
        delay=effective_delay,
        requested_status=effective_status,
    )

    if random.random() < effective_fail_rate:
        logger.warning("outbound_webhook_simulated_failure", idempotency_key=idempotency_key)
        response.status_code = 500
        return {"status": "error", "reason": "simulated_failure"}

    if effective_status != 200:
        response.status_code = effective_status
        return {"status": "custom_status", "code": effective_status}

    # Record the key only after a successful (200) delivery so retries on
    # transient failures (5xx, network errors) are still processed.
    if idempotency_key:
        _processed_keys.add(idempotency_key)

    return {"status": "received", "payload": payload}


@router.post("/trigger-event", status_code=202)
async def trigger_event(
    body: InboundTrigger,
    retry: int = Query(default=0, ge=0),
    delay: float = Query(default=1.0, ge=0.0),
) -> dict[str, Any]:
    """
    Simulates an external system sending a webhook event inbound to webhook-receiver (via api-gateway or direct URL).
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
                    max_retries=retries,
                    error=str(exc)
                )
            if attempt < retries:
                await asyncio.sleep(delay * (2**attempt))

    logger.error(
        "inbound_trigger_failed_permanently",
        url=url,
        total_attempts=retries + 1,
    )
