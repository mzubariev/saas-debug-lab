"""Service catalogue. One pytest session loads exactly one of these (ADR-1)."""

from dataclasses import dataclass
from pathlib import Path

from saas_testkit.config.paths import repo_root


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceSpec:
    """Where a service lives and how a component session imports it.

    `di_seams` lists FastAPI dependencies a test may override. An empty tuple
    means the service builds its own engine from the environment, so tests
    leave `get_db` alone.
    """

    name: str
    path: Path
    module: str
    port: int | None = None
    di_seams: tuple[str, ...] = ()

    def absolute_path(self) -> Path:
        return repo_root() / self.path


def _spec(
    name: str,
    path: str,
    module: str,
    *,
    port: int | None,
    di_seams: tuple[str, ...] = (),
) -> ServiceSpec:
    return ServiceSpec(
        name=name,
        path=Path(path),
        module=module,
        port=port,
        di_seams=di_seams,
    )


SERVICES: dict[str, ServiceSpec] = {
    spec.name: spec
    for spec in (
        _spec("task-service", "services/core/task-service", "app.main", port=8000),
        _spec("auth-service", "services/core/auth-service", "app.main", port=8000),
        _spec("api-gateway", "services/core/api-gateway", "app.main", port=8000),
        _spec("webhook-receiver", "services/core/webhook-receiver", "app.main", port=8000),
        _spec(
            "external-service-simulator",
            "services/external/external-service-simulator",
            "app.main",
            port=8000,
        ),
        _spec("webhook-dispatcher", "services/core/webhook-dispatcher", "app.run", port=9100),
        _spec("notification-worker", "workers/notification-worker", "app.worker", port=9100),
        _spec("scheduler-worker", "workers/scheduler-worker", "app.core.celery", port=9100),
    )
}
