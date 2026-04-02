from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.logging import install_request_context_middleware, install_unhandled_exception_middleware
from saas_shared.prometheus_http import install_http_metrics_middleware
from saas_shared.sentry_setup import setup_sentry_fastapi

from saas_shared.health import router as health_router
from saas_shared.logging import setup_logging
from saas_shared.telemetry import setup_telemetry

from .api.routes import routes
from .core.config import settings

setup_logging(service_name=settings.service_name, log_level=settings.log_level)

app = FastAPI(title=settings.service_name, redirect_slashes=False)

setup_sentry_fastapi(service_name=settings.service_name, dsn=settings.sentry_dsn, app=app)

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
)

app.include_router(health_router)
app.include_router(routes.router)

install_http_metrics_middleware(app)
install_request_context_middleware(app)
install_unhandled_exception_middleware(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
