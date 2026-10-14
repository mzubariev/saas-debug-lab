"""Placeholder. Do not start ``consume``."""

from types import ModuleType


def test_module_imports_after_service_env(worker_module: ModuleType) -> None:
    assert worker_module.__name__ == "app.worker"
