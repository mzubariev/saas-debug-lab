import re
import uuid
from datetime import datetime

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.task import TaskStatus

# NUL: Postgres rejects it. Lone surrogate: cannot be encoded into the 422 body.
_FORBIDDEN = re.compile("[\x00\ud800-\udfff]")


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)

    @field_validator("title", mode="before")
    @classmethod
    def reject_unsafe_chars(cls, value: object) -> object:
        if isinstance(value, str) and _FORBIDDEN.search(value):
            # Not ValueError: pydantic would echo the input into the 422 body.
            raise RequestValidationError(
                [{"type": "value_error", "loc": ("body", "title"),
                  "msg": "Title contains an unsupported character", "input": None}]
            )
        return value


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime