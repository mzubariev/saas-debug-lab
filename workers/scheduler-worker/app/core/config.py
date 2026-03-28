from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "scheduler-worker"
    log_level: str = "INFO"

    otlp_endpoint: str = "http://otel-collector:4317"

    metrics_port: int = 9100

    # Sentry error tracking. Leave empty to disable.
    sentry_dsn: str = ""

    # Celery broker and result backend.
    # Uses Redis DB 2 (DB 0 = task-service cache, DB 1 = auth-service cache).
    celery_broker_url: str = "redis://redis:6379/2"
    celery_result_backend: str = "redis://redis:6379/2"

    # Postgres — used by cleanup_old_tasks.
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # Kafka — used by retry_failed_webhooks to drain the DLQ topic.
    kafka_bootstrap_servers: str = "kafka:9092"

    # Webhook delivery target — used by retry_failed_webhooks.
    # Should match webhook-dispatcher’s WEBHOOK_URL so retried events
    # reach the same endpoint as the original delivery attempts.
    webhook_url: str = "http://webhook-simulator:8001/receive-webhook"
    webhook_timeout: int = 10

    # Tasks older than this many days (status=completed) will be deleted by
    # cleanup_old_tasks. Set to 0 to disable deletion.
    cleanup_completed_tasks_days: int = 30

    @computed_field
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
