from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "external-service-simulator"
    otlp_endpoint: str = "http://otel-collector:4317"
    integration_service_webhook_url: str = "http://api-gateway:8000/webhooks/inbound"
    default_fail_rate: float = 0.0
    default_delay: float = 0.0
    default_status: int = 200
    log_level: str = "INFO"
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
