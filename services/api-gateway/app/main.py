import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from saas_shared.health import router as health_router

from .api.routes import proxy
from .core.config import settings
from .core.logging import setup_logging
from .core.telemetry import setup_telemetry


def _setup_sentry() -> None:
    """Initialise Sentry error tracking. No-op when SENTRY_DSN is not set."""
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            # StarletteIntegration must come before FastApiIntegration.
            # Together they replace the old SentryAsgiMiddleware approach and
            # provide automatic exception capture + per-endpoint transactions.
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            # HttpxIntegration instruments every outbound httpx call made by
            # this service.  It creates child spans and, crucially, injects the
            # *gateway's own* sentry-trace / baggage headers so downstream
            # services see the correct parent span — not the raw browser span.
            HttpxIntegration(),
        ],
        # Sample 10% of transactions for performance monitoring.
        # Set to 1.0 in production only while debugging a latency issue.
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", settings.service_name)


setup_logging(service_name=settings.service_name, log_level=settings.log_level)
_setup_sentry()

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

setup_telemetry(app, settings.service_name, settings.otlp_endpoint)

app.include_router(health_router)
app.include_router(proxy.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
