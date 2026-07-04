"""Portable cookie-session helpers for web/admin auth routes.

Extracted from web_server.py so routers can manage session cookies
without importing the legacy monolith.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response

from config import settings


# ── Origin enforcement ────────────────────────────────────────────────────────


def _origin_of(url: str) -> str:
    """Return the ``scheme://host[:port]`` origin of *url*, lowercased.

    Origin headers are already bare origins; Referer headers carry a path we
    must strip. Returns "" when the URL has no scheme+host.
    """
    parsed = urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def enforce_same_origin(request: Request) -> None:
    """Raise HTTP 403 if the request's Origin/Referer is not in the allow-list.

    Allows:
    - Requests with no Origin header (server-to-server, curl, Postman).
    - Requests whose Origin EXACTLY matches a configured CORS origin.
    - localhost/127.0.0.1 origins in non-production environments.

    Matching is exact on scheme://host:port. A prefix match (the previous
    behavior) would let ``https://danah.app.evil.com`` pass the allow-list
    for ``https://danah.app``.
    """
    raw_origin = (
        str(request.headers.get("Origin", "") or "").strip()
        or str(request.headers.get("Referer", "") or "").strip()
    )
    if not raw_origin:
        return

    origin = _origin_of(raw_origin)
    if not origin:
        raise HTTPException(status_code=403, detail="Cross-origin request not allowed")

    is_production = os.getenv("DANAH_ENV", "development").lower() == "production"

    if not is_production:
        host = urlparse(origin).hostname or ""
        backend_host = os.getenv("BACKEND_HOST", "localhost")
        if host in ("localhost", "127.0.0.1", "::1", backend_host):
            return

    allowed_raw = str(settings.web_allowed_origins_raw or "").strip()
    allowed = {_origin_of(o) for o in allowed_raw.split(",") if o.strip()}
    allowed.discard("")

    if not allowed:
        return

    if origin in allowed:
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
