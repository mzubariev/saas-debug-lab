import structlog

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..client import client
from ..config import settings
from ..dependencies import verify_token


router = APIRouter()

logger = structlog.get_logger()


async def _proxy(request: Request, url: str) -> Response:
    body = await request.body()

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    try:
        resp = await client.request(
            request.method,
            url,
            content=body,
            headers=headers,
        )
    except httpx.TimeoutException:
        logger.error("proxy_timeout", method=request.method, url=url)
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except httpx.RequestError as exc:
        logger.error("proxy_connection_error", method=request.method, url=url, error=str(exc))
        raise HTTPException(status_code=502, detail="Upstream unavailable")

    log = logger.warning if resp.status_code >= 400 else logger.info
    log(
        "proxy_request",
        method=request.method,
        path=str(request.url.path),
        status=resp.status_code,
        upstream=url,
    )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


# Auth routes — no token required (this is where you obtain a token).
@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_auth(path: str, request: Request):
    return await _proxy(request, f"{settings.auth_service_url}/auth/{path}")


# Task routes — valid JWT required.
@router.api_route("/tasks", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_tasks_root(request: Request, _: dict = Depends(verify_token)):
    return await _proxy(request, f"{settings.task_service_url}/tasks")


@router.api_route("/tasks/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_tasks(path: str, request: Request, _: dict = Depends(verify_token)):
    return await _proxy(request, f"{settings.task_service_url}/tasks/{path}")