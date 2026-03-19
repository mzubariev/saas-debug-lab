import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from sqlalchemy import select

from .config import settings
from .db import engine, SessionLocal
from .logging import setup_logging
from .models.user import Base, User
from .security import hash_password
from .cache import start_redis, stop_redis
from .telemetry import setup_telemetry
from .routes import auth, health


app = FastAPI(title="auth-service")

setup_logging(settings.log_level, settings.service_name)
setup_telemetry(app, settings.service_name, settings.otlp_endpoint)

logger = structlog.get_logger()

# Default users seeded on every fresh database.
_DEFAULT_USERS: list[tuple[str, str, str]] = [
    ("admin", "admin123", "admin"),
    ("user",  "user123",  "user"),
]


@app.on_event("startup")
async def startup() -> None:

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        for username, password, role in _DEFAULT_USERS:
            result = await db.execute(select(User).where(User.username == username))
            if result.scalar_one_or_none() is None:
                db.add(User(
                    username=username,
                    hashed_password=hash_password(password),
                    role=role,
                ))

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
