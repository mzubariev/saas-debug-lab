from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    title: str


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str