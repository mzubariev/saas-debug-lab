"""Task HTTP API. The injected client's transport selects component or integration."""

from typing import cast
from uuid import UUID

import httpx
from pydantic import BaseModel

from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, ProblemBody
from saas_testkit.domain.tasks import Task, TaskCreate


class HttpTaskApi:
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None:
        self._client = client
        self._ctx = ctx

    async def create(self, body: TaskCreate) -> ApiResponse[Task]:
        return await self._send("POST", "/tasks", Task, body=body)

    async def submit(self, payload: dict[str, object]) -> ApiResponse[Task]:
        """POST `/tasks` with a caller-built JSON object (validation cases)."""
        return await self._send("POST", "/tasks", Task, payload=payload)

    async def list_tasks(self) -> ApiResponse[tuple[Task, ...]]:
        response = await self._client.request("GET", "/tasks", headers=self._ctx.headers())
        status, headers, elapsed, parsed = _parts(response)
        if not response.is_success:
            return ApiResponse(
                status=status,
                data=None,
                error=ProblemBody.model_validate(parsed),
                headers=headers,
                elapsed=elapsed,
            )
        rows = _rows(parsed)
        return ApiResponse(
            status=status,
            data=tuple(Task.model_validate(item) for item in rows),
            error=None,
            headers=headers,
            elapsed=elapsed,
        )

    async def get(self, task_id: UUID | str) -> ApiResponse[Task]:
        return await self._send("GET", f"/tasks/{task_id}", Task)

    async def start(self, task_id: UUID) -> ApiResponse[Task]:
        return await self._send("PATCH", f"/tasks/{task_id}/start", Task)

    async def complete(self, task_id: UUID) -> ApiResponse[Task]:
        return await self._send("PATCH", f"/tasks/{task_id}/complete", Task)

    async def _send[T: BaseModel](
        self,
        method: str,
        path: str,
        model: type[T],
        *,
        body: BaseModel | None = None,
        payload: dict[str, object] | None = None,
    ) -> ApiResponse[T]:
        document = payload if payload is not None else _document(body)
        response = await self._client.request(
            method,
            path,
            headers=self._ctx.headers(),
            json=document,
        )
        status, headers, elapsed, parsed = _parts(response)
        if response.is_success:
            return ApiResponse(
                status=status,
                data=model.model_validate(parsed),
                error=None,
                headers=headers,
                elapsed=elapsed,
                document=parsed,
            )
        return ApiResponse(
            status=status,
            data=None,
            error=ProblemBody.model_validate(parsed),
            headers=headers,
            elapsed=elapsed,
            document=parsed,
        )


def _rows(parsed: object) -> list[object]:
    if not isinstance(parsed, list):
        raise RuntimeError("task list was not a JSON array")
    rows: list[object] = []
    for item in cast(list[object], parsed):
        rows.append(item)
    return rows


def _document(body: BaseModel | None) -> object | None:
    if body is None:
        return None
    return cast(object, body.model_dump(mode="json"))


def _parts(response: httpx.Response) -> tuple[int, dict[str, str], float, object]:
    headers = {key: value for key, value in response.headers.items()}
    return (
        response.status_code,
        headers,
        response.elapsed.total_seconds(),
        cast(object, response.json()),
    )
