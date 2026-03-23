from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db
from ...schemas.auth import TokenResponse, UserInfo
from ...services.auth_service import AuthService

router = APIRouter(prefix="/auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_auth_service(request: Request, db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db, request.app.state.redis)


@router.post("/token", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    return await service.login(form.username, form.password)


@router.get("/me", response_model=UserInfo)
async def get_me(token: str = Depends(oauth2_scheme)):
    return AuthService.user_info_from_token(token)
