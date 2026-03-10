import httpx


client = httpx.AsyncClient(
    timeout=5.0
)