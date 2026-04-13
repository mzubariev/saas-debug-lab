"""FastAPI router that serves the Prometheus metrics endpoint.

Mirrors the pattern of ``saas_shared.health`` — import the router and include it:

    from saas_shared.metrics import router as metrics_router
    app.include_router(metrics_router)

Content negotiation: when the scraper sends ``Accept: application/openmetrics-text``
(which Prometheus does by default since v2.26), the endpoint responds in OpenMetrics
format.  OpenMetrics is required for exemplar data to be included in the output and
subsequently stored by Prometheus.  Plain Prometheus text format silently drops all
exemplar annotations.
"""
from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import REGISTRY
from prometheus_client.exposition import choose_encoder

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    accept = request.headers.get("Accept", "")
    encoder, content_type = choose_encoder(accept)
    return Response(encoder(REGISTRY), media_type=content_type)
