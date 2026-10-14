"""Placeholder. Do not start the Celery worker."""

from types import ModuleType


def test_module_imports_after_service_env(worker_module: ModuleType) -> None:
    assert worker_module.__name__ == "app.core.celery"
