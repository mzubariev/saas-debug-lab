from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..client import client
from ..config import settings


router = APIRouter()


@router.api_route("/tasks/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_tasks(path: str, request: Request):

    url = f"{settings.task_service_url}/tasks/{path}"

    body = await request.body()

    resp = await client.request(
        request.method,
        url,
        content=body,
        headers=request.headers.raw
    )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp.headers
    )