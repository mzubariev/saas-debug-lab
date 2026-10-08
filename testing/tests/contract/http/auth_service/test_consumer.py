"""Login and `/auth/me` bodies match the consumer models."""

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


async def test_me_matches_consumer_model(auth: AuthFlow, rows: Rows) -> None:
    user = await rows.user.create_async()
    token = await auth.logged_in(username=user.username, password=_PASSWORD)
    response = await auth.me(token.access_token)

    assert response.status == 200
    UserInfo.model_validate(response.document)
