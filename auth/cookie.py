"""Portable cookie-session helpers for web/admin auth routes.

Extracted from web_server.py so routers can manage session cookies
without importing the legacy monolith.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, Response

from config import settings


# ── Origin enforcement ────────────────────────────────────────────────────────


def enforce_same_origin(request: Request) -> None:
    """Raise HTTP 403 if the request's Origin/Referer is not in the allow-list.

    Allows:
    - Requests with no Origin header (server-to-server, curl, Postman).
    - Requests whose Origin matches a configured CORS origin.
    - localhost/127.0.0.1 origins in non-production environments.
    """
    import os

    origin = (
        str(request.headers.get("Origin", "") or "").strip()
        or str(request.headers.get("Referer", "") or "").strip()
    )
    if not origin:
        return

    is_production = os.getenv("DANAH_ENV", "development").lower() == "production"

    if not is_production:
        backend_host = os.getenv("BACKEND_HOST", "localhost")
        localhost_hints = ("localhost", "127.0.0.1", backend_host)
        if any(hint in origin for hint in localhost_hints):
            return

    allowed_raw = str(settings.web_allowed_origins_raw or "").strip()
    allowed = [o.strip() for o in allowed_raw.split(",") if o.strip()]

    if not allowed or "*" in allowed:
        return

    if any(origin.startswith(o) for o in allowed):
        return

    raise HTTPException(status_code=403, detail="Cross-origin request not allowed")


# ── Cookie writers ────────────────────────────────────────────────────────────

_COOKIE_NAMES = ("sb_user_token", "sb_admin_token")


def set_session_cookie(
    response: Response,
    name: str,
    token: str,
    max_age: int,
    request: Request,
) -> None:
    """Write a signed, HTTP-only session cookie."""
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    """Delete all session cookies (user + admin)."""
    for name in _COOKIE_NAMES:
        response.delete_cookie(key=name, path="/")


__all__ = ["enforce_same_origin", "set_session_cookie", "clear_session_cookies"]
