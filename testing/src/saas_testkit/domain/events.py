"""Consumer-side Kafka envelope. Tolerant of fields the producer may add."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from saas_testkit.domain.tasks import TaskStatus


class Envelope(BaseModel):
    """V1 envelope, or `event_type="unknown"` when the message is not one (SUT_MAP)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    event_type: str
    version: str | None = None
    trace_id: str | None = None
    timestamp: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class TaskCreatedPayload(BaseModel):
    """`task_created` business payload. `id`, `title`, `status` (SUT_MAP)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    status: TaskStatus


class TaskUpdatedPayload(BaseModel):
    """`task_updated` business payload. Same fields as `task_created` (SUT_MAP)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    status: TaskStatus


class WebhookInboundPayload(BaseModel):
    """`webhook_inbound` business payload. `event` and `data` (SUT_MAP)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: str
    data: dict[str, object] = Field(default_factory=dict)


class WebhookDlqPayload(BaseModel):
    """`webhook_dlq` payload: task fields plus `error`, `attempts`, `timestamp`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    status: TaskStatus
    error: str
    attempts: int
    timestamp: str
