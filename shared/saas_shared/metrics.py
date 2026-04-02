"""FastAPI router that serves the Prometheus metrics endpoint.

Mirrors the pattern of ``saas_shared.health`` — import the router and include it:

    from saas_shared.metrics import router as metrics_router
    app.include_router(metrics_router)
"""
from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
