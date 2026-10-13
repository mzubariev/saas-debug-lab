import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from ...dependencies import AuthServiceDep
from ...schemas.auth import TokenResponse, UserInfo
from ...services.auth_service import AuthService

router = APIRouter(prefix="/auth")

logger = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def login_form(form: OAuth2PasswordRequestForm = Depends()) -> OAuth2PasswordRequestForm:
    if "\x00" not in form.username:
        return form
    raise RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "username"),
                "msg": "Value error, NUL byte is not allowed",
                "input": form.username,
            }
        ]
    )


@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    service: AuthServiceDep,
    form: OAuth2PasswordRequestForm = Depends(login_form),
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
