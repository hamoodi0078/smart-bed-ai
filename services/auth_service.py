"""Mobile authentication service.

Extracted from web_server.py to break the router's dependency on the
legacy monolith.  Handles user registration, login, token lifecycle,
and Redis-backed brute-force protection.

All methods are DB-only.  The legacy JSON-store fallback that still lives
in web_server._login_mobile_user_db_first should remain active until all
existing users have a shadow row in the `users` table, then be deleted.
"""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Any

from loguru import logger

from core.security import hash_password, verify_password
from database import MobileAuthRepository, UserRepository


# ── Brute-force constants ─────────────────────────────────────────────────────
_LOCKOUT_MAX_FAILURES = 5
_LOCKOUT_WINDOW_SECONDS = 900  # 15-minute rolling window


# ── Brute-force guard ─────────────────────────────────────────────────────────


class BruteForceGuard:
    """Redis-backed per-account login failure tracker.

    Degrades gracefully to a no-op (never locked) when Redis is unavailable
    so the API stays functional in environments without Redis.
    """

    def __init__(self, redis_url: str = "") -> None:
        self._url = redis_url or os.environ.get("REDIS_URL", "")
        self._client: Any = None
        self._unavailable = False  # sticky: once Redis is proven down, stop retrying
        self._lock = threading.Lock()

    def _redis(self) -> Any:
        if self._client is not None:
            return self._client
        if self._unavailable or not self._url:
            return None
        with self._lock:
            if self._client is not None:
                return self._client
            if self._unavailable:
                return None
            try:
                import redis as _r

                # 5s timeouts: tolerant of proxied/remote Redis. A dead Redis
                # costs at most one 5s stall on the FIRST login only — the
                # sticky _unavailable flag below skips Redis for all later
                # logins in this process.
                client = _r.from_url(
                    self._url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_timeout=False,
                )
                client.ping()
                self._client = client
            except Exception:
                # Cache the failure so subsequent logins skip Redis entirely.
                self._unavailable = True
                return None
        return self._client

    @staticmethod
    def _key(email: str) -> str:
        return "login_fail:" + hashlib.sha256(email.encode()).hexdigest()[:32]

    def is_locked(self, email: str) -> bool:
        r = self._redis()
        if r is None:
            return False
        try:
            count = r.get(self._key(email))
            return count is not None and int(count) >= _LOCKOUT_MAX_FAILURES
        except Exception:
            return False

    def record_failure(self, email: str) -> int:
        r = self._redis()
        if r is None:
            return 0
        try:
            key = self._key(email)
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, _LOCKOUT_WINDOW_SECONDS, nx=True)
            results = pipe.execute()
            return int(results[0])
        except Exception:
            return 0

    def clear(self, email: str) -> None:
        r = self._redis()
        if r is None:
            return
        try:
            r.delete(self._key(email))
        except Exception:
            pass


# ── Auth service ──────────────────────────────────────────────────────────────


