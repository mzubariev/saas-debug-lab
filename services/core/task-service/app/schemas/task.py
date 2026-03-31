import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.task import TaskStatus


class TaskCreate(BaseModel):
    title: str


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime