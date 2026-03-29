from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.prometheus_http import install_http_metrics_middleware
from saas_shared.sentry_setup import setup_sentry_fastapi

from .api.routes import health, routes
from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry

setup_logging(service_name=settings.service_name, log_level=settings.log_level)
setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn)

app = FastAPI(title=settings.service_name)

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
)

app.include_router(health.router)
app.include_router(routes.router)

install_http_metrics_middleware(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
