"""Auth HTTP API. The injected client's transport selects component or integration."""

from typing import cast

import httpx
from pydantic import BaseModel

from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, ProblemBody, StatusBody
from saas_testkit.domain.users import TokenResponse, UserInfo


class HttpAuthApi:
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None:
        self._client = client
        self._ctx = ctx

    async def login(self, username: str, password: str) -> ApiResponse[TokenResponse]:
        return await self.submit_login({"username": username, "password": password})

    async def submit_login(self, fields: dict[str, str]) -> ApiResponse[TokenResponse]:
        """POST `/auth/token` with a caller-built form (missing-field cases)."""
        response = await self._client.post(
            "/auth/token",
            headers=self._ctx.headers(),
            data=fields,
        )
        return _read(response, TokenResponse)

    async def me(self, token: str) -> ApiResponse[UserInfo]:
        return await self.me_header(f"Bearer {token}")

    async def me_header(self, authorization: str | None) -> ApiResponse[UserInfo]:
        """GET `/auth/me`. `None` omits `Authorization`."""
        headers = self._ctx.headers()
        if authorization is not None:
            headers = {**headers, "Authorization": authorization}
        response = await self._client.get("/auth/me", headers=headers)
        return _read(response, UserInfo)

    async def ready(self) -> ApiResponse[StatusBody]:
        response = await self._client.get("/ready", headers=self._ctx.headers())
        return _read(response, StatusBody)


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
            document=parsed,
        )
    return ApiResponse(
        status=response.status_code,
        data=None,
        error=ProblemBody.model_validate(parsed),
        headers=headers,
        elapsed=elapsed,
        document=parsed,
    )
