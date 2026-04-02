import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.logging import install_request_context_middleware, install_unhandled_exception_middleware
from saas_shared.prometheus_http import install_http_metrics_middleware
from saas_shared.sentry_setup import setup_sentry_fastapi
from saas_shared.telemetry import instrument_sqlalchemy_async_engine

from saas_shared.health import router as health_router
from saas_shared.logging import setup_logging
from saas_shared.telemetry import setup_telemetry

from .core.config import settings
from .infrastructure.cache.client import start_redis, stop_redis
from .infrastructure.db.session import engine
from .api.routes import auth


setup_logging(service_name=settings.service_name, log_level=settings.log_level)

app = FastAPI(title="auth-service", redirect_slashes=False)

setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn, app=app)

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


app.include_router(health_router)
app.include_router(auth.router)

install_http_metrics_middleware(app)
install_request_context_middleware(app)
install_unhandled_exception_middleware(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
