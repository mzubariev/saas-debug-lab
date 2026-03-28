from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "integration-service"
    kafka_bootstrap_servers: str = "kafka:9092"

    # Topics produced by this service (consumed by webhook-dispatcher and optional analytics).
    topic_webhook_inbound: str = "webhook_inbound"
    topic_webhook_dispatch: str = "webhook_dispatch"

    otlp_endpoint: str = "http://otel-collector:4317"
    log_level: str = "INFO"
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
