import httpx


def post_json_sync(url: str, payload: dict, *, timeout: int) -> httpx.Response:
    """POST JSON body using a short-lived sync client."""
    with httpx.Client(timeout=timeout) as client:
        return client.post(url, json=payload)
