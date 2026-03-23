"""Async Redis JSON cache helpers shared by FastAPI services.

Used by auth-service (user row cache) and task-service (task list / single-task cache).
Install with ``pip install "saas-shared[services]"`` (pulls ``redis[asyncio]``).
"""

import json
from typing import Any

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis, from_url

logger = structlog.get_logger()


async def start_redis(app: FastAPI, redis_url: str) -> None:
    app.state.redis = await from_url(redis_url, encoding="utf-8", decode_responses=True)
    logger.info("redis_connected", url=redis_url)


async def stop_redis(app: FastAPI) -> None:
    await app.state.redis.aclose()
    logger.info("redis_disconnected")


async def cache_get(redis: Redis, key: str) -> dict[str, Any] | list[Any] | None:
    try:
        raw = await redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("cache_get_failed", key=key, error=str(exc))
        return None


async def cache_set(redis: Redis, key: str, value: dict[str, Any] | list[Any], ttl: int) -> None:
    try:
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        logger.warning("cache_set_failed", key=key, error=str(exc))


async def cache_delete(redis: Redis, *keys: str) -> None:
    try:
        await redis.delete(*keys)
    except Exception as exc:
        logger.warning("cache_delete_failed", keys=keys, error=str(exc))
