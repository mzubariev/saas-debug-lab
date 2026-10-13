from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import structlog
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
from saas_shared.telemetry import instrument_sqlalchemy_async_engine, setup_telemetry

from .api.routes import auth
from .core.config import settings
from .infrastructure.cache.client import start_redis, stop_redis
from .infrastructure.db.session import engine


setup_logging(service_name=settings.service_name, log_level=settings.log_level)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        await start_redis(app, settings.redis_url)
        stack.push_async_callback(stop_redis, app)
        logger.info("startup_complete")
        yield


app = FastAPI(title="auth-service", redirect_slashes=False, lifespan=lifespan)

setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn, app=app)

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
)
instrument_sqlalchemy_async_engine(engine)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(auth.router)

install_http_metrics_middleware(app)
install_request_context_middleware(app)
install_unhandled_exception_middleware(app)
