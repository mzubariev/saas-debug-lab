import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.health import router as health_router

from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry
from .infrastructure.messaging.producer import start_kafka_producer, stop_kafka_producer
from .api.routes.webhooks import router as webhooks_router


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

app = FastAPI(title="integration-service")

setup_logging(settings.log_level, settings.service_name)
setup_telemetry(app, settings.service_name, settings.otlp_endpoint)


@app.on_event("startup")
async def startup() -> None:
    await start_kafka_producer(app)


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_kafka_producer(app)


app.include_router(health_router)
app.include_router(webhooks_router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
