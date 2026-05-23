"""JWT signing and verification using authlib (HS256).

Public API is identical to the python-jose version — all callers unchanged.

Authlib encode/decode flow:
  jwt.encode(header, claims, key) → bytes
  jwt.decode(token, key)          → JWTClaims (dict-like, not yet validated)
  claims.validate()               → raises JoseError / ExpiredTokenError if bad
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

from authlib.jose import JsonWebToken, OctKey
from authlib.jose import JoseError
from authlib.jose.errors import ExpiredTokenError

from config import settings

_ALGORITHM = settings.jwt_algorithm
_jwt = JsonWebToken([_ALGORITHM])

# ── Exception aliases — preserve python-jose names used by all callers ────────
JWTError = JoseError
ExpiredSignatureError = ExpiredTokenError


def _key() -> OctKey:
    import os
    secret = settings.secret_key
    _unsafe = {"change-me-in-production", "secret", "changeme", "development", ""}
    is_production = os.getenv("DANAH_ENV", "development").lower() == "production"
    if is_production and (secret in _unsafe or len(secret) < 32):
        raise RuntimeError(
            "Refusing to sign JWT tokens with a weak SECRET_KEY in production. "
            "Set SECRET_KEY to a random 32+ character string in your .env file."
        )
    if secret in _unsafe:
        import warnings
        warnings.warn(
            "SECRET_KEY is default/weak — JWT tokens are NOT secure. Set SECRET_KEY in .env.",
            stacklevel=3,
        )
    return OctKey.import_key(secret.encode("utf-8"))


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
    token_bytes: bytes = _jwt.encode({"alg": _ALGORITHM}, claims, _key())
    return token_bytes.decode("utf-8")


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature and validate claims. Raises JWTError on failure."""
    raw = token.encode("utf-8") if isinstance(token, str) else token
    claims = _jwt.decode(raw, _key())
    claims.validate()
    return dict(claims)


def is_jwt(token: str) -> bool:
    """True if token looks like a 3-part JWT (header.payload.sig)."""
    return isinstance(token, str) and token.count(".") == 2


def decode_unverified(token: str) -> dict[str, Any]:
    """Decode a JWT payload WITHOUT verifying the signature.

    Used only for third-party social auth tokens (Apple, Google) where we
    extract claims before the upstream verification step.
    """
    raw = str(token or "").strip()
    if not raw or raw.count(".") != 2:
        return {}
    try:
        _, payload_b64, _ = raw.split(".")
        # Restore standard base64 padding before decoding
        remainder = len(payload_b64) % 4
        if remainder:
            payload_b64 += "=" * (4 - remainder)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


__all__ = [
    "JWTError",
    "ExpiredSignatureError",
    "create_access_token",
    "decode_access_token",
    "decode_unverified",
    "is_jwt",
]