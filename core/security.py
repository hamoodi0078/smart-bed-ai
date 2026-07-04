"""Centralised password hashing using bcrypt.

All password operations go through this module so the hashing scheme
can be upgraded in one place without touching call sites.

Preferred: raw bcrypt package (compatible with bcrypt 4.x and 5.x)
Fallback:  passlib CryptContext — passlib 1.7.4 is unmaintained and breaks
           with bcrypt >= 4.1 (missing __about__, 72-byte ValueError), so it
           is only used when the raw bcrypt package is absent.
Both unavailable: RuntimeError on hash, False on verify

Hashes are interchangeable: passlib's bcrypt scheme produces standard
"$2b$..." strings that bcrypt.checkpw verifies, and vice versa.
"""

from __future__ import annotations

import hashlib
import hmac

from loguru import logger

try:
    import bcrypt as _bcrypt

    _BCRYPT_AVAILABLE = True
except ImportError:
    _bcrypt = None  # type: ignore[assignment]
    _BCRYPT_AVAILABLE = False

try:
    from passlib.context import CryptContext as _CryptContext

    _pwd_context = _CryptContext(schemes=["bcrypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except ImportError:
    _CryptContext = None  # type: ignore[assignment,misc]
    _pwd_context = None
    _PASSLIB_AVAILABLE = False

# bcrypt's algorithmic input limit. bcrypt < 4 truncated silently;
# bcrypt >= 4.1 raises ValueError instead, so we truncate explicitly.
_BCRYPT_MAX_SECRET_BYTES = 72


def _is_legacy_sha256(stored: str) -> bool:
    """Detect a bare SHA-256 hex hash (64 lowercase hex chars)."""
    text = (stored or "").strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*.

    Uses the raw bcrypt package when available, falls back to passlib.
    Raises RuntimeError if neither is installed.
    """
    secret = (password or "").encode("utf-8")[:_BCRYPT_MAX_SECRET_BYTES]

    if _BCRYPT_AVAILABLE and _bcrypt is not None:
        return _bcrypt.hashpw(secret, _bcrypt.gensalt()).decode("utf-8")

    if _PASSLIB_AVAILABLE and _pwd_context is not None:
        return _pwd_context.hash(secret.decode("utf-8", errors="ignore"))

    raise RuntimeError("No password hashing backend available. Install bcrypt or passlib[bcrypt].")


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify *password* against *stored_hash*.

    Handles three cases:
    - bcrypt hashes           (preferred, raw bcrypt.checkpw)
    - passlib bcrypt hashes   (same "$2b$" format — either backend verifies both)
    - legacy bare SHA-256 hex (migration path — 64 char hex strings)

    Returns False on any error rather than raising.
    """
    secret = (password or "").encode("utf-8")
    text = (stored_hash or "").strip()
    if not text:
        return False

    # Legacy SHA-256 migration path
    if _is_legacy_sha256(text):
        legacy = hashlib.sha256(secret).hexdigest()
        return hmac.compare_digest(text.lower(), legacy)

    truncated = secret[:_BCRYPT_MAX_SECRET_BYTES]

    # raw bcrypt path (preferred)
    if _BCRYPT_AVAILABLE and _bcrypt is not None:
        try:
            return bool(_bcrypt.checkpw(truncated, text.encode("utf-8")))
        except Exception as exc:
            logger.debug("bcrypt verify error: {}", exc)
            return False

    # passlib fallback
    if _PASSLIB_AVAILABLE and _pwd_context is not None:
        try:
            return bool(_pwd_context.verify(truncated.decode("utf-8", errors="ignore"), text))
        except Exception as exc:
            logger.debug("passlib verify error: {}", exc)
            return False

    return False


def needs_rehash(stored_hash: str) -> bool:
    """Return True if *stored_hash* should be rehashed (legacy or deprecated scheme).

    Call after a successful verify; if True, replace the stored hash with a
    fresh ``hash_password()`` result.
    """
    if _is_legacy_sha256(stored_hash):
        return True
    if _PASSLIB_AVAILABLE and _pwd_context is not None:
        try:
            return bool(_pwd_context.needs_update(stored_hash))
        except Exception:
            return False
    return False


# ---------------------------------------------------------------------------
# CORS Security Configuration
# ---------------------------------------------------------------------------


def get_secure_cors_origins() -> list[str]:
    """Get secure CORS origins based on environment.

    Returns:
        List of allowed CORS origins
    """
    import os
    from config import settings

    # In production, only allow explicitly configured origins
    if os.getenv("DANAH_ENV") == "production":
        origins_str = os.getenv("WEB_ALLOWED_ORIGINS", "")
        if not origins_str:
            logger.warning(
                "Production mode but no WEB_ALLOWED_ORIGINS set - defaulting to restrictive policy"
            )
            return []

        origins = [o.strip() for o in origins_str.split(",") if o.strip()]

        # Validate origins don't contain wildcards in production
        for origin in origins:
            if "*" in origin and origin != "*":
                logger.error("Wildcard CORS origin not allowed in production: {}", origin)
                raise ValueError(f"Wildcard CORS origin not allowed in production: {origin}")

        logger.info("Production CORS origins: {}", origins)
        return origins

    # Development: allow localhost variants
    return [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


def validate_cors_origin(origin: str) -> bool:
    """Validate a CORS origin matches security requirements.

    Args:
        origin: Origin URL to validate

    Returns:
        True if origin is valid
    """
    import re

    if not origin:
        return False

    # Must start with http:// or https://
    if not origin.startswith(("http://", "https://")):
        return False

    # In production, enforce HTTPS
    import os

    if os.getenv("DANAH_ENV") == "production" and not origin.startswith("https://"):
        logger.warning("Non-HTTPS origin rejected in production: {}", origin)
        return False

    # Reject origins with credentials in URL
    if "@" in origin:
        return False

    return True
