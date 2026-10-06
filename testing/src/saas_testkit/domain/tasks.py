"""Task boundary models. Field names and status values match task-service `TaskOut`."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TaskStatus(StrEnum):
    created = "created"
    in_progress = "in_progress"
    completed = "completed"


class TaskCreate(BaseModel):
    """Body of `POST /tasks`. Strict: this is what the tests send."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str


class Task(BaseModel):
    """`TaskOut`. Extra fields from the service are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: UUID
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
