from datetime import datetime, timedelta, timezone

import jwt
import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..dependencies import get_db
from ..models.user import User
from ..schemas.auth import TokenResponse, UserInfo
from ..security import verify_password
from ..cache import cache_get, cache_set


router = APIRouter(prefix="/auth")

logger = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_USER_CACHE_TTL = 300  # seconds


def _user_key(username: str) -> str:
    return f"user:{username}"


def _create_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    redis = request.app.state.redis
    key = _user_key(form.username)

    cached_user = await cache_get(redis, key)

    if cached_user is not None:
        logger.debug("cache_hit", key=key)
        hashed_password = cached_user["hashed_password"]
        role = cached_user["role"]
        username = cached_user["username"]
    else:
        result = await db.execute(select(User).where(User.username == form.username))
        user = result.scalar_one_or_none()

        if user is None:
            logger.warning("login_failed", username=form.username, reason="user_not_found")
            # Record the failed attempt as a Sentry breadcrumb so it appears
            # in the trail for any subsequent exception in the same request.
            sentry_sdk.add_breadcrumb(
                category="auth",
                message=f"Login failed: unknown user '{form.username}'",
                level="warning",
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        await cache_set(
            redis,
            key,
            {"username": user.username, "hashed_password": user.hashed_password, "role": user.role},
            ttl=_USER_CACHE_TTL,
        )

        hashed_password = user.hashed_password
        role = user.role
        username = user.username

    if not verify_password(form.password, hashed_password):
        logger.warning("login_failed", username=form.username, reason="wrong_password")
        sentry_sdk.add_breadcrumb(
            category="auth",
            message=f"Login failed: wrong password for '{form.username}'",
            level="warning",
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(username, role)

    # Tell Sentry which user is authenticated for the rest of this request.
    sentry_sdk.set_user({"username": username, "role": role})

    logger.info("login_success", username=username, role=role)

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserInfo)
async def get_me(token: str = Depends(oauth2_scheme)):

    payload = _decode_token(token)

    # Propagate user identity to any Sentry event raised downstream.
    sentry_sdk.set_user({"username": payload["sub"], "role": payload.get("role", "user")})

    return UserInfo(username=payload["sub"], role=payload.get("role", "user"))
