"""Bring the integration stack up, wait until each service kind is ready, and tear it down.

`BASE_URL` means the stack is already up (CI). `KEEP_STACK=1` skips `down -v`.
"""

import json
import os
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import quote

import httpx
import jwt
import psycopg
from argon2 import PasswordHasher
from filelock import FileLock
from pydantic import BaseModel, ConfigDict

from saas_testkit.adapters.wiremock import WireMockSink
from saas_testkit.config.paths import repo_root, testing_root

_READY_TIMEOUT_S = 180.0
_BUILD_TIMEOUT_S = 900.0
_TOKEN_SKEW_S = 60
_POSTGRES_HOST_PORT = 5433
_REDIS_HOST_PORT = 6380
_KAFKA_HOST_PORT = 9093
_GATEWAY_PORT = 8001

_FASTAPI_EXEC = ("auth-service", "task-service", "webhook-receiver")
_FASTAPI_HTTP = (
    ("api-gateway", f"http://127.0.0.1:{_GATEWAY_PORT}/health"),
    ("external-service-simulator", "http://127.0.0.1:8000/health"),
)
_HTTP = (
    ("mailhog", "http://127.0.0.1:8025/api/v2/messages"),
    ("wiremock", "http://127.0.0.1:8089/__admin/mappings"),
    ("nginx", "http://127.0.0.1/health"),
    ("frontend", "http://127.0.0.1:5173/"),
    ("toxiproxy", "http://127.0.0.1:8474/version"),
)
_WORKERS = (
    ("webhook-dispatcher", 9101),
    ("notification-worker", 9102),
    ("scheduler-worker", 9103),
)
_TCP = (
    ("postgres", _POSTGRES_HOST_PORT),
    ("redis", _REDIS_HOST_PORT),
    ("kafka", _KAFKA_HOST_PORT),
)
_HEALTH_PROBE = (
    "import urllib.request; "
    "urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"
)
_HASHER = PasswordHasher()


@dataclass(frozen=True, slots=True, kw_only=True)
class Stack:
    """URLs for one integration run. `owned` is false when `BASE_URL` was already set."""

    base_url: str
    nginx_url: str
    owned: bool


class _SessionFile(BaseModel):
    """Written by the controller. Workers only read it."""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    nginx_url: str
    access_token: str


def stack_up() -> Stack:
    """Start the test stack, or attach when `BASE_URL` is set."""
    base = os.environ.get("BASE_URL", "").strip()
    nginx = os.environ.get("NGINX_URL", "http://127.0.0.1").strip().rstrip("/")
    if base:
        return Stack(base_url=base.rstrip("/"), nginx_url=nginx, owned=False)
    _stack_dir().mkdir(parents=True, exist_ok=True)
    with FileLock(_lock_path(), timeout=_BUILD_TIMEOUT_S):
        _require("up", "-d", "--build", "--remove-orphans", *_services(), timeout=_BUILD_TIMEOUT_S)
        _wait_until(_postgres_ready, "postgres")
        _require("up", "-d", "--force-recreate", "--no-deps", "migrations", timeout=180)
        _wait_ready()
    return Stack(base_url=f"http://127.0.0.1:{_GATEWAY_PORT}", nginx_url=nginx, owned=True)


def stack_down() -> None:
    """`docker compose down -v`. `make stack-down` always calls this."""
    completed = _compose("down", "-v", timeout=180)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "docker compose down failed")


def release_stack() -> None:
    """Tear the stack down unless `KEEP_STACK=1` or this process did not start it."""
    if os.environ.get("KEEP_STACK") == "1" or os.environ.get("BASE_URL", "").strip():
        return
    stack_down()


def ensure_admin_token(stack: Stack) -> str:
    """Seed once and log in once per run. Refresh when the JWT is close to `exp`."""
    _stack_dir().mkdir(parents=True, exist_ok=True)
    with FileLock(_lock_path(), timeout=120):
        current = _read_token()
        if current is None or _expires_soon(current):
            _seed()
            current = _login(stack.base_url)
        _write_session(stack, current)
        if stack.owned:
            WireMockSink("http://127.0.0.1:8089").install_catch_all()
        return current


def read_session() -> _SessionFile:
    """What the controller wrote. Workers call this and do not log in."""
    path = _session_path()
    if not path.is_file():
        raise RuntimeError(f"integration session file is missing: {path}")
    session = _SessionFile.model_validate_json(path.read_text())
    if _expires_soon(session.access_token):
        raise RuntimeError("admin token is close to exp; the controller should have refreshed it")
    return session


def _services() -> tuple[str, ...]:
    names: list[str] = []
    for line in (repo_root() / "infra" / "test-stack.services").read_text().splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            names.append(name)
    if not names:
        raise RuntimeError("infra/test-stack.services is empty")
    return tuple(names)


def _wait_ready() -> None:
    pending = _not_ready()
    deadline = time.monotonic() + _READY_TIMEOUT_S
    while pending and time.monotonic() < deadline:
        time.sleep(2)
        pending = _not_ready()
    if not pending:
        return
    logs = _compose("logs", "--tail", "100", *pending, timeout=60)
    detail = (logs.stdout + logs.stderr).strip()
    raise RuntimeError(f"not ready after {_READY_TIMEOUT_S:.0f}s: {', '.join(pending)}\n{detail}")


