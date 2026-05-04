"""Rate limiting and session limit constants."""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


class RateLimits:
    """Per-endpoint rate limits (requests per minute)."""

    AUTH_PER_MINUTE: int = _env_int("RATE_LIMIT_AUTH_PER_MINUTE", 10)
    # OTP endpoints are stricter than general auth to prevent SMS flood/brute-force.
    OTP_PER_MINUTE: int = _env_int("RATE_LIMIT_OTP_PER_MINUTE", 5)
    CHAT_PER_MINUTE: int = _env_int("RATE_LIMIT_CHAT_PER_MINUTE", 30)
    GENERAL_PER_MINUTE: int = _env_int("RATE_LIMIT_GENERAL_PER_MINUTE", 60)
    ADMIN_PER_MINUTE: int = _env_int("RATE_LIMIT_ADMIN_PER_MINUTE", 30)
    BILLING_WEBHOOK_PER_MINUTE: int = _env_int("RATE_LIMIT_BILLING_WEBHOOK_PER_MINUTE", 20)


class SessionLimits:
    """Session and connection limits."""

    MAX_CHAT_ENGINES: int = 200
    DEVICE_STALE_WINDOW_SECONDS: int = 180
    SCENE_PREVIEW_SECONDS: float = 3.0
    MAX_USERS_LIST: int = 5000
    MAX_EVENTS_LIST: int = 500
    MAX_EMOTIONAL_FOLLOWUPS: int = 40
    SLEEP_HISTORY_MAX_SESSIONS: int = 365
