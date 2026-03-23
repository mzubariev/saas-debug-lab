import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry
from .infrastructure.db.session import SessionLocal
from .infrastructure.cache.client import start_redis, stop_redis
from .models.user import User
from .repositories.user_repository import UserRepository
from .security import hash_password
from .api.routes import auth, health


def _setup_sentry() -> None:
    """Initialise Sentry error tracking. No-op when SENTRY_DSN is not set."""
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", settings.service_name)


_setup_sentry()

app = FastAPI(title="auth-service")

setup_logging(settings.log_level, settings.service_name)
setup_telemetry(app, settings.service_name, settings.otlp_endpoint)

logger = structlog.get_logger()

# Default users seeded on every fresh database.
# Schema is created by Alembic (auth-migrate init container) before startup.
_DEFAULT_USERS: list[tuple[str, str, str]] = [
    ("admin", "admin123", "admin"),
    ("user", "user123", "user"),
]


@app.on_event("startup")
async def startup() -> None:
    async with SessionLocal() as db:
        repo = UserRepository(db)
        for username, password, role in _DEFAULT_USERS:
            if await repo.get_by_username(username) is None:
                repo.add(
                    User(
                        username=username,
                        hashed_password=hash_password(password),
                        role=role,
                    )
                )
        await db.commit()

    await start_redis(app, settings.redis_url)

    logger.info("startup_complete", service=settings.service_name)


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_redis(app)


app.include_router(health.router)
app.include_router(auth.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
