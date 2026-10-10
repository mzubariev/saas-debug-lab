from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from saas_shared.logging import install_request_context_middleware, install_unhandled_exception_middleware
from saas_shared.metrics import router as metrics_router
from saas_shared.prometheus_http import install_http_metrics_middleware
from saas_shared.sentry_setup import setup_sentry_fastapi

from saas_shared.health import router as health_router
from saas_shared.logging import setup_logging
from saas_shared.telemetry import setup_telemetry

from .core.config import settings


setup_logging(service_name=settings.service_name, log_level=settings.log_level)

app = FastAPI(title="api-gateway", redirect_slashes=False)

# Bridge is registered on the app before setup_telemetry so that OTel's middleware
# ends up outermost (Starlette LIFO). Request flow: OTel → CORS → Bridge → handler.
setup_sentry_fastapi(
    service_name=settings.service_name,
    dsn=settings.sentry_dsn,
    httpx=True,
    app=app,
)

# The frontend Vite dev server runs on port 5173 (a different origin from the
# Nginx port 80 that the API lives behind).  CORS headers are required for the
# browser to attach sentry-trace / baggage to cross-origin fetch() calls.
# `CORS_ORIGINS` appends origins (the test stack publishes the UI on 5174).
def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost",  # production-like Docker frontend
        "http://127.0.0.1:5173",
    ]
    for item in settings.cors_origins.split(","):
        origin = item.strip()
        if origin and origin not in origins:
            origins.append(origin)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
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

# Import proxy only after telemetry: proxy pulls in the shared httpx.AsyncClient, which must be
# constructed after HTTPXClientInstrumentor().instrument() or outbound calls won't inject
# traceparent and downstream services break trace continuity.
from .api.routes import proxy

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(proxy.router)

install_http_metrics_middleware(app)
install_request_context_middleware(app)
install_unhandled_exception_middleware(app)

