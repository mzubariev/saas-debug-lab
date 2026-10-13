from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from saas_shared.health import router as health_router
from saas_shared.logging import (
    install_request_context_middleware,
    install_unhandled_exception_middleware,
    setup_logging,
)
from saas_shared.metrics import router as metrics_router
from saas_shared.prometheus_http import install_http_metrics_middleware
from saas_shared.sentry_setup import setup_sentry_fastapi
from saas_shared.telemetry import setup_telemetry

from .api.routes import webhooks
from .core.config import settings
from .infrastructure.messaging.producer import start_kafka_producer, stop_kafka_producer


setup_logging(service_name=settings.service_name, log_level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        await start_kafka_producer(app)
        stack.push_async_callback(stop_kafka_producer, app)
        yield


app = FastAPI(title="webhook-receiver", redirect_slashes=False, lifespan=lifespan)

setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn, app=app)

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
)


app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(webhooks.router)

install_http_metrics_middleware(app)
install_request_context_middleware(app)
install_unhandled_exception_middleware(app)
