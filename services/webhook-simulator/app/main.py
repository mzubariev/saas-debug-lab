from fastapi import FastAPI
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import make_asgi_app

from .api.routes import health, routes
from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry

setup_logging(service_name=settings.service_name, log_level=settings.log_level)

app = FastAPI(title=settings.service_name)

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
    settings.otlp_datadog_endpoint,
)
HTTPXClientInstrumentor().instrument()

app.include_router(health.router)
app.include_router(routes.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
