from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "api-gateway"
    task_service_url: str
    auth_service_url: str
    integration_service_url: str
    jwt_secret: str
    gateway_timeout: float = 5.0
    otlp_endpoint: str = "http://otel-collector:4317"
    log_level: str = "INFO"
    sentry_dsn: str = ""
    # Comma-separated extras. Empty keeps the lab origins in main.py.
    cors_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
