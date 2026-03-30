import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db
from ...schemas.auth import TokenResponse, UserInfo
from ...services.auth_service import AuthService

router = APIRouter(prefix="/auth")

logger = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_auth_service(request: Request, db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db, request.app.state.redis)


@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    # Emits one JSON object on stdout: includes request_id (middleware), trace_id (OTEL), message=event.
    logger.info(
        "auth_login_attempt",
        username=form.username,
        client_host=request.client.host if request.client else None,
    )
    return await service.login(form.username, form.password)


@router.get("/me", response_model=UserInfo)
async def get_me(token: str = Depends(oauth2_scheme)):
    return AuthService.user_info_from_token(token)
