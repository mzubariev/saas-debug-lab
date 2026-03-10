from fastapi import FastAPI
from prometheus_client import make_asgi_app

from .logging import setup_logging
from .routes import health, tasks
from .kafka import start_kafka, stop_kafka
from .telemetry import setup_telemetry


app = FastAPI(title="task-service")

# logging
setup_logging()

# tracing
setup_telemetry(app)


@app.on_event("startup")
async def startup():

    await start_kafka(app)


@app.on_event("shutdown")
async def shutdown():

    await stop_kafka(app)


# routers
app.include_router(health.router)
app.include_router(tasks.router)


# prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)