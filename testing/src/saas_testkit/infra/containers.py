"""Start Postgres, Redis, and Redpanda, or attach to URLs the environment already provides.

Testcontainers imports stay inside the start functions so unit tests can import
this module without a Docker daemon.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

from saas_testkit.config.settings import (
    POSTGRES_IMAGE,
    POSTGRES_TEST_COMMAND,
    REDIS_IMAGE,
    REDPANDA_IMAGE,
    KitSettings,
)
from saas_testkit.infra.template_db import ensure_template_database

logger = logging.getLogger("saas_testkit.containers")

# Postgres 15 keeps its data directory here. Postgres 18+ moves it; re-check on upgrade.
PGDATA = "/var/lib/postgresql/data"
_REDIS_DB_MAX = 15

# Topic names from SUT_MAP. Created before workers subscribe.
KAFKA_TOPICS = ("task_created", "task_updated", "webhook_inbound", "webhook_dlq")


class Stoppable(Protocol):
    """A Testcontainers container. Only ``stop`` is required."""

    def stop(self) -> None:
        """Stop and remove the container."""


class Infra(BaseModel):
    """Serializable URLs handed from the xdist controller to its workers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pg_admin_url: str
    redis_url: str
    kafka_bootstrap: str
    template_db: str
    service: str
    layer: str
    owned: bool

    def redis_url_for(self, index: int) -> str:
        return redis_url_for(self.redis_url, index)


@dataclass(slots=True)
class InfraHandle:
    """Controller-side handle. Workers only ever see :class:`Infra`."""

    info: Infra
    containers: tuple[Stoppable, ...] = ()

    def model_dump(self) -> dict[str, object]:
        return dict(self.info.model_dump())

    def stop(self) -> None:
        if not self.info.owned:
            return
        _stop(self.containers)


def redis_url_for(base: str, index: int) -> str:
    """Redis URL for one xdist worker. Indexes stay inside the default 16 databases."""
    if not 0 <= index <= _REDIS_DB_MAX:
        raise ValueError(f"redis DB index {index} is outside 0..{_REDIS_DB_MAX}")
    parts = urlsplit(base)
    if parts.scheme != "redis" or not parts.netloc:
        raise ValueError(f"not a redis URL: {base}")
    return urlunsplit((parts.scheme, parts.netloc, f"/{index}", "", ""))


def start_or_attach_infra(
    *,
    service: str,
    layer: str,
    settings: KitSettings | None = None,
) -> InfraHandle:
    """Use ``TEST_*`` URLs when they are set; otherwise start Testcontainers.

    Each resource is independent. The template database is created against whichever
    Postgres URL won. Containers started here are stopped by :meth:`InfraHandle.stop`.
    """
    chosen = settings if settings is not None else KitSettings()
    started: list[Stoppable] = []
    try:
        pg_url = chosen.test_pg_url or _start_postgres(started)
        redis_url = chosen.test_redis_url or _start_redis(started)
        kafka = chosen.test_kafka_bootstrap or _start_redpanda(started)
        template = ensure_template_database(pg_url)
        ensure_kafka_topics(kafka)
    except Exception:
        try:
            _stop(started)
        except Exception:
            logger.warning("failed to stop a test container during startup rollback", exc_info=True)
        raise
    info = Infra(
        pg_admin_url=pg_url,
        redis_url=_redis_base(redis_url),
        kafka_bootstrap=kafka,
        template_db=template,
        service=service,
        layer=layer,
        owned=bool(started),
    )
    return InfraHandle(info=info, containers=tuple(started))


def _start_postgres(started: list[Stoppable]) -> str:
    from testcontainers.community.postgres import PostgresContainer

    container = (
        PostgresContainer(
            POSTGRES_IMAGE,
            username="postgres",
            password="test",
            dbname="postgres",
            driver="psycopg",
        )
        .with_command(cast(list[str], POSTGRES_TEST_COMMAND.split()))
        .with_tmpfs_mount(PGDATA, "1g")
    )
    logger.info("starting testcontainers postgres %s", POSTGRES_IMAGE)
    container.start()
    started.append(container)
    return container.get_connection_url()


def _start_redis(started: list[Stoppable]) -> str:
    from testcontainers.community.redis import RedisContainer

    container = RedisContainer(REDIS_IMAGE)
    logger.info("starting testcontainers redis %s", REDIS_IMAGE)
    container.start()
    started.append(container)
    host = container.get_container_host_ip()
    port = container.get_exposed_port(container.port)
    return f"redis://{host}:{port}"


def ensure_kafka_topics(bootstrap: str) -> None:
    """Create the lab topics if they are missing. Safe when several sessions start together."""
    asyncio.run(_ensure_kafka_topics(bootstrap))


async def _ensure_kafka_topics(bootstrap: str) -> None:
    from aiokafka.admin import (  # pyright: ignore[reportMissingTypeStubs]
        AIOKafkaAdminClient,
        NewTopic,
    )

    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap)
    try:
        await admin.start()
        missing = [name for name in KAFKA_TOPICS if name not in set(await admin.list_topics())]
        if not missing:
            return
        await admin.create_topics(
            [NewTopic(name=name, num_partitions=1, replication_factor=1) for name in missing]
        )
        # A topic that already exists is success. Any other failure leaves it absent.
        still = [name for name in missing if name not in set(await admin.list_topics())]
        if still:
            raise RuntimeError(f"kafka topics were not created: {', '.join(still)}")
        logger.info("created kafka topics %s", ", ".join(missing))
    finally:
        await admin.close()


def _start_redpanda(started: list[Stoppable]) -> str:
    from testcontainers.community.kafka import RedpandaContainer

    container = RedpandaContainer(REDPANDA_IMAGE)
    logger.info("starting testcontainers redpanda %s", REDPANDA_IMAGE)
    container.start(timeout=90)
    started.append(container)
    return container.get_bootstrap_server()


def _redis_base(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _stop(containers: Sequence[Stoppable]) -> None:
    errors: list[Exception] = []
    for container in reversed(containers):
        try:
            container.stop()
        except Exception as exc:
            errors.append(exc)
            logger.warning("failed to stop a test container", exc_info=exc)
    if errors:
        raise errors[0]
