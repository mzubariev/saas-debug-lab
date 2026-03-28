from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from saas_shared.sentry_setup import setup_sentry_fastapi

from .api.routes import proxy, health
from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry


setup_logging(service_name=settings.service_name, log_level=settings.log_level)
setup_sentry_fastapi(
    service_name=settings.service_name,
    dsn=settings.sentry_dsn,
    httpx=True,
)

app = FastAPI(title="api-gateway")

# The frontend Vite dev server runs on port 5173 (a different origin from the
# Nginx port 80 that the API lives behind).  CORS headers are required for the
# browser to attach sentry-trace / baggage to cross-origin fetch() calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost",        # production-like Docker frontend
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],           # must include sentry-trace and baggage
    expose_headers=["*"],
)

setup_telemetry(
    app,
    settings.service_name,
    settings.otlp_endpoint,
)

app.include_router(health.router)
app.include_router(proxy.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
