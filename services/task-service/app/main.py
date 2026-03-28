from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.sentry_setup import setup_sentry_fastapi
from saas_shared.telemetry import instrument_sqlalchemy_async_engine

from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry
from .api.routes import health, tasks
from .infrastructure.messaging.producer import start_kafka, stop_kafka
from .infrastructure.cache.client import start_redis, stop_redis
from .infrastructure.db.session import engine


setup_logging(service_name=settings.service_name, log_level=settings.log_level)
setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn)

# Schema is created by the shared `migrations` one-shot container before startup.

app = FastAPI(title="task-service")

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
    settings.otlp_datadog_endpoint,
)
instrument_sqlalchemy_async_engine(engine)


@app.on_event("startup")
async def startup():
    await start_kafka(app)
    await start_redis(app, settings.redis_url)


@app.on_event("shutdown")
async def shutdown():
    await stop_kafka(app)
    await stop_redis(app)


app.include_router(health.router)
app.include_router(tasks.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
