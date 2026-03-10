from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    task_service_url: str
    gateway_timeout: float = 5.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()