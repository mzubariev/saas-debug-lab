"""Auth steps in business language. Preconditions check; the test checks the rest."""

from saas_testkit.adapters.http.auth import HttpAuthApi
from saas_testkit.adapters.redis.users import UserCache
from saas_testkit.domain.http import ApiResponse, StatusBody
from saas_testkit.domain.users import TokenResponse, UserInfo
from saas_testkit.factories.jwt import JwtFactory


class AuthFlow:
    def __init__(self, auth: HttpAuthApi, cache: UserCache | None = None) -> None:
        self._auth = auth
        self._cache = cache

    async def login(self, *, username: str, password: str) -> ApiResponse[TokenResponse]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._auth.login(username, password)

    async def submit_login(self, fields: dict[str, str]) -> ApiResponse[TokenResponse]:
        """Behaviour under test: a form that may omit `username` or `password`."""
        return await self._auth.submit_login(fields)

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

    async def me_as(self, kind: str, *, sub: str, role: str) -> ApiResponse[UserInfo]:
        """`/auth/me` with a valid, expired, tampered, unsigned, missing, or malformed header."""
        factory = JwtFactory()
        match kind:
            case "valid":
                return await self.me(factory.valid(sub=sub, role=role))
            case "expired":
                return await self.me(factory.expired(sub=sub, role=role))
            case "tampered":
                return await self.me(factory.tampered(sub=sub, role=role))
            case "alg_none":
                return await self.me(factory.alg_none(sub=sub, role=role))
            case "missing":
                return await self._auth.me_header(None)
            case "malformed":
                return await self._auth.me_header("Token abc")
            case _:
                raise ValueError(f"unknown token case {kind}")

    async def ready(self) -> ApiResponse[StatusBody]:
        """Behaviour under test: the caller asserts on the response."""
        return await self._auth.ready()

    async def cached_user(self, username: str) -> dict[str, object] | None:
        """The `user:{username}` entry, or `None` when Redis has no such key."""
        return await self._require_cache().user(username)

    async def replace_cached_role(self, username: str, role: str) -> None:
        """Overwrite the cached role so the next login shows whether Redis served it."""
        cache = self._require_cache()
        cached = await cache.user(username)
        if cached is None:
            raise AssertionError(f"user:{username} is not cached")
        await cache.put(username, {**cached, "role": role})

    def _require_cache(self) -> UserCache:
        if self._cache is None:
            raise RuntimeError("AuthFlow has no UserCache")
        return self._cache
