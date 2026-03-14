from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..client import client
from ..config import settings


router = APIRouter()


async def _proxy(request: Request, url: str) -> Response:
    body = await request.body()

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    resp = await client.request(
        request.method,
        url,
        content=body,
        headers=headers,
    )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


@router.api_route("/tasks", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_tasks_root(request: Request):
    return await _proxy(request, f"{settings.task_service_url}/tasks")


@router.api_route("/tasks/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_tasks(path: str, request: Request):
    return await _proxy(request, f"{settings.task_service_url}/tasks/{path}")