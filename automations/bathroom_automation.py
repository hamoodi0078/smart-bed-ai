"""Night bathroom trip automation for Smart Bed AI.

Detects short bed absences during night hours via pressure sensor,
activates ultra-dim pathway LEDs, and auto-restores sleep mode on return.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("automations.bathroom_automation")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BathroomAutomation:
    """Manages automatic pathway lighting for night bathroom trips."""

    def __init__(
        self,
        *,
        night_start_hour: int = 22,
        night_end_hour: int = 6,
        max_trip_minutes: float = 10.0,
        pathway_brightness: float = 0.02,
        pathway_color: str = "#FF8C00",
        fade_out_seconds: float = 30.0,
        auto_off_minutes: float = 3.0,
    ):
        self._night_start = max(0, min(23, int(night_start_hour)))
        self._night_end = max(0, min(23, int(night_end_hour)))
        self._max_trip = max(1.0, float(max_trip_minutes))
        self._brightness = max(0.01, min(0.10, float(pathway_brightness)))
        self._color = str(pathway_color or "#FF8C00").strip()
        self._fade_out = max(5.0, float(fade_out_seconds))
        self._auto_off = max(1.0, float(auto_off_minutes))

        self._trip_active = False
        self._trip_started_at: datetime | None = None
        self._lights_activated = False
        self._trip_history: list[dict[str, Any]] = []

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("bathroom_trips", {})
        bt = profile["bathroom_trips"]
        bt.setdefault("total_trips", 0)
        bt.setdefault("avg_duration_seconds", 0)
        bt.setdefault("history", [])

    # ------------------------------------------------------------------
    # Trip detection
    # ------------------------------------------------------------------

    def on_bed_exit(self, now: datetime | None = None) -> dict[str, Any]:
        """Called when pressure sensor detects bed exit during night."""
        now = now or _utcnow()

        if not self._is_night(now):
            return {"activated": False, "reason": "Not night hours."}

        if self._trip_active:
            return {"activated": False, "reason": "Trip already in progress."}

        self._trip_active = True
        self._trip_started_at = now
        self._lights_activated = True

        logger.info("Bathroom trip detected at %s", now.isoformat())
        return {
            "activated": True,
            "pathway_lights": {
                "brightness": self._brightness,
                "color": self._color,
                "animation": "solid",
                "zone": "bed_edge",
            },
            "auto_off_minutes": self._auto_off,
            "message": "Pathway lights activated.",
        }

    def on_bed_return(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Called when pressure sensor detects return to bed."""
        now = now or _utcnow()
        self.ensure_shape(profile)

        if not self._trip_active:
            return {"deactivated": False, "reason": "No active trip."}

        duration_seconds = 0.0
        if self._trip_started_at:
            duration_seconds = (now - self._trip_started_at).total_seconds()

        self._trip_active = False
        self._lights_activated = False

        record = {
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M"),
            "duration_seconds": round(duration_seconds, 1),
            "timestamp": now.isoformat(),
        }
        profile["bathroom_trips"]["history"].append(record)
        profile["bathroom_trips"]["history"] = profile["bathroom_trips"]["history"][-90:]
        profile["bathroom_trips"]["total_trips"] = len(profile["bathroom_trips"]["history"])
        self._update_avg_duration(profile)

        logger.info("Bathroom trip ended: %.0f seconds", duration_seconds)
        return {
            "deactivated": True,
            "duration_seconds": round(duration_seconds, 1),
            "fade_out": {
                "brightness": 0.0,
                "duration_seconds": self._fade_out,
                "animation": "fade_to_black",
            },
            "resume_sleep_mode": True,
        }

    def check_timeout(self, now: datetime | None = None) -> dict[str, Any]:
        """Check if trip exceeded max duration (not a bathroom trip)."""
        now = now or _utcnow()

        if not self._trip_active or not self._trip_started_at:
            return {"timed_out": False}

        elapsed_minutes = (now - self._trip_started_at).total_seconds() / 60.0

        if elapsed_minutes >= self._max_trip:
            self._trip_active = False
            self._lights_activated = False
            logger.info("Bathroom trip timed out after %.1f minutes", elapsed_minutes)
            return {
                "timed_out": True,
                "elapsed_minutes": round(elapsed_minutes, 1),
                "action": "turn_off_lights",
                "classify_as": "mid_sleep_wake",
            }

        if elapsed_minutes >= self._auto_off and self._lights_activated:
            self._lights_activated = False
            return {
                "timed_out": False,
                "auto_off": True,
                "elapsed_minutes": round(elapsed_minutes, 1),
                "action": "dim_lights",
            }

        return {"timed_out": False, "elapsed_minutes": round(elapsed_minutes, 1)}

    def is_trip_active(self) -> bool:
        return self._trip_active

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, profile: dict, days: int = 30) -> dict[str, Any]:
        """Return bathroom trip statistics."""
        self.ensure_shape(profile)
        history = profile["bathroom_trips"].get("history", [])
        cutoff = (_utcnow() - timedelta(days=max(1, days))).date().isoformat()
        recent = [t for t in history if str(t.get("date", "")) >= cutoff]

        if not recent:
            return {"total_trips": 0, "period_days": days}

        durations = [float(t.get("duration_seconds", 0)) for t in recent]
        nights = len(set(str(t.get("date", "")) for t in recent))

        return {
            "total_trips": len(recent),
            "period_days": days,
            "avg_per_night": round(len(recent) / max(1, nights), 2),
            "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0,
            "nights_with_trips": nights,
            "impact_on_sleep": "minimal" if len(recent) / max(1, nights) <= 1 else "noticeable",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_night(self, now: datetime) -> bool:
        hour = now.hour
        if self._night_start > self._night_end:
            return hour >= self._night_start or hour <= self._night_end
        return self._night_start <= hour <= self._night_end

    def _update_avg_duration(self, profile: dict) -> None:
        history = profile["bathroom_trips"].get("history", [])
        durations = [
            float(t.get("duration_seconds", 0)) for t in history[-30:] if t.get("duration_seconds")
        ]
        if durations:
            profile["bathroom_trips"]["avg_duration_seconds"] = round(
                sum(durations) / len(durations), 1
            )
