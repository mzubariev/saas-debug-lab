from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.logging import install_request_context_middleware, install_unhandled_exception_middleware
from saas_shared.prometheus_http import install_http_metrics_middleware
from saas_shared.sentry_setup import setup_sentry_fastapi

from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry
from .infrastructure.messaging.producer import start_kafka_producer, stop_kafka_producer
from .api.routes import health, webhooks



setup_logging(service_name=settings.service_name, log_level=settings.log_level)

app = FastAPI(title="webhook-receiver", redirect_slashes=False)

setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn, app=app)

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
)


@app.on_event("startup")
async def startup() -> None:
    await start_kafka_producer(app)


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_kafka_producer(app)


app.include_router(health.router)
app.include_router(webhooks.router)

install_http_metrics_middleware(app)
install_request_context_middleware(app)
install_unhandled_exception_middleware(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
