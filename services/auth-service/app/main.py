import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.sentry_setup import setup_sentry_fastapi
from saas_shared.telemetry import instrument_sqlalchemy_async_engine

from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry
from .infrastructure.cache.client import start_redis, stop_redis
from .infrastructure.db.session import engine
from .api.routes import auth, health


setup_logging(service_name=settings.service_name, log_level=settings.log_level)
setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn)

app = FastAPI(title="auth-service")

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
)
instrument_sqlalchemy_async_engine(engine)

logger = structlog.get_logger()


@app.on_event("startup")
async def startup() -> None:
    await start_redis(app, settings.redis_url)

    logger.info("startup_complete")


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_redis(app)


app.include_router(health.router)
app.include_router(auth.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
