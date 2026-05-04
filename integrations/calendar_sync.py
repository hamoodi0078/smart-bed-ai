"""Calendar integration for Smart Bed AI.

Syncs with phone calendar (Google/Apple) via API, parses next-day events,
auto-adjusts wake time and bedtime suggestions based on schedule,
and provides morning briefings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("integrations.calendar_sync")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CalendarSync:
    """Manages calendar integration for schedule-aware automations."""

    def __init__(
        self,
        *,
        default_prep_minutes: int = 60,
        min_sleep_hours: float = 7.0,
        max_sleep_hours: float = 9.0,
    ):
        self._prep_minutes = max(15, int(default_prep_minutes))
        self._min_sleep = max(5.0, float(min_sleep_hours))
        self._max_sleep = max(self._min_sleep + 1, float(max_sleep_hours))
        self._cached_events: list[dict[str, Any]] = []
        self._cache_date = ""

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("calendar", {})
        cal = profile["calendar"]
        cal.setdefault("enabled", True)
        cal.setdefault("prep_minutes", self._prep_minutes)
        cal.setdefault("auto_alarm_enabled", True)
        cal.setdefault("morning_brief_enabled", True)
        cal.setdefault("events_cache", [])
        cal.setdefault("last_sync_at", "")

    # ------------------------------------------------------------------
    # Event ingestion (called from mobile app or API)
    # ------------------------------------------------------------------

    def sync_events(self, profile: dict, events: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
        """Receive calendar events from mobile app."""
        now = now or _utcnow()
        self.ensure_shape(profile)

        normalized: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            norm = {
                "title": str(event.get("title", "")).strip()[:200],
                "start_time": str(event.get("start_time", "")).strip(),
                "end_time": str(event.get("end_time", "")).strip(),
                "all_day": bool(event.get("all_day", False)),
                "location": str(event.get("location", "")).strip()[:200],
                "is_travel": bool(event.get("is_travel", False)),
            }
            if norm["title"] and norm["start_time"]:
                normalized.append(norm)

        profile["calendar"]["events_cache"] = normalized[-50:]
        profile["calendar"]["last_sync_at"] = now.isoformat()
        self._cached_events = normalized
        self._cache_date = now.date().isoformat()

        logger.info("Calendar synced: %d events", len(normalized))
        return {"synced": True, "events_count": len(normalized)}

    # ------------------------------------------------------------------
    # Schedule analysis
    # ------------------------------------------------------------------

    def get_tomorrow_schedule(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Get tomorrow's schedule with first event and suggested wake/bed times."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        events = profile.get("calendar", {}).get("events_cache", [])
        tomorrow = (now + timedelta(days=1)).date()
        tomorrow_str = tomorrow.isoformat()

        tomorrow_events: list[dict[str, Any]] = []
        for event in events:
            try:
                start = datetime.fromisoformat(str(event.get("start_time", "")))
                if start.date() == tomorrow:
                    tomorrow_events.append(event)
            except Exception:
                continue

        tomorrow_events.sort(key=lambda e: str(e.get("start_time", "")))

        if not tomorrow_events:
            return {
                "has_events": False,
                "message": "No events tomorrow. Sleep in if you'd like!",
                "suggested_alarm": None,
                "suggested_bedtime": None,
            }

        first_event = tomorrow_events[0]
        try:
            first_start = datetime.fromisoformat(str(first_event.get("start_time", "")))
            first_hour = first_start.hour
            first_minute = first_start.minute
        except Exception:
            return {"has_events": True, "events": tomorrow_events, "suggested_alarm": None}

        prep = int(profile.get("calendar", {}).get("prep_minutes", self._prep_minutes))
        alarm_minutes = first_hour * 60 + first_minute - prep
        if alarm_minutes < 0:
            alarm_minutes += 24 * 60
        alarm_time = f"{alarm_minutes // 60:02d}:{alarm_minutes % 60:02d}"

        target_sleep = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)
        target_sleep = max(self._min_sleep, min(self._max_sleep, target_sleep))
        bedtime_minutes = alarm_minutes - int(target_sleep * 60)
        if bedtime_minutes < 0:
            bedtime_minutes += 24 * 60
        bedtime = f"{bedtime_minutes // 60:02d}:{bedtime_minutes % 60:02d}"

        return {
            "has_events": True,
            "events_count": len(tomorrow_events),
            "events": tomorrow_events,
            "first_event": {
                "title": first_event.get("title", ""),
                "start_time": first_event.get("start_time", ""),
                "location": first_event.get("location", ""),
            },
            "suggested_alarm": alarm_time,
            "suggested_bedtime": bedtime,
            "prep_minutes": prep,
            "target_sleep_hours": target_sleep,
            "message": (
                f"Tomorrow: '{first_event.get('title', '')}' at "
                f"{first_hour:02d}:{first_minute:02d}. "
                f"Suggested bedtime: {bedtime}, alarm: {alarm_time} "
                f"(for {target_sleep:.1f}h sleep)."
            ),
        }

    def get_today_remaining(self, profile: dict, now: datetime | None = None) -> list[dict[str, Any]]:
        """Get remaining events for today."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        events = profile.get("calendar", {}).get("events_cache", [])
        today = now.date()
        now_iso = now.isoformat()

        remaining: list[dict[str, Any]] = []
        for event in events:
            try:
                start = datetime.fromisoformat(str(event.get("start_time", "")))
                if start.date() == today and str(event.get("start_time", "")) >= now_iso:
                    remaining.append(event)
            except Exception:
                continue

        remaining.sort(key=lambda e: str(e.get("start_time", "")))
        return remaining

    # ------------------------------------------------------------------
    # Smart schedule actions
    # ------------------------------------------------------------------

    def evaluate_evening(self, profile: dict, now: datetime | None = None) -> dict[str, Any] | None:
        """Evening evaluation: check tomorrow and suggest bedtime/alarm."""
        now = now or _utcnow()
        if now.hour != 22:
            return None

        self.ensure_shape(profile)
        if not profile.get("calendar", {}).get("enabled", True):
            return None

        schedule = self.get_tomorrow_schedule(profile, now)
        if not schedule.get("has_events", False):
            return None

        actions: list[dict[str, Any]] = []
        alarm = schedule.get("suggested_alarm")
        bedtime = schedule.get("suggested_bedtime")

        if alarm and profile.get("calendar", {}).get("auto_alarm_enabled", True):
            actions.append({
                "type": "set_alarm",
                "time": alarm,
                "reason": f"Based on tomorrow's first event: {schedule.get('first_event', {}).get('title', '')}",
            })

        actions.append({
            "type": "notification",
            "category": "calendar_evening",
            "message": schedule.get("message", ""),
            "priority": "medium",
        })

        return {
            "type": "calendar_evening_brief",
            "schedule": schedule,
            "actions": actions,
        }

    def get_morning_brief(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Generate morning briefing with today's schedule."""
        now = now or _utcnow()
        self.ensure_shape(profile)

        if not profile.get("calendar", {}).get("morning_brief_enabled", True):
            return {"enabled": False}

        remaining = self.get_today_remaining(profile, now)

        if not remaining:
            return {
                "enabled": True,
                "has_events": False,
                "message": "No events today. Enjoy your free day!",
            }

        first = remaining[0]
        summary_parts = [f"You have {len(remaining)} event(s) today."]
        try:
            start = datetime.fromisoformat(str(first.get("start_time", "")))
            summary_parts.append(f"First: '{first.get('title', '')}' at {start.strftime('%H:%M')}.")
        except Exception:
            pass

        return {
            "enabled": True,
            "has_events": True,
            "events_count": len(remaining),
            "events": remaining[:5],
            "message": " ".join(summary_parts),
        }

    def is_free_day_tomorrow(self, profile: dict, now: datetime | None = None) -> bool:
        """Check if tomorrow has no events (can sleep in)."""
        schedule = self.get_tomorrow_schedule(profile, now)
        return not schedule.get("has_events", False)

    def has_early_event_tomorrow(self, profile: dict, before_hour: int = 8, now: datetime | None = None) -> bool:
        """Check if tomorrow has an event before a given hour."""
        schedule = self.get_tomorrow_schedule(profile, now)
        if not schedule.get("has_events", False):
            return False
        first = schedule.get("first_event", {})
        try:
            start = datetime.fromisoformat(str(first.get("start_time", "")))
            return start.hour < before_hour
        except Exception:
            return False
