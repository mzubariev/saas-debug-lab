import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.health import router as health_router

from .config import settings
from .logging import setup_logging
from .telemetry import setup_telemetry
from .routes import proxy


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
        ],
        # Sample 10% of transactions for performance monitoring.
        # Set to 1.0 in production only while debugging a latency issue.
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", settings.service_name)


_setup_sentry()

app = FastAPI(title="api-gateway")

setup_logging(settings.log_level, settings.service_name)
setup_telemetry(app, settings.service_name, settings.otlp_endpoint)

app.include_router(health_router)
app.include_router(proxy.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
