"""Characterised api-gateway behaviour. The flow returns the response; the test decides."""

import pytest

from saas_testkit.domain import ApiResponse, ProxiedBody
from saas_testkit.flows import GatewayFlow

_SERVICES = {
    "auth": "auth-service",
    "tasks": "task-service",
    "tasks-item": "task-service",
    "webhooks": "webhook-receiver",
}
_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost",
)


def _detail(response: ApiResponse[ProxiedBody]) -> str:
    assert response.error is not None
    detail = response.error.detail
    assert isinstance(detail, str)
    return detail


@pytest.mark.parametrize("route", ["auth", "tasks", "tasks-item", "webhooks"])
async def test_routes_a_prefix_to_its_upstream(gateway: GatewayFlow, route: str) -> None:
    routed = await gateway.through(route)

    assert routed.response.status == 200
    assert routed.response.data is not None
    assert routed.response.data.marker == "ok"
    assert routed.service == _SERVICES[route]
    assert routed.path == gateway.path_for(route)


@pytest.mark.parametrize("route", ["auth", "webhooks"])
async def test_open_routes_do_not_require_a_token(gateway: GatewayFlow, route: str) -> None:
    routed = await gateway.open(route)

    assert routed.response.status == 200
    assert routed.service == _SERVICES[route]
    assert routed.path == gateway.path_for(route)


@pytest.mark.parametrize(
    ("kind", "detail"),
    [
        pytest.param("missing", "Missing authorization header", id="missing"),
        pytest.param("expired", "Token expired", id="expired"),
        pytest.param("tampered", "Invalid token:", id="tampered"),
        pytest.param("alg_none", "Invalid token:", id="alg-none"),
    ],
)
async def test_tasks_reject_a_bad_token(gateway: GatewayFlow, kind: str, detail: str) -> None:
    routed = await gateway.tasks_as(kind)

    assert routed.response.status == 401
    assert routed.service is None
    text = _detail(routed.response)
    if kind in {"tampered", "alg_none"}:
        assert text.startswith(detail)
        return
    assert text == detail


async def test_proxy_forwards_ordinary_headers_and_replaces_the_client_host(
    gateway: GatewayFlow,
) -> None:
    # characterization: the proxy omits host, sentry-trace, baggage, traceparent, and
    # tracestate. With OTLP_ENDPOINT empty, the httpx instrumentor puts the client's
    # baggage, traceparent, and tracestate back. sentry-trace stays off. Host on the
    # wire is the upstream hostname.
    forwarded = await gateway.forwarded_headers()

    assert "sentry-trace" not in forwarded.headers
    assert forwarded.client_host not in forwarded.headers.values()
    assert forwarded.headers["host"] == forwarded.upstream_host
    assert forwarded.headers["baggage"] == forwarded.baggage
    assert forwarded.headers["traceparent"] == forwarded.traceparent
    assert forwarded.headers["tracestate"] == forwarded.tracestate
    assert forwarded.headers["x-request-id"] == forwarded.request_id
    assert forwarded.headers["x-lab-marker"] == forwarded.marker


@pytest.mark.parametrize(
    ("status", "marker"),
    [
        pytest.param(404, "missing", id="client-error"),
        pytest.param(503, "unavailable", id="server-error"),
    ],
)
async def test_upstream_status_and_body_pass_through(
    gateway: GatewayFlow, status: int, marker: str
) -> None:
    response = await gateway.passthrough(status=status, marker=marker)

    assert response.status == status
    assert response.document == {"marker": marker}


@pytest.mark.parametrize(
    ("failure", "status", "detail"),
    [
        pytest.param("timeout", 504, "Downstream timeout", id="timeout"),
        pytest.param("down", 502, "Downstream unavailable", id="connection-error"),
    ],
)
async def test_upstream_transport_failure_is_a_gateway_error(
    gateway: GatewayFlow, failure: str, status: int, detail: str
) -> None:
    response = await gateway.when_upstream_fails(failure)

    assert response.status == status
    assert response.error is not None
    assert response.error.detail == detail


@pytest.mark.parametrize("origin", _ORIGINS)
async def test_cors_allows_the_frontend_origins(gateway: GatewayFlow, origin: str) -> None:
    assert await gateway.allowed_origin(origin) == origin


async def test_cors_rejects_an_unknown_origin(gateway: GatewayFlow) -> None:
    assert await gateway.allowed_origin("http://evil.example") is None
