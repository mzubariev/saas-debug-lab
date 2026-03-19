from fastapi import FastAPI
from prometheus_client import make_asgi_app

from .config import settings
from .db import engine
from .logging import setup_logging
from .models.task import Base
from .routes import health, tasks
from .kafka import start_kafka, stop_kafka
from .cache import start_redis, stop_redis
from .telemetry import setup_telemetry


app = FastAPI(title="task-service")

setup_logging(settings.log_level, settings.service_name)
setup_telemetry(app, settings.service_name, settings.otlp_endpoint)


@app.on_event("startup")
async def startup():

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await start_kafka(app)
    await start_redis(app, settings.redis_url)


@app.on_event("shutdown")
async def shutdown():

    await stop_kafka(app)
    await stop_redis(app)


# routers
app.include_router(health.router)
app.include_router(tasks.router)


# prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)