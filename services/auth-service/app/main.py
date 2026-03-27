import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.sentry_setup import setup_sentry_fastapi

from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry
from .infrastructure.db.session import SessionLocal
from .infrastructure.cache.client import start_redis, stop_redis
from .models.user import User
from .repositories.user_repository import UserRepository
from .security import hash_password
from .api.routes import auth, health


setup_logging(service_name=settings.service_name, log_level=settings.log_level)
setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn)

app = FastAPI(title="auth-service")

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
    settings.otlp_datadog_endpoint,
)

logger = structlog.get_logger()

# Default users seeded on every fresh database.
# Schema is created by the shared `migrations` one-shot container before startup.
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

    logger.info("startup_complete")


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_redis(app)


app.include_router(health.router)
app.include_router(auth.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
