"""In-memory sliding-window rate limiter middleware for FastAPI."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from constants.limits import RateLimits


class _SlidingWindowCounter:
    """Thread-safe sliding window rate counter per client key."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        timestamps = self._windows[key]
        self._windows[key] = [t for t in timestamps if t > cutoff]
        if len(self._windows[key]) >= max_requests:
            return False
        self._windows[key].append(now)
        return True

    def cleanup(self, max_age_seconds: int = 300) -> None:
        now = time.monotonic()
        cutoff = now - max_age_seconds
        stale_keys = [k for k, v in self._windows.items() if not v or v[-1] < cutoff]
        for k in stale_keys:
            del self._windows[k]


_counter = _SlidingWindowCounter()
_cleanup_last = time.monotonic()
_CLEANUP_INTERVAL = 120.0


import ipaddress
import os

_TRUSTED_PROXY_CIDRS_RAW = os.environ.get("TRUSTED_PROXY_CIDR", "127.0.0.1/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
_TRUSTED_PROXY_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
for _cidr in _TRUSTED_PROXY_CIDRS_RAW.split(","):
    _cidr = _cidr.strip()
    if _cidr:
        try:
            _TRUSTED_PROXY_NETWORKS.append(ipaddress.ip_network(_cidr, strict=False))
        except ValueError:
            logger.warning("Invalid TRUSTED_PROXY_CIDR entry ignored: {}", _cidr)


def _is_trusted_proxy(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _TRUSTED_PROXY_NETWORKS)
    except ValueError:
        return False


def _client_ip(request: Request) -> str:
    client = request.client
    direct_host = client.host if client else None
    # Only trust X-Forwarded-For when the direct connection is from a known proxy.
    if direct_host and _is_trusted_proxy(direct_host):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if direct_host:
        return direct_host
    return "unknown"


def _route_limit(path: str, method: str) -> int:
    """Return the per-minute rate limit for a given route."""
    path_lower = path.lower()

    # OTP must be tighter than general auth — prevents SMS flooding and code brute-force.
    if "/otp/" in path_lower or path_lower.endswith("/otp/request") or path_lower.endswith("/otp/verify"):
        return RateLimits.OTP_PER_MINUTE

    if "/auth/" in path_lower or path_lower.endswith("/login") or path_lower.endswith("/register"):
        return RateLimits.AUTH_PER_MINUTE

    if "/chat" in path_lower or "/ai/" in path_lower:
        return RateLimits.CHAT_PER_MINUTE

    if "/admin/" in path_lower:
        return RateLimits.ADMIN_PER_MINUTE

    if "/billing/webhook" in path_lower:
        return RateLimits.BILLING_WEBHOOK_PER_MINUTE

    return RateLimits.GENERAL_PER_MINUTE


_EXEMPT_PATHS = {"/healthz", "/metrics", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter that keys on client IP + route category."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        global _cleanup_last

        path = str(request.url.path or "/")
        method = str(request.method or "GET").upper()

        if path in _EXEMPT_PATHS or method == "OPTIONS":
            return await call_next(request)

        now = time.monotonic()
        if now - _cleanup_last > _CLEANUP_INTERVAL:
            _counter.cleanup()
            _cleanup_last = now

        client_key = _client_ip(request)
        limit = _route_limit(path, method)
        rate_key = f"{client_key}:{path}"

        if not _counter.is_allowed(rate_key, limit, window_seconds=60):
            logger.warning(
                "Rate limit exceeded: client={} path={} limit={}/min",
                client_key,
                path,
                limit,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "ok": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Too many requests. Limit: {limit}/min.",
                        "retry_after": 60,
                    },
                },
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response
