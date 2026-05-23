"""Islamic calendar–based automations: Eid al-Fitr, Eid al-Adha, and Jumu'ah.

Usage — call ``register_islamic_automations(registry)`` once at app startup
(e.g. in ``api/service_registry.py``) to wire these into the runtime:

    from automations.islamic_automations import register_islamic_automations
    register_islamic_automations(registry)

The automations use the Hijri date from ``islamic_mode.islamic_calendar`` to
determine when Eid begins and integrate with the existing LED / notification /
scene effect system through the standard ``Effect`` return type.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from automations.base import Automation
from core.types import Effect

_LOG = logging.getLogger("automations.islamic")

# ── Hijri date helpers ────────────────────────────────────────────────────────

def _hijri_today() -> tuple[int, int, int]:
    """Return (year, month, day) in the Hijri calendar for today."""
    try:
        from islamic_mode.islamic_calendar import IslamicCalendarService
        cal = IslamicCalendarService()
        info = cal.get_hijri_date()
        return (
            int(info.get("hijri_year", 0) or 0),
            int(info.get("hijri_month_number", 0) or 0),
            int(info.get("hijri_day", 0) or 0),
        )
    except Exception as exc:
        _LOG.debug("Hijri date lookup failed: %s", exc)
        return (0, 0, 0)


def _is_eid_al_fitr() -> bool:
    """1 Shawwal (month 10)."""
    _, month, day = _hijri_today()
    return month == 10 and day == 1


def _is_eid_al_adha() -> bool:
    """10 Dhu al-Hijjah (month 12)."""
    _, month, day = _hijri_today()
    return month == 12 and day == 10


def _is_jumuah() -> bool:
    """Friday (weekday 4 in Python's 0=Monday convention)."""
    return datetime.date.today().weekday() == 4


# ── Effect factories ──────────────────────────────────────────────────────────

def _eid_effect(eid_name: str) -> list[Effect]:
    """Return a bundle of effects for an Eid morning."""
    return [
        Effect(
            type="notification",
            payload={
                "title": f"🌙 {eid_name} Mubarak!",
                "body": (
                    f"Wishing you and your family a blessed {eid_name}. "
                    "Taqabbal Allahu minna wa minkum."
                ),
                "notification_type": "eid_greeting",
                "priority": "high",
            },
        ),
        Effect(
            type="scene",
            payload={
                "scene_name": "eid_morning",
                "led_color": "#FFD700",
                "brightness": 85,
                "fade_seconds": 30,
                "message": f"{eid_name} Mubarak!",
            },
        ),
        Effect(
            type="tts",
            payload={
                "text": f"Eid Mubarak! {eid_name}. Taqabbal Allahu minna wa minkum.",
                "priority": "high",
            },
        ),
    ]


def _jumuah_effect(ctx: dict[str, Any]) -> list[Effect]:
    """Return a gentle Jumu'ah reminder effect."""
    prayer_time = ctx.get("dhuhr_time", "12:15")
    return [
        Effect(
            type="notification",
            payload={
                "title": "جمعة مباركة — Jumu'ah Mubarak",
                "body": f"Friday prayer (Dhuhr) is at {prayer_time}. May Allah accept from all of us.",
                "notification_type": "jumuah_reminder",
                "priority": "normal",
            },
        ),
        Effect(
            type="scene",
            payload={
                "scene_name": "jumuah_morning",
                "led_color": "#90EE90",
                "brightness": 60,
                "fade_seconds": 15,
            },
        ),
    ]


# ── Automation definitions ────────────────────────────────────────────────────

def _eid_fitr_trigger(ctx: dict[str, Any]) -> bool:
    return _is_eid_al_fitr()


def _eid_fitr_action(ctx: dict[str, Any]) -> list[Effect]:
    _LOG.info("Eid al-Fitr automation fired")
    return _eid_effect("Eid al-Fitr")


def _eid_adha_trigger(ctx: dict[str, Any]) -> bool:
    return _is_eid_al_adha()


def _eid_adha_action(ctx: dict[str, Any]) -> list[Effect]:
    _LOG.info("Eid al-Adha automation fired")
    return _eid_effect("Eid al-Adha")


def _jumuah_trigger(ctx: dict[str, Any]) -> bool:
    if not _is_jumuah():
        return False
    # Only fire in the morning window (08:00-11:30) so we don't spam all day
    now_local: datetime.datetime | None = ctx.get("now_local")
    if now_local is None:
        return False
    return datetime.time(8, 0) <= now_local.time() <= datetime.time(11, 30)


def _jumuah_action(ctx: dict[str, Any]) -> list[Effect]:
    _LOG.info("Jumu'ah reminder automation fired")
    return _jumuah_effect(ctx)


# ── Jumu'ah window dedup key — only one reminder per Friday ──────────────────

def _jumuah_window_key(ctx: dict[str, Any]) -> str:
    """Return today's ISO date so the automation only fires once per Friday."""
    now: datetime.datetime | None = ctx.get("now_local")
    if now is not None:
        return f"jumuah:{now.date().isoformat()}"
    return f"jumuah:{datetime.date.today().isoformat()}"


def _eid_window_key(ctx: dict[str, Any]) -> str:
    """Return the current Hijri date string as dedup key — fires once per Eid day."""
    year, month, day = _hijri_today()
    return f"eid:{year}-{month:02d}-{day:02d}"


# ── Registration helper ───────────────────────────────────────────────────────

EID_AL_FITR_AUTOMATION = Automation(
    name="eid_al_fitr_greeting",
    trigger=_eid_fitr_trigger,
    action=_eid_fitr_action,
    # Cooldown must be ≥ 60 (registry minimum); 23h ensures it won't re-fire
    # intra-day while the Hijri date stays the same.
    cooldown_minutes=1380,
    criticality="non_critical",
    window_key=_eid_window_key,
)

EID_AL_ADHA_AUTOMATION = Automation(
    name="eid_al_adha_greeting",
    trigger=_eid_adha_trigger,
    action=_eid_adha_action,
    cooldown_minutes=1380,
    criticality="non_critical",
    window_key=_eid_window_key,
)

JUMUAH_REMINDER_AUTOMATION = Automation(
    name="jumuah_friday_reminder",
    trigger=_jumuah_trigger,
    action=_jumuah_action,
    # 60-min cooldown is the registry minimum; window_key prevents same-day repeats.
    cooldown_minutes=60,
    criticality="non_critical",
    window_key=_jumuah_window_key,
)


def register_islamic_automations(registry: Any) -> None:
    """Register all Islamic calendar automations into *registry*.

    Call once at startup from ``api/service_registry.py``::

        from automations.islamic_automations import register_islamic_automations
        register_islamic_automations(registry)
    """
    registry.register(EID_AL_FITR_AUTOMATION)
    registry.register(EID_AL_ADHA_AUTOMATION)
    registry.register(JUMUAH_REMINDER_AUTOMATION)
    _LOG.info("Islamic automations registered: Eid al-Fitr, Eid al-Adha, Jumu'ah")