class AuthService:
    """Stateless authentication service — safe to instantiate once at startup."""

    def __init__(
        self,
        user_repo: UserRepository | None = None,
        token_repo: MobileAuthRepository | None = None,
        brute_force: BruteForceGuard | None = None,
    ) -> None:
        self._users = user_repo or UserRepository()
        self._tokens = token_repo or MobileAuthRepository()
        self._guard = brute_force or BruteForceGuard()

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        email: str,
        password: str,
        name: str = "",
        client_name: str = "flutter_app",
    ) -> dict[str, Any]:
        """Create a new user and issue tokens.

        Returns:
            Combined user + token response dict ready to send to the client.
        Raises:
            ValueError: if the email is already registered.
        """
        if self._users.get_user_by_email(email) is not None:
            raise ValueError("Email already registered")

        pw_hash = hash_password(password)
        user_row = self._users.create_user(
            email=email,
            password_hash=pw_hash,
            full_name=name or None,
        )
        user = _row_to_dict(user_row)
        tokens = self._tokens.issue_tokens(
            user_id=user["user_id"],
            client_name=client_name,
        )
        logger.info("auth.register user_id={} email={}", user["user_id"], email)
        return self.build_auth_response(user, tokens)

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(
        self,
        email: str,
        password: str,
        client_name: str = "flutter_app",
    ) -> dict[str, Any] | None:
        """Authenticate and issue tokens.

        Returns None on invalid credentials (caller should return 401).
        Brute-force failures are recorded automatically; call is_locked()
        before calling this method if you want to short-circuit with 429.
        """
        user_row = self._users.get_user_by_email(email)
        if user_row is None:
            self._guard.record_failure(email)
            return None

        stored_hash = str(getattr(user_row, "password_hash", "") or "")
        if not verify_password(password, stored_hash):
            self._guard.record_failure(email)
            return None

        self._guard.clear(email)
        user = _row_to_dict(user_row)
        tokens = self._tokens.issue_tokens(
            user_id=user["user_id"],
            client_name=client_name,
        )
        logger.info("auth.login user_id={} email={}", user["user_id"], email)
        return self.build_auth_response(user, tokens)

    # ── Token operations ──────────────────────────────────────────────────────

    def refresh(self, refresh_token: str) -> dict[str, Any] | None:
        """Rotate a refresh token and return a fresh auth response.

        Returns None if the token is invalid, expired, or already revoked.
        """
        tokens = self._tokens.refresh_tokens(refresh_token)
        if not isinstance(tokens, dict) or not tokens:
            logger.warning("auth.refresh token_not_found_or_expired")
            return None

        session = self._tokens.validate_access_token(str(tokens.get("access_token", "") or ""))
        if not session:
            return None

        user_row = self._users.get_user_by_id(str(session.get("user_id", "") or ""))
        if user_row is None:
            return None

        user = _row_to_dict(user_row)
        logger.info("auth.refresh user_id={}", user["user_id"])
        return self.build_auth_response(user, tokens)

    def logout(self, *, access_token: str = "", refresh_token: str = "") -> bool:
        """Revoke the provided tokens. Returns True if anything was revoked."""
        return bool(
            self._tokens.revoke_tokens(
                access_token=access_token,
                refresh_token=refresh_token,
            )
        )

    def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke every active session for a user (e.g. after password reset)."""
        return self._tokens.revoke_all_tokens_for_user(user_id)

    def get_user_by_token(self, access_token: str) -> dict[str, Any] | None:
        """Validate an access token and return the user dict, or None."""
        session = self._tokens.validate_access_token(access_token)
        if not session:
            return None
        user_row = self._users.get_user_by_id(str(session.get("user_id", "") or ""))
        if user_row is None:
            return None
        return _row_to_dict(user_row)

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Fetch a user by id and return the standard user dict, or None.

        For callers that have already validated the token (e.g. via the
        get_current_user dependency) and only need the DB identity.
        """
        user_row = self._users.get_user_by_id(str(user_id or "").strip())
        if user_row is None:
            return None
        return _row_to_dict(user_row)

    # ── Cookie-flow helpers (create/verify without token issuance) ───────────

    def create_user_only(
        self,
        email: str,
        password: str,
        name: str = "",
    ) -> dict[str, Any]:
        """Create a user and return the user dict WITHOUT issuing tokens.

        Used by cookie-based auth flows that manage their own sessions.
        Raises ValueError if the email is already registered.
        """
        if self._users.get_user_by_email(email) is not None:
            raise ValueError("Email already registered")

        pw_hash = hash_password(password)
        user_row = self._users.create_user(
            email=email,
            password_hash=pw_hash,
            full_name=name or None,
        )
        logger.info("auth.create_user_only user_id={} email={}", getattr(user_row, "id", ""), email)
        return _row_to_dict(user_row)

    def verify_user(self, email: str, password: str) -> dict[str, Any] | None:
        """Verify credentials and return user dict WITHOUT issuing tokens.

        Returns None on wrong password or unknown email.
        Used by cookie-based auth flows.  Brute-force counters are updated.
        """
        user_row = self._users.get_user_by_email(email)
        if user_row is None:
            self._guard.record_failure(email)
            return None
        stored_hash = str(getattr(user_row, "password_hash", "") or "")
        if not verify_password(password, stored_hash):
            self._guard.record_failure(email)
            return None
        self._guard.clear(email)
        return _row_to_dict(user_row)

    # ── Brute-force passthrough ───────────────────────────────────────────────

    def is_locked(self, email: str) -> bool:
        return self._guard.is_locked(email)

    # ── Response builder ──────────────────────────────────────────────────────

    @staticmethod
    def build_auth_response(user: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
        """Build the standard mobile auth JSON response."""
        return {
            "ok": True,
            "user": {
                "user_id": str(user.get("user_id", "") or ""),
                "email": str(user.get("email", "") or ""),
                "name": str(user.get("name", "") or ""),
                "client_name": str(tokens.get("client_name", "") or ""),
            },
            "access_token": str(tokens.get("access_token", "") or ""),
            "token_type": "Bearer",
            "expires_at": str(tokens.get("expires_at", "") or ""),
            "expires_in": int(tokens.get("expires_in", 3600) or 3600),
            "refresh_token": str(tokens.get("refresh_token", "") or ""),
            "refresh_expires_at": str(tokens.get("refresh_expires_at", "") or ""),
        }


# ── Internal helpers ──────────────────────────────────────────────────────────


def _row_to_dict(user_row: Any) -> dict[str, Any]:
    """Convert a User ORM row to the standard user payload dict."""
    return {
        "user_id": str(getattr(user_row, "id", "") or ""),
        "email": str(getattr(user_row, "email", "") or ""),
        "name": str(getattr(user_row, "full_name", "") or ""),
        "role": str(getattr(user_row, "role", "user") or "user"),
        "subscription_status": str(getattr(user_row, "subscription_status", "free") or "free"),
    }


# ── Module-level singleton ────────────────────────────────────────────────────

_auth_service: AuthService | None = None
_auth_service_lock = threading.Lock()


def get_auth_service() -> AuthService:
    """Return the process-level AuthService singleton (lazy-initialised)."""
    global _auth_service
    if _auth_service is None:
        with _auth_service_lock:
            if _auth_service is None:
                _auth_service = AuthService()
    return _auth_service


__all__ = ["AuthService", "BruteForceGuard", "get_auth_service"]
