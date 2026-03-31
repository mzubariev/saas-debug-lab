from datetime import datetime, timedelta, timezone

import jwt
import sentry_sdk
import structlog
from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.user import User
from ..repositories.user_repository import UserRepository
from ..schemas.auth import TokenResponse, UserInfo
from ..security import verify_password
from ..infrastructure.cache.client import cache_get, cache_set

logger = structlog.get_logger()

_USER_CACHE_TTL = 300  # seconds


def _user_key(username: str) -> str:
    return f"user:{username}"


class AuthService:
    """Login flow, JWT issue/decode, and Redis cache-aside for user rows.

    Does not import FastAPI beyond HTTPException for error signalling.
    """

    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self._repo = UserRepository(db)
        self._redis = redis

    def _create_token(self, username: str, role: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
        payload = {"sub": username, "role": role, "exp": expire}
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    @staticmethod
    def _decode_token(token: str) -> dict:
        try:
            return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as exc:
            logger.info("token_expired")
            raise HTTPException(status_code=401, detail="Token expired") from exc
        except jwt.InvalidTokenError as exc:
            logger.warning("token_invalid", error=str(exc))
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    async def login(self, username: str, password: str) -> TokenResponse:
        key = _user_key(username)

        cached_user = await cache_get(self._redis, key)

        if cached_user is not None:
            logger.debug("cache_hit", key=key)
            hashed_password = cached_user["hashed_password"]
            role = cached_user["role"]
            db_username = cached_user["username"]
        else:
            user = await self._repo.get_by_username(username)

            if user is None:
                logger.warning("login_failed", username=username, reason="user_not_found")
                sentry_sdk.add_breadcrumb(
                    category="auth",
                    message=f"Login failed: unknown user '{username}'",
                    level="warning",
                )
                raise HTTPException(status_code=401, detail="Invalid credentials")

            await cache_set(
                self._redis,
                key,
                {"username": user.username, "hashed_password": user.hashed_password, "role": user.role},
                ttl=_USER_CACHE_TTL,
            )

            hashed_password = user.hashed_password
            role = user.role
            db_username = user.username

        if not verify_password(password, hashed_password):
            logger.warning("login_failed", username=username, reason="wrong_password")
            sentry_sdk.add_breadcrumb(
                category="auth",
                message=f"Login failed: wrong password for '{username}'",
                level="warning",
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = self._create_token(db_username, role)

        sentry_sdk.set_user({"username": db_username, "role": role})

        logger.info("login_success", username=db_username, role=role)

        return TokenResponse(access_token=token)

    @staticmethod
    def user_info_from_token(token: str) -> UserInfo:
        """Decode JWT and build UserInfo — no DB / Redis (used by GET /auth/me)."""
        payload = AuthService._decode_token(token)
        username = payload["sub"]
        role = payload.get("role", "user")

        sentry_sdk.set_user({"username": username, "role": role})
        logger.debug("token_verified", username=username, role=role)

        return UserInfo(username=username, role=role)
