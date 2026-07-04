"""croniter-based cron expression utilities.

Used by AutomationRegistry to support cron-scheduled automations alongside
the existing cooldown-based system.

Public API:
  is_valid_cron(expr)                        → bool
  next_fire(expr, now)                       → datetime | None
  prev_fire(expr, now)                       → datetime | None
  should_fire_now(expr, now, tolerance_s)    → bool
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

try:
    from croniter import croniter as _croniter

    _CRONITER_AVAILABLE = True
except ImportError:
    _croniter = None  # type: ignore[assignment]
    _CRONITER_AVAILABLE = False


def is_valid_cron(expr: str) -> bool:
    """Return True when *expr* is a valid 5-field cron expression."""
    if not _CRONITER_AVAILABLE or _croniter is None:
        return False
    try:
        return bool(_croniter.is_valid(str(expr or "").strip()))
    except Exception:
        return False


def next_fire(expr: str, now: datetime | None = None) -> datetime | None:
    """Return the next datetime the cron fires after *now* (UTC-aware)."""
    if not _CRONITER_AVAILABLE or _croniter is None:
        return None
    try:
        base = now or datetime.now(timezone.utc)
        return _croniter(expr, base).get_next(datetime)
    except Exception as exc:
        logger.debug("croniter next_fire failed expr={!r}: {}", expr, exc)
        return None


def prev_fire(expr: str, now: datetime | None = None) -> datetime | None:
    """Return the most recent datetime the cron fired before *now* (UTC-aware)."""
    if not _CRONITER_AVAILABLE or _croniter is None:
        return None
    try:
        base = now or datetime.now(timezone.utc)
        return _croniter(expr, base).get_prev(datetime)
    except Exception as exc:
        logger.debug("croniter prev_fire failed expr={!r}: {}", expr, exc)
        return None


def should_fire_now(
    expr: str,
    now: datetime | None = None,
    tolerance_seconds: int = 60,
) -> bool:
    """Return True when *now* is within *tolerance_seconds* of a cron firing.

    The automation registry calls this once per tick (≈ every minute) with a
    60-second tolerance so a cron firing is never missed even if the tick lands
    slightly late.
    """
    if not _CRONITER_AVAILABLE or _croniter is None:
        return False
    base = now or datetime.now(timezone.utc)
    try:
        last = _croniter(expr, base).get_prev(datetime)
        return abs((base - last).total_seconds()) <= int(tolerance_seconds)
    except Exception as exc:
        logger.debug("croniter should_fire_now failed expr={!r}: {}", expr, exc)
        return False
