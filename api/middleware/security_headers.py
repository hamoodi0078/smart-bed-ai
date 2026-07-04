"""Security-headers middleware — adds defensive HTTP headers to every response.

Headers applied:
  X-Frame-Options            — prevents clickjacking
  X-Content-Type-Options     — prevents MIME-type sniffing
  Referrer-Policy            — limits referrer leakage
  Content-Security-Policy    — restricts resource origins
  Permissions-Policy         — disables browser features not needed
  Strict-Transport-Security  — only set when HTTPS is detected
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_HSTS_MAX_AGE = 63_072_000  # 2 years

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none';"
)

_PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security-related HTTP headers on every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["Permissions-Policy"] = _PERMISSIONS

        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
            or os.getenv("DANAH_ENV", "development").lower() == "production"
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={_HSTS_MAX_AGE}; includeSubDomains; preload"
            )

        return response
