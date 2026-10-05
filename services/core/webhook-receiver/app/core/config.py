from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "webhook-receiver"
    kafka_bootstrap_servers: str

    # Inbound events published to Kafka for downstream consumers.
    topic_webhook_inbound: str = "webhook_inbound"

    otlp_endpoint: str = "http://otel-collector:4317"
    log_level: str = "INFO"
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
