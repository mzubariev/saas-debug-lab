from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "webhook-dispatcher"
    kafka_bootstrap_servers: str = "kafka:9092"
    consumer_group: str = "webhook-dispatcher"

    webhook_url: str = "http://webhook-simulator:8001/receive-webhook"
    webhook_timeout: int = 10
    max_retries: int = 3

    log_level: str = "INFO"
    sentry_dsn: str = ""

    otlp_endpoint: str = "http://otel-collector:4317"

    metrics_port: int = 9100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()

# Topics consumed — task lifecycle events + manual dispatch queue from integration-service.
CONSUME_TOPICS: tuple[str, ...] = ("task_created", "task_updated", "webhook_dispatch")
