"""Sliding-window rate limiter middleware for FastAPI.

Uses Redis sorted sets for distributed state so limits hold across all
Gunicorn workers and container restarts. Falls back to an in-memory
counter if Redis is unavailable (single-instance deployments / dev).
"""

from __future__ import annotations

import ipaddress
import os
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from constants.limits import RateLimits


# ── Redis-backed sliding window ───────────────────────────────────────────────


class _RedisCounter:
    """Sliding-window counter backed by Redis sorted sets.

    Each key is a Redis sorted set where members are unique request IDs
    and scores are Unix timestamps. Old entries are pruned on every check.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        window_start = now - window_seconds
        member = f"{now:.6f}"  # unique enough within a single second

        pipe = self._redis.pipeline()
        # Remove timestamps outside the window
        pipe.zremrangebyscore(key, "-inf", window_start)
        # Add current request
        pipe.zadd(key, {member: now})
        # Count requests in window (including this one)
        pipe.zcard(key)
        # Auto-expire the key so Redis doesn't accumulate stale sets
        pipe.expire(key, window_seconds + 5)
        results = await pipe.execute()
        count: int = results[2]
        return count <= max_requests

    async def cleanup(self) -> None:
        pass  # Redis TTL handles cleanup


# ── In-memory fallback ────────────────────────────────────────────────────────


class _InMemoryCounter:
    """Thread-safe in-memory sliding window. Single-process only."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._cleanup_at = time.monotonic() + 120.0

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        timestamps = self._windows[key]
        self._windows[key] = [t for t in timestamps if t > cutoff]
        if len(self._windows[key]) >= max_requests:
            return False
        self._windows[key].append(now)
        return True

    async def cleanup(self) -> None:
        now = time.monotonic()
        if now < self._cleanup_at:
            return
        self._cleanup_at = now + 120.0
        cutoff = now - 300.0
        stale = [k for k, v in self._windows.items() if not v or v[-1] < cutoff]
        for k in stale:
            del self._windows[k]


# ── Counter factory ───────────────────────────────────────────────────────────

_counter: _RedisCounter | _InMemoryCounter | None = None


async def _get_counter() -> _RedisCounter | _InMemoryCounter:
    global _counter
    if _counter is not None:
        return _counter

    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            import redis.asyncio as aioredis

            # 5s timeouts: tolerant of proxied/remote Redis (e.g. Railway public
            # endpoint) while still bounding the stall when Redis is down. The
            # result is cached in _counter either way, so only the first request
            # ever pays this cost.
            client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=False,
            )
            await client.ping()
            _counter = _RedisCounter(client)
            logger.info("Rate limiter: using Redis backend ({})", redis_url.split("@")[-1])
            return _counter
        except Exception as exc:
            logger.warning("Rate limiter: Redis unavailable ({}), falling back to in-memory", exc)

    _counter = _InMemoryCounter()
    logger.warning("Rate limiter: using in-memory backend — limits are per-process only")
    return _counter


# ── IP resolution (trusted proxy aware) ──────────────────────────────────────

_TRUSTED_PROXY_CIDRS_RAW = os.environ.get(
    "TRUSTED_PROXY_CIDR", "127.0.0.1/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
)
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
    if direct_host and _is_trusted_proxy(direct_host):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_host or "unknown"


# ── Per-route limits ──────────────────────────────────────────────────────────


def _route_limit(path: str, method: str) -> int:
    path_lower = path.lower()
    if (
        "/otp/" in path_lower
        or path_lower.endswith("/otp/request")
        or path_lower.endswith("/otp/verify")
    ):
        return RateLimits.OTP_PER_MINUTE
    if path_lower.endswith("/login") or path_lower.endswith("/register"):
        return RateLimits.AUTH_LOGIN_PER_MINUTE
    if "/auth/" in path_lower:
        return RateLimits.AUTH_PER_MINUTE
    if "/chat" in path_lower or "/ai/" in path_lower:
        return RateLimits.CHAT_PER_MINUTE
    if "/admin/" in path_lower:
        return RateLimits.ADMIN_PER_MINUTE
    if "/billing/webhook" in path_lower:
        return RateLimits.BILLING_WEBHOOK_PER_MINUTE
    return RateLimits.GENERAL_PER_MINUTE


_EXEMPT_PATHS = {"/healthz", "/metrics", "/docs", "/openapi.json", "/redoc"}


# ── Middleware ────────────────────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed on client IP + route category."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import sys

        if "pytest" in sys.modules or os.getenv("DANAH_ENV", "development").lower() in (
            "test",
            "testing",
        ):
            return await call_next(request)

        path = str(request.url.path or "/")
        method = str(request.method or "GET").upper()

        if path in _EXEMPT_PATHS or method == "OPTIONS":
            return await call_next(request)

        counter = await _get_counter()
        await counter.cleanup()

        client_ip = _client_ip(request)
        limit = _route_limit(path, method)
        rate_key = f"rl:{client_ip}:{path}"

        allowed = await counter.is_allowed(rate_key, limit, window_seconds=60)
        if not allowed:
            logger.warning(
                "Rate limit exceeded: client={} path={} limit={}/min",
                client_ip,
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
