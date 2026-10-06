"""User boundary model. `GET /auth/me` returns `username` and `role` only."""

from pydantic import BaseModel, ConfigDict


class UserInfo(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    username: str
    role: str
