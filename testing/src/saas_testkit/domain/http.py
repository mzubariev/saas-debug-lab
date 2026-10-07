"""HTTP result returned by adapters. Flows and tests read it; adapters never assert."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


class ProblemDetail(BaseModel):
    """One FastAPI validation error. Extra keys (`input`, `ctx`) are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    loc: tuple[str | int, ...]
    msg: str
    type: str


class ProblemBody(BaseModel):
    """FastAPI error body. `detail` is a string or a list of validation errors."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    detail: str | list[ProblemDetail]


class StatusBody(BaseModel):
    """`GET /ready` returns `{"status": "ready"}`."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ApiResponse[T]:
    status: int
    data: T | None
    error: ProblemBody | None
    headers: dict[str, str]
    elapsed: float
    document: object | None = None
