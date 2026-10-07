"""Cross-layer pytest hooks.

Markers come from the test path. ``--service`` puts that service on ``sys.path``,
ignores the other component directories, and the controller starts infrastructure.
"""

from pathlib import Path

import pytest
from xdist.workermanage import WorkerController

from saas_testkit.config import SERVICES
from saas_testkit.infra import (
    InfraHandle,
    _layer,
    install_service_paths,
    is_worker,
    needs_infra,
    start_or_attach_infra,
)

_MARKERS: dict[str, pytest.MarkDecorator] = {
    "unit": pytest.mark.unit,
    "contract": pytest.mark.contract,
    "component": pytest.mark.component,
    "integration": pytest.mark.integration,
    "e2e_ui": pytest.mark.e2e_ui,
    "smoke": pytest.mark.smoke,
    "synthetic": pytest.mark.synthetic,
}
_LAYER_TIMEOUTS = {
    "component": 30,
    "contract": 120,
    "integration": 120,
    "e2e_ui": 120,
}
_INFRA_LAYERS = frozenset({"component", "contract"})


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--service",
        action="store",
        choices=sorted(SERVICES),
        default=None,
        help="Service selected for a component or contract session.",
    )
    parser.addoption(
        "--update-contracts",
        action="store_true",
        default=False,
        help="Rewrite committed contract snapshots (ADR-17).",
    )


def pytest_configure(config: pytest.Config) -> None:
    service = config.getoption("service")
    selected = service if isinstance(service, str) and service else None
    if selected is not None:
        install_service_paths(SERVICES[selected])
    if is_worker(config) or not needs_infra(config):
        return
    root = Path(config.rootpath)
    layer = "component"
    for arg in config.args:
        found = _layer(str(arg), root)
        if found in _INFRA_LAYERS:
            layer = found
            break
    config._infra = start_or_attach_infra(service=selected or "", layer=layer)  # type: ignore[attr-defined]


def pytest_configure_node(node: WorkerController) -> None:
    handle = getattr(node.config, "_infra", None)
    if isinstance(handle, InfraHandle):
        node.workerinput["infra"] = handle.model_dump()


def pytest_unconfigure(config: pytest.Config) -> None:
    handle = getattr(config, "_infra", None)
    if isinstance(handle, InfraHandle):
        handle.stop()


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    service = config.getoption("service")
    if not isinstance(service, str) or not service:
        return None
    try:
        parts = collection_path.relative_to(config.rootpath).parts
    except ValueError:
        return None
    if len(parts) < 3 or parts[0] != "tests" or parts[1] != "component":
        return None
    selected = service.replace("-", "_")
    if parts[2] in {selected, "conftest.py"}:
        return None
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = config.rootpath
    for item in items:
        layer = _layer_name(root, item.path)
        if layer is None:
            continue
        marker = _MARKERS.get(layer)
        if marker is not None:
            item.add_marker(marker)
        _apply_layer_timeout(item, layer)


def _layer_name(root: Path, path: Path) -> str | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    if len(relative.parts) < 2 or relative.parts[0] != "tests":
        return None
    return relative.parts[1]


def _apply_layer_timeout(item: pytest.Item, layer: str) -> None:
    seconds = _LAYER_TIMEOUTS.get(layer)
    if seconds is None or item.get_closest_marker("timeout") is not None:
        return
    item.add_marker(pytest.mark.timeout(seconds))
