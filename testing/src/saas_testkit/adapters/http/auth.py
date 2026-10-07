"""Auth HTTP API. The injected client's transport selects component or integration."""

from typing import cast

import httpx
from pydantic import BaseModel

from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, ProblemBody
from saas_testkit.domain.users import TokenResponse, UserInfo


class HttpAuthApi:
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None:
        self._client = client
        self._ctx = ctx

    async def login(self, username: str, password: str) -> ApiResponse[TokenResponse]:
        response = await self._client.post(
            "/auth/token",
            headers=self._ctx.headers(),
            data={"username": username, "password": password},
        )
        return _read(response, TokenResponse)

    async def me(self, token: str) -> ApiResponse[UserInfo]:
        headers = {**self._ctx.headers(), "Authorization": f"Bearer {token}"}
        response = await self._client.get("/auth/me", headers=headers)
        return _read(response, UserInfo)


def _read[T: BaseModel](response: httpx.Response, model: type[T]) -> ApiResponse[T]:
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
