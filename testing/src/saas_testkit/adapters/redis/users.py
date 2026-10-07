"""User row cache. Key matches auth-service: `user:{username}`."""

import json
from typing import cast

from redis.asyncio import Redis

_TTL = 300


class UserCache:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def user(self, username: str) -> dict[str, object] | None:
        raw = await self._client.get(f"user:{username}")
        if not isinstance(raw, str):
            return None
        try:
            parsed = cast(object, json.loads(raw))
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        body: dict[str, object] = {}
        for key, item in cast(dict[object, object], parsed).items():
            if not isinstance(key, str):
                return None
            body[key] = item
        return body

    async def put(self, username: str, body: dict[str, object]) -> None:
        await self._client.set(f"user:{username}", json.dumps(body), ex=_TTL)
