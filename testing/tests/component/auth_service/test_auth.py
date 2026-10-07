"""Characterised auth-service behaviour. The flow returns the response; the test decides."""

import json
import os
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from pytest_mock import MockerFixture

from saas_testkit.domain import ApiResponse, UserInfo
from saas_testkit.factories import LAB_JWT_SECRET, Rows
from saas_testkit.flows import AuthFlow

# `UserRowFactory` stores one argon2 hash of this password.
_PASSWORD = "user123"
_SUBJECT = "ada"
_ROLE = "user"


def _claims(token: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        jwt.decode(  # pyright: ignore[reportUnknownMemberType]
            token,
            LAB_JWT_SECRET,
            algorithms=["HS256"],
        ),
    )


def _assert_lifetime(claims: dict[str, object]) -> None:
    exp = claims["exp"]
    if not isinstance(exp, int | float):
        raise AssertionError(f"exp was {exp!r}")
    minutes = int(os.environ["TOKEN_EXPIRE_MINUTES"])
    remaining = exp - datetime.now(UTC).timestamp()
    assert abs(remaining - minutes * 60) < 15


def _detail(response: ApiResponse[UserInfo]) -> str:
    assert response.error is not None
    detail = response.error.detail
    assert isinstance(detail, str)
    return detail


def _omits_secrets(document: object, hashed: str) -> None:
    assert isinstance(document, dict)
    assert "password" not in document
    assert "hashed_password" not in document
    assert hashed not in json.dumps(document)


@pytest.mark.parametrize("role", ["user", "admin"])
async def test_login_issues_a_token_for_each_role(auth: AuthFlow, rows: Rows, role: str) -> None:
    # `role` is copied into the token and echoed by `/auth/me`. No route enforces it.
    user = await rows.user.create_async(role=role)

    response = await auth.login(username=user.username, password=_PASSWORD)

    assert response.status == 200
    assert response.data is not None
    assert response.data.token_type == "bearer"
    claims = _claims(response.data.access_token)
    assert claims["sub"] == user.username
    assert claims["role"] == role
    assert set(claims) == {"sub", "role", "exp"}
    _assert_lifetime(claims)


@pytest.mark.parametrize(
    ("known_user", "password"),
    [
        pytest.param(True, "wrong-password", id="wrong-password"),
        pytest.param(False, _PASSWORD, id="unknown-user"),
    ],
)
async def test_login_rejects_bad_credentials_with_the_same_body(
    auth: AuthFlow, rows: Rows, known_user: bool, password: str
) -> None:
    if known_user:
        user = await rows.user.create_async()
        username = user.username
    else:
        username = f"nobody-{uuid4().hex}"

    response = await auth.login(username=username, password=password)

    assert response.status == 401
    assert response.error is not None
    assert response.error.detail == "Invalid credentials"


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({}, id="both-missing"),
        pytest.param({"password": "secret"}, id="username-missing"),
        pytest.param({"username": "ada"}, id="password-missing"),
    ],
)
async def test_login_rejects_missing_fields(auth: AuthFlow, fields: dict[str, str]) -> None:
    response = await auth.submit_login(fields)

    assert response.status == 422


@pytest.mark.parametrize(
    ("kind", "code", "detail"),
    [
        pytest.param("valid", 200, None, id="valid"),
        pytest.param("expired", 401, "Token expired", id="expired"),
        pytest.param("tampered", 401, "Invalid token:", id="tampered"),
        pytest.param("alg_none", 401, "Invalid token:", id="alg-none"),
        # characterization: OAuth2PasswordBearer rejects these before JWT decode.
        pytest.param("missing", 401, "Not authenticated", id="missing-header"),
        pytest.param("malformed", 401, "Not authenticated", id="malformed-header"),
    ],
)
async def test_me_accepts_only_a_valid_token(
    auth: AuthFlow, kind: str, code: int, detail: str | None
) -> None:
    response = await auth.me_as(kind, sub=_SUBJECT, role=_ROLE)

    assert response.status == code
    if kind == "valid":
        assert response.data is not None
        assert response.data.username == _SUBJECT
        assert response.data.role == _ROLE
        return
    text = _detail(response)
    if kind in {"tampered", "alg_none"}:
        assert detail is not None
        assert text.startswith(detail)
        return
    assert text == detail


