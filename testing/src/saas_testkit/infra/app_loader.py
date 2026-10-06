"""Put one service on ``sys.path`` and import its ASGI app.

Every service package is named ``app``, so a process loads only the service
selected with ``--service``. Import the app after ``service_env`` has set
``POSTGRES_*``, ``REDIS_URL``, and ``KAFKA_BOOTSTRAP_SERVERS``.
"""

import importlib
import sys
from pathlib import Path
from types import ModuleType

from saas_testkit.config.paths import repo_root
from saas_testkit.config.services import ServiceSpec


def install_service_paths(spec: ServiceSpec) -> None:
    """Insert ``shared/`` and the service directory at the front of ``sys.path``."""
    root = repo_root()
    shared = root / "shared"
    service = spec.absolute_path()
    if not shared.is_dir():
        raise FileNotFoundError(f"shared package is missing: {shared}")
    if not service.is_dir():
        raise FileNotFoundError(f"service directory is missing: {service}")
    entries = [str(shared), str(service)]
    for entry in entries:
        while entry in sys.path:
            sys.path.remove(entry)
    sys.path[:0] = entries


def import_service_app(spec: ServiceSpec) -> object:
    """Return ``spec.module.app``. The caller has already installed the service path."""
    _reject_foreign_app(spec.absolute_path())
    module = importlib.import_module(spec.module)
    app = module.__dict__.get("app")
    if app is None:
        raise RuntimeError(f"{spec.module} does not define an ASGI app")
    return app


def _reject_foreign_app(service_dir: Path) -> None:
    loaded = sys.modules.get("app")
    if loaded is None:
        return
    root = service_dir.resolve()
    origin = _module_origin(loaded)
    if origin is not None and (origin == root or origin.is_relative_to(root)):
        return
    where = str(origin) if origin is not None else "an unknown location"
    raise RuntimeError(f"app is already imported from {where}, not {root}")


def _module_origin(module: ModuleType) -> Path | None:
    file = getattr(module, "__file__", None)
    if isinstance(file, str):
        return Path(file).resolve()
    paths = getattr(module, "__path__", None)
    if paths is None:
        return None
    first = next(iter(paths), None)
    if isinstance(first, str):
        return Path(first).resolve()
    return None
