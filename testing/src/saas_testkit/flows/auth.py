"""Auth steps in business language. Preconditions check; the test checks the rest."""

from saas_testkit.adapters.http.auth import HttpAuthApi
from saas_testkit.domain.http import ApiResponse
from saas_testkit.domain.users import TokenResponse, UserInfo


class AuthFlow:
    def __init__(self, auth: HttpAuthApi) -> None:
        self._auth = auth

    async def login(self, *, username: str, password: str) -> ApiResponse[TokenResponse]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._auth.login(username, password)

    async def logged_in(self, *, username: str, password: str) -> TokenResponse:
        """Precondition. Raises if login does not return 200."""
        response = await self.login(username=username, password=password)
        if response.status != 200 or response.data is None:
            detail = None if response.error is None else response.error.detail
            raise AssertionError(f"expected 200, got {response.status}: {detail}")
        return response.data

    async def me(self, token: str) -> ApiResponse[UserInfo]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._auth.me(token)
