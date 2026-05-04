"""JWT signing and verification using python-jose (HS256).

Design:
  - The DB stores only the opaque JTI (token_urlsafe(32), 43 chars) for revocation.
  - The client receives a signed JWT that embeds the JTI as the `jti` claim.
  - Validation: decode JWT → extract jti → single DB revocation check.
  - Legacy opaque tokens (no dots) fall back to direct DB lookup in repositories.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from config import settings

_ALGORITHM = settings.jwt_algorithm


def _secret() -> str:
    key = settings.secret_key
    if not key or key == "change-me-in-production":
        import warnings
        warnings.warn(
            "SECRET_KEY is not set — JWT tokens are NOT secure. Set SECRET_KEY in .env.",
            stacklevel=3,
        )
    return key


def create_access_token(
    *,
    user_id: str,
    jti: str,
    exp: datetime,
    email: str = "",
    client_name: str = "",
) -> str:
    """Return a signed HS256 JWT. The JTI is the DB revocation key."""
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": user_id,
        "jti": jti,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if email:
        claims["email"] = email
    if client_name:
        claims["client"] = client_name
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify and return claims. Raises JWTError on invalid/expired tokens."""
    return jwt.decode(token, _secret(), algorithms=[_ALGORITHM])


def is_jwt(token: str) -> bool:
    """True if token looks like a 3-part JWT (header.payload.sig)."""
    return isinstance(token, str) and token.count(".") == 2


def decode_unverified(token: str) -> dict[str, Any]:
    """Decode a JWT payload WITHOUT verifying the signature.

    Used only for third-party social auth tokens (Apple, Google) where we
    extract claims before the upstream verification step.
    """
    raw = str(token or "").strip()
    if not raw:
        return {}
    try:
        # jose's get_unverified_claims raises JWTError on malformed tokens
        return jwt.get_unverified_claims(raw)
    except JWTError:
        return {}


__all__ = [
    "JWTError",
    "ExpiredSignatureError",
    "create_access_token",
    "decode_access_token",
    "decode_unverified",
    "is_jwt",
]