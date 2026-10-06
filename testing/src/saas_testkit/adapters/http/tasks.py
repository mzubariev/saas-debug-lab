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

    async def get(self, task_id: UUID) -> ApiResponse[Task]:
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
    ) -> ApiResponse[T]:
        payload = None if body is None else cast(object, body.model_dump(mode="json"))
        response = await self._client.request(
            method,
            path,
            headers=self._ctx.headers(),
            json=payload,
        )
        parsed = cast(object, response.json())
        elapsed = response.elapsed.total_seconds()
        headers = {key: value for key, value in response.headers.items()}
        if response.is_success:
            return ApiResponse(
                status=response.status_code,
                data=model.model_validate(parsed),
                error=None,
                headers=headers,
                elapsed=elapsed,
            )
        return ApiResponse(
            status=response.status_code,
            data=None,
            error=ProblemBody.model_validate(parsed),
            headers=headers,
            elapsed=elapsed,
        )
