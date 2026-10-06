"""Process settings for a test run. Connection URLs come from the environment."""

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Same major as infra/docker-compose.yml and testing/compose.deps.yml (ADR-18).
POSTGRES_IMAGE = "postgres:15"
REDIS_IMAGE = "redis:7"
REDPANDA_IMAGE = "docker.redpanda.com/redpandadata/redpanda:v26.2.2"

# postgres -c flags for every throwaway test Postgres (ADR-18).
POSTGRES_TEST_COMMAND = (
    "postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200"
)


class KitSettings(BaseSettings):
    """Env-or-container switches. Unset URLs mean the controller starts Testcontainers."""

    model_config = SettingsConfigDict(extra="forbid", frozen=True)

    infra: Literal["auto", "off", "on"] = "auto"
    test_pg_url: str | None = None
    test_redis_url: str | None = None
    test_kafka_bootstrap: str | None = None

    @field_validator("infra", mode="before")
    @classmethod
    def _normalise_infra(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("test_pg_url", "test_redis_url", "test_kafka_bootstrap", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if value == "":
            return None
        return value
