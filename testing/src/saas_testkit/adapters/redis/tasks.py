"""Task list and item cache. Keys match task-service: `tasks:list` and `tasks:{id}`."""

import json
from typing import cast
from uuid import UUID

from redis.asyncio import Redis


class TaskCache:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def item(self, task_id: UUID) -> dict[str, object] | None:
        return _mapping(await self._load(f"tasks:{task_id}"))

    async def put_item(self, task_id: UUID, body: dict[str, object]) -> None:
        await self._client.set(f"tasks:{task_id}", _dump(body), ex=120)

    async def drop_item(self, task_id: UUID) -> None:
        await self._client.delete(f"tasks:{task_id}")

    async def put_list(self, body: list[dict[str, object]]) -> None:
        await self._client.set("tasks:list", _dump(body), ex=60)

    async def drop_list(self) -> None:
        await self._client.delete("tasks:list")

    async def _load(self, key: str) -> object | None:
        raw = await self._client.get(key)
        if not isinstance(raw, str):
            return None
        try:
            return cast(object, json.loads(raw))
        except json.JSONDecodeError:
            return None


def _dump(body: object) -> str:
    return json.dumps(body)


def _mapping(value: object | None) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    parsed: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            return None
        parsed[key] = item
    return parsed
