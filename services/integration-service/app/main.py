from fastapi import FastAPI
from prometheus_client import make_asgi_app
from saas_shared.health import router as health_router

from .config import settings
from .logging import setup_logging
from .telemetry import setup_telemetry
from .kafka import start_kafka, stop_kafka
from .routes.webhooks import router as webhooks_router


app = FastAPI(title="integration-service")

setup_logging(settings.log_level, settings.service_name)
setup_telemetry(app, settings.service_name, settings.otlp_endpoint)


@app.on_event("startup")
async def startup() -> None:
    await start_kafka(app)


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_kafka(app)


app.include_router(health_router)
app.include_router(webhooks_router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
