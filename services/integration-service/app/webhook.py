import asyncio
import json
import random

import httpx
import structlog

from .config import settings

logger = structlog.get_logger()

_BACKOFF_BASE = 1.0  # seconds


async def deliver(
    client: httpx.AsyncClient,
    producer,
    payload: dict,
) -> None:
    """
    Attempt to deliver payload to the configured WEBHOOK_URL.

    Retries up to MAX_RETRIES times with exponential backoff.
    On permanent failure, publishes the payload to the webhook_dlq Kafka topic.
    """
    last_error: str = ""

    for attempt in range(1, settings.max_retries + 1):
        try:
            if settings.simulate_latency_ms > 0:
                await asyncio.sleep(settings.simulate_latency_ms / 1000)

            if random.random() < settings.simulate_failure_rate:
                raise httpx.RequestError("simulated_failure")

            resp = await client.post(
                settings.webhook_url,
                json=payload,
                timeout=settings.webhook_timeout,
            )
            resp.raise_for_status()

            logger.info(
                "webhook_sent",
                task_id=payload.get("id"),
                status_code=resp.status_code,
                attempt=attempt,
            )
            await _produce(producer, "webhook_sent", payload)
            return

        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_error = str(exc)
            logger.warning(
                "webhook_attempt_failed",
                task_id=payload.get("id"),
                attempt=attempt,
                max_retries=settings.max_retries,
                error=last_error,
            )

            if attempt < settings.max_retries:
                backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

    logger.error(
        "webhook_failed_permanently",
        task_id=payload.get("id"),
        error=last_error,
    )
    await _produce(producer, "webhook_failed", {**payload, "error": last_error})
    await _produce(producer, "webhook_dlq", {**payload, "error": last_error})


async def _produce(producer, topic: str, payload: dict) -> None:
    try:
        value = json.dumps(payload, default=str).encode("utf-8")
        await producer.send_and_wait(topic, value)
    except Exception as exc:
        logger.error("kafka_produce_failed", topic=topic, error=str(exc))
