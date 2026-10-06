"""Consumer-side Kafka envelope. Tolerant of fields the producer may add."""

from pydantic import BaseModel, ConfigDict, Field


class Envelope(BaseModel):
    """V1 envelope, or `event_type="unknown"` when the message is not one (SUT_MAP)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    event_type: str
    version: str | None = None
    trace_id: str | None = None
    timestamp: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
