"""Access tokens with the auth-service claims. No I/O."""

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt

# Lab value from SUT_MAP. Services require JWT_SECRET and do not default it.
LAB_JWT_SECRET = "dev-secret-change-in-production"
_TTL = timedelta(minutes=30)


class JwtFactory:
    """HS256 tokens: valid, expired, tampered, and `alg=none`."""

    def __init__(self, secret: str = LAB_JWT_SECRET) -> None:
        self._secret = secret

    def valid(self, *, sub: str, role: str) -> str:
        return self._sign(sub=sub, role=role, exp=datetime.now(UTC) + _TTL)

    def expired(self, *, sub: str, role: str) -> str:
        return self._sign(sub=sub, role=role, exp=datetime.now(UTC) - timedelta(seconds=60))

    def tampered(self, *, sub: str, role: str) -> str:
        """Same signature, payload `role` changed. HS256 verification must fail."""
        token = self.valid(sub=sub, role=role)
        header, _payload, signature = token.split(".")
        claims = cast(
            dict[str, object],
            jwt.decode(token, self._secret, algorithms=["HS256"]),  # pyright: ignore[reportUnknownMemberType]
        )
        claims["role"] = "admin" if claims.get("role") != "admin" else "user"
        payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
        return f"{header}.{payload}.{signature}"

    def alg_none(self, *, sub: str, role: str) -> str:
        """Unsigned token. PyJWT refuses to encode `alg=none`."""
        header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":")).encode())
        body = _b64url(
            json.dumps(
                {"sub": sub, "role": role, "exp": int(time.time()) + int(_TTL.total_seconds())},
                separators=(",", ":"),
            ).encode()
        )
        return f"{header}.{body}."

    def _sign(self, *, sub: str, role: str, exp: datetime) -> str:
        return jwt.encode(  # pyright: ignore[reportUnknownMemberType]
            {"sub": sub, "role": role, "exp": exp},
            self._secret,
            algorithm="HS256",
        )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
