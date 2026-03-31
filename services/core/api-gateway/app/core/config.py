from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "api-gateway"
    task_service_url: str
    auth_service_url: str = "http://auth-service:8000"
    integration_service_url: str = "http://integration-service:8000"
    jwt_secret: str = "dev-secret-change-in-production"
    gateway_timeout: float = 5.0
    otlp_endpoint: str = "http://otel-collector:4317"
    log_level: str = "INFO"
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
