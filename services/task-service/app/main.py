import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from .config import settings
from .logging import setup_logging
from .routes import health, tasks
from .kafka import start_kafka, stop_kafka
from .cache import start_redis, stop_redis
from .telemetry import setup_telemetry


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

# Schema is created by Alembic (task-migrate init container) before startup.

app = FastAPI(title="task-service")

setup_logging(settings.log_level, settings.service_name)
setup_telemetry(app, settings.service_name, settings.otlp_endpoint)


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
