from fastapi import FastAPI
from prometheus_client import make_asgi_app

from .telemetry import setup_telemetry
from .routes import proxy


app = FastAPI(title="api-gateway")

setup_telemetry(app)

app.include_router(proxy.router)


metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health():
    return {"status": "ok"}