def _not_ready() -> tuple[str, ...]:
    pending: list[str] = []
    if not _migrations_done():
        pending.append("migrations")
    for name, url in _FASTAPI_HTTP:
        if not _http_ok(url):
            pending.append(name)
    for name in _FASTAPI_EXEC:
        if not _exec_health(name):
            pending.append(name)
    for name, url in _HTTP:
        if not _http_ok(url):
            pending.append(name)
    for name, port in _WORKERS:
        if not _http_ok(f"http://127.0.0.1:{port}/metrics"):
            pending.append(name)
    for name, port in _TCP:
        if not _tcp_open(port):
            pending.append(name)
    return tuple(pending)


def _wait_until(probe: Callable[[], bool], name: str) -> None:
    deadline = time.monotonic() + _READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if probe():
            return
        time.sleep(2)
    logs = _compose("logs", "--tail", "100", name, timeout=60)
    detail = (logs.stdout + logs.stderr).strip()
    raise RuntimeError(f"{name} was not ready\n{detail}")


def _postgres_ready() -> bool:
    if not _tcp_open(_POSTGRES_HOST_PORT):
        return False
    completed = _compose(
        "exec",
        "-T",
        "postgres",
        "pg_isready",
        "-U",
        "admin",
        "-d",
        "saas",
        timeout=20,
    )
    return completed.returncode == 0


def _migrations_done() -> bool:
    for row in _ps():
        if row.get("Service") != "migrations":
            continue
        state = str(row.get("State", "")).lower()
        return state == "exited" and row.get("ExitCode") == 0
    return False


def _exec_health(service: str) -> bool:
    completed = _compose("exec", "-T", service, "python", "-c", _HEALTH_PROBE, timeout=20)
    return completed.returncode == 0


def _http_ok(url: str) -> bool:
    try:
        response = httpx.get(url, timeout=2)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _ps() -> list[dict[str, object]]:
    completed = _compose("ps", "-a", "--format", "json", timeout=30)
    text = completed.stdout.strip()
    if completed.returncode != 0 or not text:
        return []
    if text.startswith("["):
        return _rows(cast(object, json.loads(text)))
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        rows.extend(_rows(cast(object, json.loads(line))))
    return rows


def _rows(loaded: object) -> list[dict[str, object]]:
    if isinstance(loaded, dict):
        parsed = _string_keys(cast(object, loaded))
        return [] if parsed is None else [parsed]
    if not isinstance(loaded, list):
        return []
    rows: list[dict[str, object]] = []
    for item in cast(list[object], loaded):
        parsed = _string_keys(item)
        if parsed is not None:
            rows.append(parsed)
    return rows


def _string_keys(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    parsed: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if isinstance(key, str):
            parsed[key] = item
    return parsed


def _seed() -> None:
    admin_hash = _HASHER.hash("admin123")
    user_hash = _HASHER.hash("user123")
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO users (username, hashed_password, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            ("admin", admin_hash, "admin"),
        )
        conn.execute(
            """
            INSERT INTO users (username, hashed_password, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            ("user", user_hash, "user"),
        )


def _login(base_url: str) -> str:
    response = httpx.post(
        f"{base_url}/auth/token",
        data={"username": "admin", "password": "admin123"},
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError(f"admin login failed: {response.status_code} {response.text}")
    body = cast(dict[str, object], response.json())
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("admin login did not return access_token")
    return token


def _database_url() -> str:
    override = os.environ.get("DATABASE_URL", "").strip()
    if override:
        return override
    user = quote("admin")
    password = quote("admin")
    return f"postgresql://{user}:{password}@127.0.0.1:{_POSTGRES_HOST_PORT}/saas"


def _read_token() -> str | None:
    path = _session_path()
    if not path.is_file():
        return None
    try:
        session = _SessionFile.model_validate_json(path.read_text())
    except ValueError:
        return None
    return session.access_token


def _write_session(stack: Stack, token: str) -> None:
    document = _SessionFile(
        base_url=stack.base_url,
        nginx_url=stack.nginx_url,
        access_token=token,
    )
    path = _session_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(document.model_dump_json())
    temporary.replace(path)


def _expires_soon(token: str) -> bool:
    try:
        claims = cast(
            dict[str, object],
            jwt.decode(token, options={"verify_signature": False}),  # pyright: ignore[reportUnknownMemberType]
        )
    except jwt.PyJWTError:
        return True
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        return True
    return exp - time.time() < _TOKEN_SKEW_S


def _stack_dir() -> Path:
    return testing_root() / ".stack"


def _lock_path() -> Path:
    return _stack_dir() / "stack.lock"


def _session_path() -> Path:
    return _stack_dir() / "session.json"


def _require(*args: str, timeout: float) -> subprocess.CompletedProcess[str]:
    completed = _compose(*args, timeout=timeout)
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr).strip()
        raise RuntimeError(f"docker compose failed\n{detail}")
    return completed


def _compose(*args: str, timeout: float) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.test.yml",
        *args,
    ]
    return subprocess.run(  # noqa: S603
        command,
        cwd=repo_root() / "infra",
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
