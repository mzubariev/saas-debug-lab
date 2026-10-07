"""Gateway steps in business language. Preconditions check; the test checks the rest."""

import os
from dataclasses import dataclass
from uuid import uuid4

from saas_testkit.adapters.http.gateway import GatewayUpstream, HttpGatewayApi
from saas_testkit.context import RunContext
from saas_testkit.domain.http import ApiResponse, ProxiedBody
from saas_testkit.factories.jwt import JwtFactory

_CLIENT_HOST = "client.example"
_BAGGAGE = "client=baggage"
_TRACESTATE = "client=state"
_SERVICES = (
    ("AUTH_SERVICE_URL", "auth-service"),
    ("TASK_SERVICE_URL", "task-service"),
    ("INTEGRATION_SERVICE_URL", "webhook-receiver"),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Routed:
    """A gateway response plus the upstream it reached. Both are `None` when it did not proxy."""

    response: ApiResponse[ProxiedBody]
    service: str | None
    path: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Forwarded:
    """Headers the upstream received, and the values this call sent."""

    headers: dict[str, str]
    request_id: str
    marker: str
    client_host: str
    upstream_host: str
    baggage: str
    traceparent: str
    tracestate: str


class GatewayFlow:
    def __init__(self, api: HttpGatewayApi, upstream: GatewayUpstream, ctx: RunContext) -> None:
        self._api = api
        self._upstream = upstream
        self._ctx = ctx
        self._leaf = uuid4().hex

    def path_for(self, route: str) -> str:
        """Gateway path for `auth`, `tasks`, `tasks-item`, or `webhooks`."""
        match route:
            case "auth":
                return f"/auth/{self._leaf}"
            case "tasks":
                return "/tasks"
            case "tasks-item":
                return f"/tasks/{self._leaf}"
            case "webhooks":
                return f"/webhooks/{self._leaf}"
            case _:
                raise ValueError(f"unknown route {route}")

    async def through(self, route: str) -> Routed:
        """Proxy `route` with a valid token. The caller asserts on the response."""
        self._upstream.respond(status=200, marker="ok")
        token = f"Bearer {JwtFactory().valid(sub='ada', role='user')}"
        response = await self._api.request("GET", self.path_for(route), token=token)
        return self._routed(response)

    async def open(self, route: str) -> Routed:
        """Proxy `route` with no `Authorization` header."""
        self._upstream.respond(status=200, marker="ok")
        response = await self._api.request("GET", self.path_for(route))
        return self._routed(response)

    async def tasks_as(self, kind: str) -> Routed:
        """`GET /tasks` with a missing, expired, tampered, or `alg=none` token."""
        self._upstream.respond(status=200, marker="ok")
        response = await self._api.request("GET", "/tasks", token=_token(kind))
        return self._routed(response)

    async def passthrough(self, *, status: int, marker: str) -> ApiResponse[ProxiedBody]:
        """Upstream status and JSON body, returned unchanged."""
        self._upstream.respond(status=status, marker=marker)
        return await self._api.request("GET", self.path_for("auth"))

    async def when_upstream_fails(self, failure: str) -> ApiResponse[ProxiedBody]:
        """`timeout` or `down`. The caller asserts on the gateway's error."""
        self._upstream.fail(failure)
        return await self._api.request("GET", self.path_for("auth"))

    async def forwarded_headers(self) -> Forwarded:
        """Send hop-by-hop headers and return what the auth upstream received."""
        self._upstream.respond(status=200, marker="ok")
        marker = uuid4().hex
        await self._api.request(
            "GET",
            self.path_for("auth"),
            headers={
                "host": _CLIENT_HOST,
                "sentry-trace": "client-sentry",
                "baggage": _BAGGAGE,
                "traceparent": self._ctx.traceparent,
                "tracestate": _TRACESTATE,
                "x-lab-marker": marker,
            },
        )
        request = self._upstream.last_request()
        if request is None:
            raise AssertionError("upstream was not called")
        return Forwarded(
            headers={key.lower(): value for key, value in request.headers.items()},
            request_id=self._ctx.test_id,
            marker=marker,
            client_host=_CLIENT_HOST,
            upstream_host=_auth_host(),
            baggage=_BAGGAGE,
            traceparent=self._ctx.traceparent,
            tracestate=_TRACESTATE,
        )

    async def allowed_origin(self, origin: str) -> str | None:
        """`Access-Control-Allow-Origin` echoed for `origin`, or `None`."""
        response = await self._api.preflight(origin)
        return response.headers.get("access-control-allow-origin")

    def _routed(self, response: ApiResponse[ProxiedBody]) -> Routed:
        request = self._upstream.last_request()
        if request is None:
            return Routed(response=response, service=None, path=None)
        return Routed(
            response=response,
            service=_service_for(str(request.url)),
            path=request.url.path,
        )


def _token(kind: str) -> str | None:
    factory = JwtFactory()
    match kind:
        case "missing":
            return None
        case "expired":
            return f"Bearer {factory.expired(sub='ada', role='user')}"
        case "tampered":
            return f"Bearer {factory.tampered(sub='ada', role='user')}"
        case "alg_none":
            return f"Bearer {factory.alg_none(sub='ada', role='user')}"
        case _:
            raise ValueError(f"unknown token case {kind}")


def _service_for(url: str) -> str | None:
    for env_name, label in _SERVICES:
        if url.startswith(os.environ[env_name].rstrip("/")):
            return label
    return None


def _auth_host() -> str:
    base = os.environ["AUTH_SERVICE_URL"]
    return base.split("://", 1)[1].rstrip("/")
