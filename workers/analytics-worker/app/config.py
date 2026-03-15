from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "analytics-worker"
    kafka_bootstrap_servers: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
