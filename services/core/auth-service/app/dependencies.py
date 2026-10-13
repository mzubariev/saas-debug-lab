from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .infrastructure.db.session import SessionLocal
from .services.auth_service import AuthService


async def get_db():
    async with SessionLocal() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_auth_service(request: Request, db: DbSession) -> AuthService:
    return AuthService(db, request.app.state.redis)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
