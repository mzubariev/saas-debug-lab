from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    service_name: str = "notification-worker"
    kafka_bootstrap_servers: str
    log_level: str = "INFO"

    # SMTP delivery settings.
    # Default: Toxiproxy → MailHog (no auth, catches all mail locally).
    # Swap to a real provider (e.g. smtp.gmail.com:587 with STARTTLS) to deliver
    # to actual inboxes such as emailhook.site.
    smtp_host: str = "toxiproxy"
    smtp_port: int = 11025
    smtp_use_tls: bool = False       # Implicit TLS from first byte (port 465)
    smtp_use_starttls: bool = False  # Upgrade plain connection to TLS (port 587)
    smtp_username: str = ""
    smtp_password: str = ""

    # Email addresses used in every outbound notification.
    email_from: str = "notifications@saas-debug-lab.local"
    email_to: str = "change-me@emailhook.site"

    sentry_dsn: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
