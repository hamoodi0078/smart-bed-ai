"""Smart nap detection and optimization for Smart Bed AI.

Detects daytime naps via pressure sensor, tracks nap duration, suggests optimal
nap timing, and triggers gentle wake to prevent oversleeping.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("sleep_tracking.nap_optimizer")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NapOptimizer:
    """Detects and optimizes daytime naps using pressure sensor data."""

    def __init__(
        self,
        *,
        nap_detect_threshold_minutes: int = 10,
        max_power_nap_minutes: int = 25,
        max_recovery_nap_minutes: int = 90,
        nap_window_start_hour: int = 11,
        nap_window_end_hour: int = 17,
        evening_cutoff_hour: int = 18,
    ):
        self._detect_threshold = max(5, int(nap_detect_threshold_minutes))
        self._max_power_nap = max(10, int(max_power_nap_minutes))
        self._max_recovery_nap = max(30, int(max_recovery_nap_minutes))
        self._window_start = max(0, min(23, int(nap_window_start_hour)))
        self._window_end = max(0, min(23, int(nap_window_end_hour)))
        self._evening_cutoff = max(0, min(23, int(evening_cutoff_hour)))

        self._active_nap: dict[str, Any] | None = None
        self._nap_history: list[dict[str, Any]] = []

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("naps", {})
        naps = profile["naps"]
        naps.setdefault("history", [])
        naps.setdefault("total_naps", 0)
        naps.setdefault("preferred_nap_time", "")
        naps.setdefault("avg_nap_duration_minutes", 0)

    # ------------------------------------------------------------------
    # Nap detection
    # ------------------------------------------------------------------

    def detect_nap_start(self, now: datetime | None = None) -> dict[str, Any]:
        """Call when pressure sensor detects bed entry during daytime."""
        now = now or _utcnow()
        hour = now.hour

        if not (self._window_start <= hour <= self._evening_cutoff):
            return {"nap_detected": False, "reason": "Outside nap detection window."}

        if self._active_nap is not None:
            return {"nap_detected": False, "reason": "Nap already in progress."}

        self._active_nap = {
            "start_time": now.isoformat(),
            "detected_at": now.isoformat(),
            "max_duration_minutes": self._max_power_nap,
        }

        logger.info("Potential nap detected at %s", now.isoformat())
        return {
            "nap_detected": True,
            "start_time": now.isoformat(),
            "suggested_duration": self._max_power_nap,
            "wake_alert_at": (now + timedelta(minutes=self._max_power_nap)).isoformat(),
        }

    def confirm_nap(self, now: datetime | None = None) -> dict[str, Any]:
        """Confirm nap after threshold duration of continuous bed pressure."""
        now = now or _utcnow()
        if self._active_nap is None:
            return {"confirmed": False, "reason": "No active nap to confirm."}

        try:
            start = datetime.fromisoformat(self._active_nap["start_time"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except Exception:
            return {"confirmed": False, "reason": "Invalid nap start time."}

        elapsed = (now - start).total_seconds() / 60.0
        if elapsed < self._detect_threshold:
            return {
                "confirmed": False,
                "reason": f"Only {elapsed:.0f} min elapsed, need {self._detect_threshold} min to confirm.",
                "minutes_elapsed": round(elapsed, 1),
            }

        self._active_nap["confirmed"] = True
        logger.info("Nap confirmed after %d minutes", int(elapsed))
        return {
            "confirmed": True,
            "minutes_elapsed": round(elapsed, 1),
            "message": f"Nap detected! I'll wake you gently in {self._max_power_nap - int(elapsed)} minutes.",
        }

    def end_nap(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """End active nap and record it in history."""
        now = now or _utcnow()
        self.ensure_shape(profile)

        if self._active_nap is None:
            return {"ended": False, "reason": "No active nap."}

        try:
            start = datetime.fromisoformat(self._active_nap["start_time"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except Exception:
            self._active_nap = None
            return {"ended": False, "reason": "Invalid nap data."}

        duration_minutes = (now - start).total_seconds() / 60.0
        if duration_minutes < 5:
            self._active_nap = None
            return {"ended": False, "reason": "Too short to record as nap."}

        nap_record = {
            "start_time": start.isoformat(),
            "end_time": now.isoformat(),
            "duration_minutes": round(duration_minutes, 1),
            "date": start.date().isoformat(),
            "nap_type": self._classify_nap(duration_minutes),
        }

        profile["naps"]["history"].append(nap_record)
        profile["naps"]["history"] = profile["naps"]["history"][-90:]
        profile["naps"]["total_naps"] = len(profile["naps"]["history"])
        self._update_preferred_time(profile)
        self._active_nap = None

        impact = self._assess_bedtime_impact(duration_minutes, now)

        logger.info("Nap ended: %d min (%s)", int(duration_minutes), nap_record["nap_type"])
        return {
            "ended": True,
            "nap": nap_record,
            "bedtime_impact": impact,
        }

    def should_wake(self, now: datetime | None = None) -> dict[str, Any]:
        """Check if active nap has exceeded recommended duration."""
        now = now or _utcnow()
        if self._active_nap is None:
            return {"should_wake": False}

        try:
            start = datetime.fromisoformat(self._active_nap["start_time"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except Exception:
            return {"should_wake": False}

        elapsed = (now - start).total_seconds() / 60.0
        max_dur = self._active_nap.get("max_duration_minutes", self._max_power_nap)

        if elapsed >= max_dur:
            return {
                "should_wake": True,
                "elapsed_minutes": round(elapsed, 1),
                "max_minutes": max_dur,
                "message": f"Nap has been {int(elapsed)} minutes. Time to wake up gently!",
                "wake_type": "gentle",
            }

        remaining = max_dur - elapsed
        return {
            "should_wake": False,
            "elapsed_minutes": round(elapsed, 1),
            "remaining_minutes": round(remaining, 1),
        }

    def is_nap_active(self) -> bool:
        return self._active_nap is not None

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------

    def suggest_nap(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Proactively suggest a nap based on sleep debt and time of day."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        hour = now.hour

        if not (self._window_start <= hour <= self._window_end):
            return {"suggest": False, "reason": "Outside optimal nap window."}

        if self._active_nap is not None:
            return {"suggest": False, "reason": "Nap already in progress."}

        if self._napped_today(profile, now):
            return {"suggest": False, "reason": "Already napped today."}

        debt = float(profile.get("sleep_debt", {}).get("cumulative_debt_hours", 0) or 0)
        sleep = profile.get("sleep", {})
        bed_hist = sleep.get("bedtime_history", [])
        wake_hist = sleep.get("wake_history", [])

        last_night_short = False
        if bed_hist and wake_hist:
            try:
                bed = datetime.fromisoformat(str(bed_hist[-1]))
                wake = datetime.fromisoformat(str(wake_hist[-1]))
                if wake > bed:
                    hours = (wake - bed).total_seconds() / 3600.0
                    last_night_short = hours < 6.0
            except Exception:
                pass

        reasons: list[str] = []
        if debt > 2.0:
            reasons.append(f"sleep debt of {debt:.1f} hours")
        if last_night_short:
            reasons.append("short sleep last night")
        if 13 <= hour <= 15:
            reasons.append("post-lunch dip window")

        if not reasons:
            return {"suggest": False, "reason": "No nap indicators detected."}

        preferred = profile["naps"].get("preferred_nap_time", "")
        nap_time = preferred if preferred else f"{max(13, min(hour, 15))}:00"
        duration = 20 if debt <= 3.0 else 30

        return {
            "suggest": True,
            "reasons": reasons,
            "suggested_time": nap_time,
            "suggested_duration_minutes": duration,
            "nap_type": "power" if duration <= 25 else "recovery",
            "message": f"A {duration}-min nap would help ({', '.join(reasons)}).",
        }

    def get_nap_stats(self, profile: dict, days: int = 30) -> dict[str, Any]:
        """Return nap statistics for the given period."""
        self.ensure_shape(profile)
        history = profile["naps"].get("history", [])
        cutoff = (_utcnow() - timedelta(days=max(1, days))).date().isoformat()
        recent = [n for n in history if str(n.get("date", "")) >= cutoff]

        if not recent:
            return {"total_naps": 0, "period_days": days, "message": "No naps recorded."}

        durations = [float(n.get("duration_minutes", 0)) for n in recent]
        types = [str(n.get("nap_type", "")) for n in recent]

        return {
            "total_naps": len(recent),
            "period_days": days,
            "avg_duration_minutes": round(sum(durations) / len(durations), 1) if durations else 0,
            "total_nap_hours": round(sum(durations) / 60.0, 2),
            "power_naps": types.count("power"),
            "recovery_naps": types.count("recovery"),
            "long_naps": types.count("long"),
            "preferred_time": profile["naps"].get("preferred_nap_time", ""),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_nap(duration_minutes: float) -> str:
        if duration_minutes <= 25:
            return "power"
        if duration_minutes <= 45:
            return "recovery"
        return "long"

    def _assess_bedtime_impact(self, nap_minutes: float, nap_end: datetime) -> dict[str, Any]:
        """Assess how the nap might affect tonight's bedtime."""
        if nap_minutes <= 20 and nap_end.hour < 16:
            return {
                "impact": "none",
                "message": "Short nap, no impact on tonight's bedtime.",
                "bedtime_adjustment_minutes": 0,
            }
        if nap_minutes <= 30 and nap_end.hour < 17:
            return {
                "impact": "minimal",
                "message": "May delay bedtime by 15-30 minutes.",
                "bedtime_adjustment_minutes": 20,
            }
        if nap_minutes > 45 or nap_end.hour >= 17:
            delay = min(90, int(nap_minutes * 0.8))
            return {
                "impact": "significant",
                "message": f"Long or late nap may delay bedtime by ~{delay} minutes.",
                "bedtime_adjustment_minutes": delay,
            }
        return {
            "impact": "mild",
            "message": "Consider going to bed slightly later tonight.",
            "bedtime_adjustment_minutes": 30,
        }

    def _napped_today(self, profile: dict, now: datetime) -> bool:
        today = now.date().isoformat()
        history = profile.get("naps", {}).get("history", [])
        return any(str(n.get("date", "")) == today for n in history)

    def _update_preferred_time(self, profile: dict) -> None:
        history = profile["naps"].get("history", [])
        recent = history[-14:]
        if not recent:
            return
        start_hours = []
        for n in recent:
            try:
                dt = datetime.fromisoformat(str(n.get("start_time", "")))
                start_hours.append(dt.hour * 60 + dt.minute)
            except Exception:
                continue
        if start_hours:
            avg = int(sum(start_hours) / len(start_hours))
            profile["naps"]["preferred_nap_time"] = f"{avg // 60:02d}:{avg % 60:02d}"
            profile["naps"]["avg_nap_duration_minutes"] = round(
                sum(float(n.get("duration_minutes", 0)) for n in recent) / len(recent), 1
            )
