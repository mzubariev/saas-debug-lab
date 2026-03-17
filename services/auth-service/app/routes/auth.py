from datetime import datetime, timedelta, timezone

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..dependencies import get_db
from ..models.user import User
from ..schemas.auth import TokenResponse, UserInfo
from ..security import verify_password


router = APIRouter(prefix="/auth")

logger = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


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
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("login_failed", username=form.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(user.username, user.role)

    logger.info("login_success", username=user.username, role=user.role)

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserInfo)
async def get_me(token: str = Depends(oauth2_scheme)):

    payload = _decode_token(token)

    return UserInfo(username=payload["sub"], role=payload.get("role", "user"))