async def test_responses_omit_the_password_and_its_hash(auth: AuthFlow, rows: Rows) -> None:
    user = await rows.user.create_async()

    login = await auth.login(username=user.username, password=_PASSWORD)
    assert login.status == 200
    assert login.data is not None
    _omits_secrets(login.document, user.hashed_password)
    claims = _claims(login.data.access_token)
    assert _PASSWORD not in claims.values()
    assert user.hashed_password not in claims.values()

    me = await auth.me(login.data.access_token)
    assert me.status == 200
    assert me.data is not None
    assert me.data.username == user.username
    _omits_secrets(me.document, user.hashed_password)


async def test_stored_password_hash_is_argon2(auth: AuthFlow, rows: Rows) -> None:
    user = await rows.user.create_async()
    assert user.hashed_password.startswith("$argon2")

    response = await auth.login(username=user.username, password=_PASSWORD)

    assert response.status == 200


async def test_ready_stays_ready_when_dependencies_are_down(
    auth: AuthFlow,
    rows: Rows,
    service_app: FastAPI,
    mocker: MockerFixture,
) -> None:
    # characterization: GET /ready does not check Redis or Postgres.
    user = await rows.user.create_async()
    mocker.patch.object(
        service_app.state.redis,
        "get",
        autospec=True,
        side_effect=ConnectionError("redis down"),
    )
    mocker.patch.object(
        service_app.state.redis,
        "set",
        autospec=True,
        side_effect=ConnectionError("redis down"),
    )
    mocker.patch(
        "app.repositories.user_repository.UserRepository.get_by_username",
        autospec=True,
        side_effect=ConnectionError("postgres down"),
    )

    login = await auth.login(username=user.username, password=_PASSWORD)
    ready = await auth.ready()

    assert login.status == 500
    assert ready.status == 200
    assert ready.data is not None
    assert ready.data.status == "ready"


async def test_second_login_uses_the_user_cache(auth: AuthFlow, rows: Rows) -> None:
    user = await rows.user.create_async(role="user")
    first = await auth.logged_in(username=user.username, password=_PASSWORD)
    assert _claims(first.access_token)["role"] == "user"

    await auth.replace_cached_role(user.username, "admin")
    second = await auth.login(username=user.username, password=_PASSWORD)

    assert second.status == 200
    assert second.data is not None
    assert _claims(second.data.access_token)["role"] == "admin"
    assert user.role == "user"


@pytest.mark.xfail(
    strict=True,
    reason="BUG-4: login cache stores hashed_password at user:{username}",
)
async def test_user_cache_omits_the_password_hash(auth: AuthFlow, rows: Rows) -> None:
    user = await rows.user.create_async()
    await auth.logged_in(username=user.username, password=_PASSWORD)

    cached = await auth.cached_user(user.username)

    assert cached is not None
    assert "hashed_password" not in cached


async def test_login_works_when_redis_is_down(
    auth: AuthFlow,
    rows: Rows,
    service_app: FastAPI,
    mocker: MockerFixture,
) -> None:
    user = await rows.user.create_async()
    mocker.patch.object(
        service_app.state.redis,
        "get",
        autospec=True,
        side_effect=ConnectionError("redis down"),
    )
    mocker.patch.object(
        service_app.state.redis,
        "set",
        autospec=True,
        side_effect=ConnectionError("redis down"),
    )

    response = await auth.login(username=user.username, password=_PASSWORD)

    assert response.status == 200
    assert response.data is not None
    claims = _claims(response.data.access_token)
    assert claims["sub"] == user.username
    assert claims["role"] == user.role


async def test_me_does_not_open_a_database_session(auth: AuthFlow, mocker: MockerFixture) -> None:
    mocker.patch(
        "app.dependencies.SessionLocal",
        side_effect=AssertionError("GET /auth/me opened a database session"),
    )

    response = await auth.me_as("valid", sub=_SUBJECT, role=_ROLE)

    assert response.status == 200
    assert response.data is not None
    assert response.data.username == _SUBJECT
    assert response.data.role == _ROLE
