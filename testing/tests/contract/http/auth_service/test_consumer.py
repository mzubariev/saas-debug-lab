"""Login and `/auth/me` bodies match the consumer models."""

import pytest

from saas_testkit.domain import TokenResponse, UserInfo
from saas_testkit.factories import Rows
from saas_testkit.flows import AuthFlow

# `UserRowFactory` stores one argon2 hash of this password.
_PASSWORD = "user123"


async def test_token_matches_consumer_model(auth: AuthFlow, rows: Rows) -> None:
    user = await rows.user.create_async()
    response = await auth.login(username=user.username, password=_PASSWORD)

    assert response.status == 200
    TokenResponse.model_validate(response.document)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-9: NUL in username is invalid UTF-8 for Postgres; POST /auth/token returns 500",
)
async def test_login_with_a_nul_username_is_not_a_server_error(auth: AuthFlow) -> None:
    response = await auth.login(username="user\x00", password="user123")

    assert response.status < 500


async def test_me_matches_consumer_model(auth: AuthFlow, rows: Rows) -> None:
    user = await rows.user.create_async()
    token = await auth.logged_in(username=user.username, password=_PASSWORD)
    response = await auth.me(token.access_token)

    assert response.status == 200
    UserInfo.model_validate(response.document)
