"""Self-tests for JwtFactory. No Docker."""

import base64
import json
import time
from typing import cast

import jwt
import pytest

from saas_testkit.factories import JwtFactory

_SECRET = "dev-secret-change-in-production"
_SUB = "user"
_ROLE = "user"


def test_valid_token_decodes_with_lab_secret() -> None:
    token = JwtFactory().valid(sub=_SUB, role=_ROLE)

    claims = cast(dict[str, object], jwt.decode(token, _SECRET, algorithms=["HS256"]))

    assert claims["sub"] == _SUB
    assert claims["role"] == _ROLE
    assert cast(float, claims["exp"]) > time.time()


def test_expired_token_raises_expired_signature() -> None:
    token = JwtFactory().expired(sub=_SUB, role=_ROLE)

    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, _SECRET, algorithms=["HS256"])


def test_tampered_token_raises_invalid_signature() -> None:
    token = JwtFactory().tampered(sub=_SUB, role=_ROLE)

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, _SECRET, algorithms=["HS256"])


def test_alg_none_token_header_uses_none() -> None:
    token = JwtFactory().alg_none(sub=_SUB, role=_ROLE)
    header = _segment(token.split(".", maxsplit=1)[0])

    assert header["alg"] == "none"


def test_alg_none_token_rejected_by_hs256() -> None:
    token = JwtFactory().alg_none(sub=_SUB, role=_ROLE)

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, _SECRET, algorithms=["HS256"])


def _segment(value: str) -> dict[str, object]:
    padded = value + "=" * (-len(value) % 4)
    loaded = cast(object, json.loads(base64.urlsafe_b64decode(padded)))
    assert isinstance(loaded, dict)
    return cast(dict[str, object], loaded)
