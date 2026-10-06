"""Decide when the controller starts infrastructure, and name xdist workers."""

from pathlib import Path

import pytest

from saas_testkit.config.settings import KitSettings

# These layers use the compose stack. They must not start Testcontainers or build a template.
_SHARED_STACK = frozenset({"integration", "e2e_ui", "smoke", "synthetic"})


def is_worker(config: pytest.Config) -> bool:
    """True inside an xdist worker process. The controller has no ``workerinput``."""
    return hasattr(config, "workerinput")


def worker_index(worker_id: str) -> int:
    """``gw0`` -> 0. A non-xdist run (``master``) uses Redis DB 0."""
    if worker_id == "master":
        return 0
    if worker_id.startswith("gw") and worker_id.removeprefix("gw").isdigit():
        return int(worker_id.removeprefix("gw"))
    raise ValueError(f"unrecognised xdist worker id: {worker_id}")


def needs_infra(config: pytest.Config) -> bool:
    """True only for a ``--service`` session or ``INFRA=on``.

    ``integration``, ``e2e_ui``, ``smoke``, and ``synthetic`` never start containers,
    even when one of those switches is set.
    """
    service = config.getoption("service")
    selected = service if isinstance(service, str) and service else None
    args = tuple(str(arg) for arg in config.args)
    return infra_required(
        infra_mode=KitSettings().infra,
        service=selected,
        args=args,
        root=Path(str(config.rootpath)),
    )


def infra_required(
    *,
    infra_mode: str,
    service: str | None,
    args: tuple[str, ...],
    root: Path,
) -> bool:
    if _targets_shared_stack(args, root):
        return False
    if service:
        return True
    return infra_mode == "on"


def _targets_shared_stack(args: tuple[str, ...], root: Path) -> bool:
    return any(_layer(arg, root) in _SHARED_STACK for arg in args)


def _layer(arg: str, root: Path) -> str | None:
    raw = arg.split("::", 1)[0]
    path = Path(raw)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            return None
    if len(path.parts) >= 2 and path.parts[0] == "tests":
        return path.parts[1]
    return None
