import httpx

from ...core.config import settings


client = httpx.AsyncClient(
    timeout=settings.gateway_timeout
)
