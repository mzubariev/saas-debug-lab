"""Self-tests for database names, Redis indexes, and the infra gate. No Docker."""

import sys
import types

import pytest

from saas_testkit.config.paths import repo_root
from saas_testkit.config.services import SERVICES, redis_db_index
from saas_testkit.infra.app_loader import import_service_app, install_service_paths
from saas_testkit.infra.containers import Infra, redis_url_for
from saas_testkit.infra.template_db import (
    DbUrls,
    quote_ident,
    read_alembic_head,
    template_database_name,
    worker_database_name,
)
from saas_testkit.infra.xdist import infra_required, worker_index


def test_worker_database_name_matches_the_visible_name() -> None:
    assert worker_database_name("task-service", "component", "gw0") == (
        "test_task_service_component_gw0"
    )
    assert worker_database_name("task-service", "component", "gw1") == (
        "test_task_service_component_gw1"
    )


def test_template_database_name_uses_the_alembic_head() -> None:
    assert template_database_name("0002") == "app_template_0002"
    assert read_alembic_head() == "0002"


def test_quote_ident_rejects_unsafe_names() -> None:
    assert quote_ident("tasks") == '"tasks"'
    with pytest.raises(ValueError, match="unsafe SQL identifier"):
        quote_ident("task-service")


def test_db_urls_split_the_admin_url() -> None:
    urls = DbUrls.for_database(
        "postgresql://postgres:p%40ss@localhost:5432/postgres",
        "app_template_0002",
    )

    assert urls.postgres_env() == {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "app_template_0002",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "p@ss",
    }
    assert urls.async_url == "postgresql+asyncpg://postgres:p%40ss@localhost:5432/app_template_0002"
    assert urls.sync_url == "postgresql+psycopg://postgres:p%40ss@localhost:5432/app_template_0002"


def test_redis_url_for_replaces_any_existing_index() -> None:
    assert redis_url_for("redis://localhost:6379", 0) == "redis://localhost:6379/0"
    assert redis_url_for("redis://localhost:6379/4", 2) == "redis://localhost:6379/2"


def test_redis_url_for_rejects_indexes_past_the_default_database_count() -> None:
    with pytest.raises(ValueError, match=r"outside 0\.\.15"):
        redis_url_for("redis://localhost:6379", 16)


def test_redis_db_index_keeps_task_and_auth_apart() -> None:
    task = [redis_db_index("task-service", worker) for worker in range(8)]
    auth = [redis_db_index("auth-service", worker) for worker in range(8)]

    assert task == list(range(8))
    assert auth == list(range(8, 16))
    assert set(task).isdisjoint(auth)


def test_redis_db_index_for_worker_zero_stays_in_range() -> None:
    for name in SERVICES:
        assert 0 <= redis_db_index(name, 0) <= 15


def test_redis_db_index_rejects_an_index_above_15() -> None:
    with pytest.raises(ValueError, match=r"exceeds 15 \(auth-service block 8 \+ worker 8\)"):
        redis_db_index("auth-service", 8)


def test_worker_index_maps_gw_and_master() -> None:
    assert worker_index("master") == 0
    assert worker_index("gw0") == 0
    assert worker_index("gw3") == 3
    with pytest.raises(ValueError, match="unrecognised"):
        worker_index("worker-1")


def test_infra_required_only_for_a_service_session_or_infra_on() -> None:
    root = repo_root()

    assert (
        infra_required(infra_mode="auto", service=None, args=("tests/component",), root=root)
        is False
    )
    assert infra_required(infra_mode="auto", service=None, args=("tests/unit",), root=root) is False
    assert infra_required(infra_mode="off", service=None, args=(), root=root) is False
    assert (
        infra_required(
            infra_mode="auto",
            service="task-service",
            args=("tests/component",),
            root=root,
        )
        is True
    )
    assert infra_required(infra_mode="on", service=None, args=("tests/unit",), root=root) is True
    assert infra_required(infra_mode="on", service=None, args=(), root=root) is True


def test_shared_stack_layers_never_need_infra() -> None:
    root = repo_root()

    for layer in ("integration", "e2e_ui", "smoke", "synthetic"):
        assert (
            infra_required(
                infra_mode="on",
                service="task-service",
                args=(f"tests/{layer}",),
                root=root,
            )
            is False
        )


def test_infra_round_trip() -> None:
    info = Infra(
        pg_admin_url="postgresql://postgres:test@localhost:5432/postgres",
        redis_url="redis://localhost:6379",
        kafka_bootstrap="localhost:9092",
        template_db="app_template_0002",
        service="task-service",
        layer="component",
        owned=False,
    )

    assert Infra.model_validate(info.model_dump()) == info
    assert info.redis_url_for(1) == "redis://localhost:6379/1"


def test_install_service_paths_puts_shared_then_the_service_first() -> None:
    before = list(sys.path)
    try:
        install_service_paths(SERVICES["task-service"])
        root = repo_root()
        assert sys.path[0] == str(root / "shared")
        assert sys.path[1] == str(SERVICES["task-service"].absolute_path())
        install_service_paths(SERVICES["task-service"])
        assert sys.path.count(str(root / "shared")) == 1
    finally:
        sys.path[:] = before


def test_shared_stack_absolute_path_never_needs_infra() -> None:
    root = repo_root()
    path = str(root / "tests" / "integration" / "test_flow.py")

    assert infra_required(infra_mode="on", service="task-service", args=(path,), root=root) is False


def test_import_service_app_rejects_a_foreign_package() -> None:
    foreign = types.ModuleType("app")
    foreign.__file__ = str(SERVICES["auth-service"].absolute_path() / "app" / "__init__.py")
    sys.modules["app"] = foreign
    try:
        with pytest.raises(RuntimeError, match="already imported"):
            import_service_app(SERVICES["task-service"])
    finally:
        sys.modules.pop("app", None)


def test_import_service_app_accepts_the_selected_service(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SERVICES["task-service"].absolute_path()
    package = types.ModuleType("app")
    package.__file__ = str(service / "app" / "__init__.py")
    sentinel = object()
    monkeypatch.setattr(
        "saas_testkit.infra.app_loader.importlib.import_module",
        lambda _name: types.SimpleNamespace(app=sentinel),
    )
    sys.modules["app"] = package
    try:
        assert import_service_app(SERVICES["task-service"]) is sentinel
    finally:
        sys.modules.pop("app", None)
