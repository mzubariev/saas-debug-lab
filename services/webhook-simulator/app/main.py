from fastapi import FastAPI
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from saas_shared.health import router as health_router

from .api.routes.routes import router as api_router
from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry

setup_logging(service_name=settings.service_name, log_level=settings.log_level)

app = FastAPI(title=settings.service_name)

setup_telemetry(app, settings.service_name, settings.otlp_endpoint)
HTTPXClientInstrumentor().instrument()

app.include_router(health_router)
app.include_router(api_router)
