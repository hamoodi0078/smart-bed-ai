"""Shared slowapi Limiter instance for per-route rate limiting.

Usage in route files:
    from api.limiter import limiter

    @router.post("/sensitive-endpoint")
    @limiter.limit("5/minute")
    async def my_endpoint(request: Request):
        ...

The global sliding-window middleware (RateLimitMiddleware) still enforces
category-based limits across all routes. This limiter adds per-route
granularity for endpoints that need tighter control.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from constants.limits import RateLimits

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{RateLimits.GENERAL_PER_MINUTE}/minute"],
    headers_enabled=True,
)
