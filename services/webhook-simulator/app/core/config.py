from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "webhook-simulator"
    otlp_endpoint: str = "http://jaeger:4317"
    integration_service_webhook_url: str = "http://integration-service:8000/webhooks/inbound"
    default_fail_rate: float = 0.0
    default_delay: float = 0.0
    default_status: int = 200
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
