"""Cross-layer pytest hooks.

Layer directories receive their marker here. Service path setup and
infrastructure stay in P1.
"""

from pathlib import Path

import pytest

_MARKERS: dict[str, pytest.MarkDecorator] = {
    "unit": pytest.mark.unit,
    "contract": pytest.mark.contract,
    "component": pytest.mark.component,
    "integration": pytest.mark.integration,
    "e2e_ui": pytest.mark.e2e_ui,
    "smoke": pytest.mark.smoke,
    "synthetic": pytest.mark.synthetic,
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--service",
        action="store",
        default=None,
        help="Service selected for a component or contract session.",
    )
    parser.addoption(
        "--update-contracts",
        action="store_true",
        default=False,
        help="Rewrite committed contract snapshots (ADR-17).",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = config.rootpath
    for item in items:
        marker = _marker_for(root, item.path)
        if marker is not None:
            item.add_marker(marker)


def _marker_for(root: Path, path: Path) -> pytest.MarkDecorator | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    if len(relative.parts) < 2 or relative.parts[0] != "tests":
        return None
    return _MARKERS.get(relative.parts[1])
