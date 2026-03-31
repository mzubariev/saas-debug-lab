import httpx


def create_http_client() -> httpx.AsyncClient:
    """Shared async HTTP client for outbound webhook POSTs."""
    return httpx.AsyncClient()
