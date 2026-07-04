"""Automatic guest detection for Smart Bed AI.

Detects unusual bed occupancy patterns that suggest a guest is using the bed,
auto-activates guest mode with privacy protections, and sends owner notifications.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("guest_mode.auto_guest_detection")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutoGuestDetection:
    """Detects guest presence and manages auto guest mode activation."""

    def __init__(
        self,
        *,
        unusual_hour_start: int = 10,
        unusual_hour_end: int = 18,
        pressure_deviation_pct: float = 30.0,
        confirmation_minutes: float = 15.0,
    ):
        self._unusual_start = int(unusual_hour_start)
        self._unusual_end = int(unusual_hour_end)
        self._deviation_pct = float(pressure_deviation_pct)
        self._confirmation_minutes = float(confirmation_minutes)

        self._detection_start: datetime | None = None
        self._guest_confirmed = False
        self._owner_away = False
        self._last_detection_date = ""

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("guest_detection", {})
        gd = profile["guest_detection"]
        gd.setdefault("auto_detect_enabled", True)
        gd.setdefault("detections_log", [])
        gd.setdefault("total_guest_sessions", 0)

    # ------------------------------------------------------------------
    # Signal inputs
    # ------------------------------------------------------------------

    def set_owner_away(self, away: bool) -> None:
        """Called when location/app indicates owner is away from home."""
        self._owner_away = bool(away)

    def on_bed_entry(
        self,
        profile: dict,
        pressure_value: float,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate if bed entry looks like a guest."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        gd = profile.get("guest_detection", {})

        if not gd.get("auto_detect_enabled", True):
            return {"detected": False, "reason": "Auto guest detection disabled."}

        today = now.date().isoformat()
        if self._last_detection_date == today and self._guest_confirmed:
            return {"detected": False, "reason": "Guest already detected today."}

        indicators: list[str] = []
        score = 0

        hour = now.hour
        if self._unusual_start <= hour <= self._unusual_end:
            indicators.append("unusual_hour")
            score += 30

        if self._owner_away:
            indicators.append("owner_away")
            score += 40

        baseline = float(profile.get("sleep", {}).get("avg_pressure_baseline", 0) or 0)
        if baseline > 0:
            deviation = abs(pressure_value - baseline) / baseline * 100.0
            if deviation >= self._deviation_pct:
                indicators.append("pressure_deviation")
                score += 30

        if score >= 50:
            self._detection_start = now
            logger.info("Guest detection triggered: score=%d indicators=%s", score, indicators)
            return {
                "detected": True,
                "confidence": min(100, score),
                "indicators": indicators,
                "awaiting_confirmation": True,
                "confirm_after_minutes": self._confirmation_minutes,
            }

        return {"detected": False, "score": score}

    def confirm_guest(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Confirm guest presence after observation period."""
        now = now or _utcnow()
        self.ensure_shape(profile)

        if self._detection_start is None:
            return {"confirmed": False, "reason": "No pending detection."}

        elapsed = (now - self._detection_start).total_seconds() / 60.0
        if elapsed < self._confirmation_minutes:
            return {
                "confirmed": False,
                "reason": f"Only {elapsed:.0f} min elapsed, need {self._confirmation_minutes:.0f} min.",
            }

        self._guest_confirmed = True
        self._last_detection_date = now.date().isoformat()

        gd = profile["guest_detection"]
        gd["total_guest_sessions"] = int(gd.get("total_guest_sessions", 0)) + 1
        gd["detections_log"].append(
            {
                "date": now.date().isoformat(),
                "detected_at": self._detection_start.isoformat(),
                "confirmed_at": now.isoformat(),
            }
        )
        gd["detections_log"] = gd["detections_log"][-50:]

        logger.info("Guest confirmed after %.0f minutes", elapsed)
        return {
            "confirmed": True,
            "guest_mode_actions": [
                {"type": "activate_guest_mode"},
                {"type": "disable_personal_automations"},
                {"type": "pause_voice_memory"},
                {"type": "pause_sleep_tracking"},
                {
                    "type": "notification",
                    "to": "owner",
                    "message": "Guest detected on your bed. Guest mode activated.",
                },
                {"type": "voice", "message": "Welcome, make yourself comfortable.", "volume": 0.4},
            ],
        }

    def reset(self) -> None:
        """Reset detection state (e.g. when guest mode deactivated)."""
        self._detection_start = None
        self._guest_confirmed = False

    def is_guest_confirmed(self) -> bool:
        return self._guest_confirmed

    def get_status(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        gd = profile.get("guest_detection", {})
        return {
            "enabled": gd.get("auto_detect_enabled", True),
            "guest_confirmed": self._guest_confirmed,
            "owner_away": self._owner_away,
            "pending_detection": self._detection_start is not None and not self._guest_confirmed,
            "total_sessions": int(gd.get("total_guest_sessions", 0)),
        }
