import httpx

from .config import settings


client = httpx.AsyncClient(
    timeout=settings.gateway_timeout
)