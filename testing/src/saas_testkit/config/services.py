"""Service catalogue. One pytest session loads exactly one of these (ADR-1)."""

from dataclasses import dataclass, field
from pathlib import Path

from saas_testkit.config.paths import repo_root
from saas_testkit.factories.jwt import LAB_JWT_SECRET

# Redis ships 16 databases (0..15). `--maxprocesses=8` needs eight indexes per
# session, so only task-service (0..7) and auth-service (8..15) get a private
# block. A third block of eight does not fit.
REDIS_BLOCK_SIZE = 8
_REDIS_DB_MAX = 15

# Lab hosts from each service `.env.example`. `{redis_url}` is this worker's Redis URL.
_GATEWAY_ENV = {
    "JWT_SECRET": LAB_JWT_SECRET,
    "AUTH_SERVICE_URL": "http://auth-service:8000",
    "TASK_SERVICE_URL": "http://task-service:8000",
    "INTEGRATION_SERVICE_URL": "http://webhook-receiver:8000",
}
_AUTH_ENV = {"JWT_SECRET": LAB_JWT_SECRET}
_SIMULATOR_ENV = {"INTEGRATION_SERVICE_WEBHOOK_URL": "http://localhost/webhooks/inbound"}
_WEBHOOK_ENV = {"WEBHOOK_URL": "http://nginx/external/receive-webhook"}
_NOTIFICATION_ENV = {"SMTP_HOST": "toxiproxy"}
_SCHEDULER_ENV = {
    "WEBHOOK_URL": "http://nginx/external/receive-webhook",
    "CELERY_BROKER_URL": "{redis_url}",
    "CELERY_RESULT_BACKEND": "{redis_url}",
}


def _no_env() -> dict[str, str]:
    return {}


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceSpec:
    """Where a service lives and how a component session imports it.

    `di_seams` lists FastAPI dependencies a test may override. An empty tuple
    means the service builds its own engine from the environment, so tests
    leave `get_db` alone.

    `env` holds the required variables SUT_MAP lists on top of the connection
    settings `service_env` already sets. `redis_block` is the first Redis
    database index for this service; the worker index is added to it.
    """

    name: str
    path: Path
    module: str
    port: int | None = None
    di_seams: tuple[str, ...] = ()
    redis_block: int = 0
    env: dict[str, str] = field(default_factory=_no_env)

    def absolute_path(self) -> Path:
        return repo_root() / self.path


def _spec(
    name: str,
    path: str,
    module: str,
    *,
    port: int | None,
    di_seams: tuple[str, ...] = (),
    redis_block: int = 0,
    env: dict[str, str] | None = None,
) -> ServiceSpec:
    return ServiceSpec(
        name=name,
        path=Path(path),
        module=module,
        port=port,
        di_seams=di_seams,
        redis_block=redis_block,
        env=dict(env or {}),
    )


def service_environment(service: str, *, redis_url: str) -> dict[str, str]:
    """Required variables for `service`. `{redis_url}` becomes `redis_url`."""
    spec = SERVICES.get(service)
    if spec is None:
        return {}
    return {key: value.replace("{redis_url}", redis_url) for key, value in spec.env.items()}


def redis_db_index(service: str, worker: int) -> int:
    """Redis database for one service session and one xdist worker.

    Index is the service block plus the worker index. task-service and
    auth-service do not share an index while both run at `--maxprocesses=8`.
    """
    spec = SERVICES.get(service)
    block = 0 if spec is None else spec.redis_block
    index = block + worker
    if index > _REDIS_DB_MAX:
        raise ValueError(
            f"redis DB index {index} exceeds {_REDIS_DB_MAX} "
            f"({service or 'unknown'} block {block} + worker {worker})"
        )
    return index


SERVICES: dict[str, ServiceSpec] = {
    spec.name: spec
    for spec in (
        _spec("task-service", "services/core/task-service", "app.main", port=8000),
        _spec(
            "auth-service",
            "services/core/auth-service",
            "app.main",
            port=8000,
            redis_block=REDIS_BLOCK_SIZE,
            env=_AUTH_ENV,
        ),
        _spec(
            "api-gateway",
            "services/core/api-gateway",
            "app.main",
            port=8000,
            env=_GATEWAY_ENV,
        ),
        _spec("webhook-receiver", "services/core/webhook-receiver", "app.main", port=8000),
        _spec(
            "external-service-simulator",
            "services/external/external-service-simulator",
            "app.main",
            port=8000,
            env=_SIMULATOR_ENV,
        ),
        _spec(
            "webhook-dispatcher",
            "services/core/webhook-dispatcher",
            "app.run",
            port=9100,
            env=_WEBHOOK_ENV,
        ),
        _spec(
            "notification-worker",
            "workers/notification-worker",
            "app.worker",
            port=9100,
            env=_NOTIFICATION_ENV,
        ),
        _spec(
            "scheduler-worker",
            "workers/scheduler-worker",
            "app.core.celery",
            port=9100,
            env=_SCHEDULER_ENV,
        ),
    )
}
