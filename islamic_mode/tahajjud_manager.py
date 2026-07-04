"""Tahajjud (night prayer) automation for Smart Bed AI.

Calculates the last third of the night, manages gentle wake sequences
for voluntary night prayer, and adapts based on user sleep quality.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from islamic_mode.prayer_times import PrayerTimesService

logger = logging.getLogger("islamic_mode.tahajjud_manager")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TahajjudManager:
    """Manages Tahajjud prayer wake automation with sleep-aware scheduling."""

    def __init__(
        self,
        prayer_service: PrayerTimesService | None = None,
        *,
        wake_before_last_third_minutes: int = 10,
        min_sleep_hours_required: float = 5.0,
        max_consecutive_skips_before_disable: int = 3,
    ):
        self._prayer_service = prayer_service or PrayerTimesService()
        self._wake_before = max(0, int(wake_before_last_third_minutes))
        self._min_sleep = max(3.0, float(min_sleep_hours_required))
        self._max_skips = max(1, int(max_consecutive_skips_before_disable))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("islamic", {})
        islamic = profile["islamic"]
        islamic.setdefault("tahajjud_enabled", False)
        islamic.setdefault("tahajjud_wake_style", "gentle")
        islamic.setdefault("tahajjud_consecutive_skips", 0)
        islamic.setdefault("tahajjud_last_wake_date", "")
        islamic.setdefault("tahajjud_last_prayed_date", "")
        islamic.setdefault("tahajjud_total_prayed", 0)
        islamic.setdefault("tahajjud_history", [])

    # ------------------------------------------------------------------
    # Last-third-of-night calculation
    # ------------------------------------------------------------------

    def calculate_last_third(self, now: datetime | None = None) -> dict[str, Any]:
        """Calculate the start of the last third of the night."""
        now = now or datetime.now()
        try:
            prayers = self._prayer_service.get_today_prayers()
        except Exception:
            return {"available": False, "reason": "Cannot fetch prayer times."}

        maghrib_str = prayers.get("Maghrib", "")
        fajr_str = prayers.get("Fajr", "")
        if not maghrib_str or not fajr_str:
            return {"available": False, "reason": "Missing Maghrib or Fajr times."}

        try:
            mh, mm = [int(x) for x in maghrib_str.split(":")]
            fh, fm = [int(x) for x in fajr_str.split(":")]
        except Exception:
            return {"available": False, "reason": "Cannot parse prayer times."}

        maghrib_minutes = mh * 60 + mm
        fajr_minutes = fh * 60 + fm
        if fajr_minutes <= maghrib_minutes:
            fajr_minutes += 24 * 60

        night_duration = fajr_minutes - maghrib_minutes
        last_third_start_minutes = maghrib_minutes + int(night_duration * 2 / 3)
        last_third_start_minutes = last_third_start_minutes % (24 * 60)

        optimal_wake = (last_third_start_minutes - self._wake_before) % (24 * 60)

        return {
            "available": True,
            "maghrib": maghrib_str,
            "fajr": fajr_str,
            "night_duration_hours": round(night_duration / 60.0, 2),
            "last_third_start": f"{last_third_start_minutes // 60:02d}:{last_third_start_minutes % 60:02d}",
            "optimal_wake_time": f"{optimal_wake // 60:02d}:{optimal_wake % 60:02d}",
            "minutes_before_fajr": fajr_minutes - last_third_start_minutes,
        }

    # ------------------------------------------------------------------
    # Should-wake evaluation
    # ------------------------------------------------------------------

    def should_wake_for_tahajjud(
        self, profile: dict, now: datetime | None = None
    ) -> dict[str, Any]:
        """Determine if user should be woken for Tahajjud right now."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        islamic = profile.get("islamic", {})

        if not islamic.get("tahajjud_enabled", False):
            return {"should_wake": False, "reason": "Tahajjud automation disabled."}

        if islamic.get("tahajjud_consecutive_skips", 0) >= self._max_skips:
            return {
                "should_wake": False,
                "reason": f"Auto-disabled after {self._max_skips} consecutive skips. Re-enable manually.",
                "auto_disabled": True,
            }

        today = now.date().isoformat()
        if islamic.get("tahajjud_last_wake_date", "") == today:
            return {"should_wake": False, "reason": "Already triggered today."}

        sleep_hours = self._estimate_current_sleep(profile, now)
        if sleep_hours < self._min_sleep:
            return {
                "should_wake": False,
                "reason": f"Only {sleep_hours:.1f}h sleep so far (min {self._min_sleep}h required).",
                "sleep_hours": round(sleep_hours, 1),
            }

        third_info = self.calculate_last_third(now)
        if not third_info.get("available", False):
            return {"should_wake": False, "reason": third_info.get("reason", "Unknown")}

        wake_time_str = third_info.get("optimal_wake_time", "")
        if not wake_time_str:
            return {"should_wake": False, "reason": "Cannot determine wake time."}

        try:
            wh, wm = [int(x) for x in wake_time_str.split(":")]
            wake_minutes = wh * 60 + wm
            now_minutes = now.hour * 60 + now.minute
            diff = abs(now_minutes - wake_minutes)
            if diff > 12 * 60:
                diff = 24 * 60 - diff
        except Exception:
            return {"should_wake": False, "reason": "Cannot calculate time difference."}

        if diff <= 10:
            return {
                "should_wake": True,
                "wake_time": wake_time_str,
                "sleep_hours": round(sleep_hours, 1),
                "last_third_start": third_info.get("last_third_start", ""),
                "fajr": third_info.get("fajr", ""),
                "message": "Time for Tahajjud. May Allah accept your prayer.",
                "wake_actions": self._build_wake_actions(islamic),
            }

        return {
            "should_wake": False,
            "reason": f"Not yet time. Wake at {wake_time_str} ({diff} min away).",
            "wake_time": wake_time_str,
        }

    # ------------------------------------------------------------------
    # Response tracking
    # ------------------------------------------------------------------

    def record_tahajjud_prayed(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Record that user prayed Tahajjud."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        islamic = profile["islamic"]
        today = now.date().isoformat()

        islamic["tahajjud_last_prayed_date"] = today
        islamic["tahajjud_consecutive_skips"] = 0
        islamic["tahajjud_total_prayed"] = int(islamic.get("tahajjud_total_prayed", 0)) + 1

        history = islamic.get("tahajjud_history", [])
        history.append({"date": today, "prayed": True, "timestamp": now.isoformat()})
        islamic["tahajjud_history"] = history[-90:]

        total = int(islamic.get("tahajjud_total_prayed", 0))
        return {
            "recorded": True,
            "total_prayed": total,
            "streak": self._calculate_streak(islamic),
            "message": f"MashaAllah! Tahajjud recorded. Total: {total} nights.",
        }

    def record_tahajjud_skipped(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Record that user skipped Tahajjud after wake attempt."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        islamic = profile["islamic"]
        today = now.date().isoformat()

        skips = int(islamic.get("tahajjud_consecutive_skips", 0)) + 1
        islamic["tahajjud_consecutive_skips"] = skips

        history = islamic.get("tahajjud_history", [])
        history.append({"date": today, "prayed": False, "timestamp": now.isoformat()})
        islamic["tahajjud_history"] = history[-90:]

        auto_disabled = skips >= self._max_skips
        if auto_disabled:
            islamic["tahajjud_enabled"] = False
            logger.info("Tahajjud auto-disabled after %d consecutive skips", skips)

        return {
            "recorded": True,
            "consecutive_skips": skips,
            "auto_disabled": auto_disabled,
            "message": "No worries. Rest well, in sha Allah."
            if not auto_disabled
            else f"Tahajjud paused after {skips} skips. Re-enable when ready.",
        }

    def mark_wake_triggered(self, profile: dict, now: datetime | None = None) -> None:
        """Mark that wake was triggered today (prevents duplicate)."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        profile["islamic"]["tahajjud_last_wake_date"] = now.date().isoformat()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        islamic = profile.get("islamic", {})
        history = islamic.get("tahajjud_history", [])
        prayed = [h for h in history if h.get("prayed", False)]
        total = len(history)

        return {
            "enabled": islamic.get("tahajjud_enabled", False),
            "total_attempts": total,
            "total_prayed": len(prayed),
            "success_rate": round(len(prayed) / total * 100, 1) if total > 0 else 0,
            "current_streak": self._calculate_streak(islamic),
            "consecutive_skips": int(islamic.get("tahajjud_consecutive_skips", 0)),
            "last_prayed_date": islamic.get("tahajjud_last_prayed_date", ""),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _estimate_current_sleep(self, profile: dict, now: datetime) -> float:
        """Estimate hours slept tonight based on bedtime history."""
        bed_hist = profile.get("sleep", {}).get("bedtime_history", [])
        if not bed_hist:
            return 0.0
        try:
            last_bed = datetime.fromisoformat(str(bed_hist[-1]))
            if last_bed.tzinfo is None:
                last_bed = last_bed.replace(tzinfo=timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            hours = (now - last_bed).total_seconds() / 3600.0
            return max(0.0, hours) if hours < 14 else 0.0
        except Exception:
            return 0.0

    def _build_wake_actions(self, islamic: dict) -> list[dict[str, Any]]:
        style = str(islamic.get("tahajjud_wake_style", "gentle")).strip().lower()
        actions = [
            {
                "type": "led_scene",
                "brightness": 0.02 if style == "gentle" else 0.05,
                "color": "#FFF5E0",
                "animation": "slow_breathing",
            },
        ]
        if style != "silent":
            actions.append(
                {
                    "type": "voice",
                    "message": "Time for Tahajjud. May Allah accept your prayer.",
                    "volume": 0.2,
                }
            )
        return actions

    @staticmethod
    def _calculate_streak(islamic: dict) -> int:
        history = islamic.get("tahajjud_history", [])
        if not history:
            return 0
        streak = 0
        for entry in reversed(history):
            if entry.get("prayed", False):
                streak += 1
            else:
                break
        return streak
