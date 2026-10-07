"""User boundary models. Responses are tolerant of extra fields."""

from pydantic import BaseModel, ConfigDict


class UserInfo(BaseModel):
    """`GET /auth/me` returns `username` and `role` only."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    username: str
    role: str


class TokenResponse(BaseModel):
    """`POST /auth/token` body. `token_type` defaults to `bearer`."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: str
    token_type: str = "bearer"
