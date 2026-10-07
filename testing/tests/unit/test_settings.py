"""Self-tests for kit settings and the service catalogue."""

import pytest
from pydantic import ValidationError

from saas_testkit.config import (
    POSTGRES_IMAGE,
    SERVICES,
    KitSettings,
    repo_root,
    service_environment,
)
from saas_testkit.factories import LAB_JWT_SECRET


def test_blank_urls_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRA", "OFF")
    monkeypatch.setenv("TEST_PG_URL", "")
    monkeypatch.setenv("TEST_REDIS_URL", "")
    monkeypatch.setenv("TEST_KAFKA_BOOTSTRAP", "")

    settings = KitSettings()

    assert settings.infra == "off"
    assert settings.test_pg_url is None
    assert settings.test_redis_url is None
    assert settings.test_kafka_bootstrap is None


def test_settings_read_connection_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PG_URL", "postgresql://postgres:test@localhost:5432/postgres")
    monkeypatch.setenv("TEST_REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("TEST_KAFKA_BOOTSTRAP", "localhost:9092")
    monkeypatch.delenv("INFRA", raising=False)

    settings = KitSettings()

    assert settings.infra == "auto"
    assert settings.test_pg_url == "postgresql://postgres:test@localhost:5432/postgres"
    assert settings.test_redis_url == "redis://localhost:6379"
    assert settings.test_kafka_bootstrap == "localhost:9092"


def test_unknown_infra_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRA", "containers")

    with pytest.raises(ValidationError):
        KitSettings()


def test_postgres_image_matches_the_lab_major() -> None:
    assert POSTGRES_IMAGE == "postgres:15"


def test_catalogue_covers_the_component_services() -> None:
    assert set(SERVICES) == {
        "task-service",
        "auth-service",
        "api-gateway",
        "webhook-receiver",
        "external-service-simulator",
        "webhook-dispatcher",
        "notification-worker",
        "scheduler-worker",
    }


def test_service_env_map_uses_one_jwt_secret() -> None:
    assert SERVICES["auth-service"].env["JWT_SECRET"] == LAB_JWT_SECRET
    assert SERVICES["api-gateway"].env["JWT_SECRET"] == LAB_JWT_SECRET
    assert service_environment("task-service", redis_url="redis://localhost:6379/0") == {}
    celery = service_environment("scheduler-worker", redis_url="redis://localhost:6379/4")
    assert celery["CELERY_BROKER_URL"] == "redis://localhost:6379/4"
    assert celery["CELERY_RESULT_BACKEND"] == "redis://localhost:6379/4"
    assert set(SERVICES["api-gateway"].env) == {
        "AUTH_SERVICE_URL",
        "INTEGRATION_SERVICE_URL",
        "JWT_SECRET",
        "TASK_SERVICE_URL",
    }
    assert set(SERVICES["notification-worker"].env) == {"SMTP_HOST"}
    assert set(SERVICES["webhook-dispatcher"].env) == {"WEBHOOK_URL"}
    assert set(SERVICES["external-service-simulator"].env) == {"INTEGRATION_SERVICE_WEBHOOK_URL"}


def test_task_service_has_no_get_db_seam() -> None:
    spec = SERVICES["task-service"]

    assert spec.module == "app.main"
    assert spec.port == 8000
    assert spec.di_seams == ()
    assert (repo_root() / spec.path).is_dir()
    assert (repo_root() / "testing" / "pyproject.toml").is_file()
