from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "integration-service"
    kafka_bootstrap_servers: str = "kafka:9092"

    webhook_url: str = "https://webhook.site/91882952-7994-4afc-bce3-01bb1461ce71"
    webhook_timeout: int = 10
    max_retries: int = 3

    simulate_latency_ms: int = 0
    simulate_failure_rate: float = 0.0

    otlp_endpoint: str = "http://jaeger:4317"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
