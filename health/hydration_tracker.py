"""Hydration tracking and smart reminders for Smart Bed AI.

Time-based hydration reminders with bedtime cutoff, manual intake logging,
daily goal tracking, and weather-adaptive frequency.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("health.hydration_tracker")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HydrationTracker:
    """Manages hydration reminders and daily water intake tracking."""

    def __init__(
        self,
        *,
        daily_goal_ml: int = 2000,
        reminder_interval_hours: float = 2.0,
        bedtime_cutoff_hours: float = 2.0,
        morning_reminder_hour: int = 7,
        serving_size_ml: int = 250,
    ):
        self._daily_goal = max(500, int(daily_goal_ml))
        self._interval = max(0.5, float(reminder_interval_hours))
        self._cutoff_hours = max(0.5, float(bedtime_cutoff_hours))
        self._morning_hour = max(5, min(12, int(morning_reminder_hour)))
        self._serving = max(100, int(serving_size_ml))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("hydration", {})
        h = profile["hydration"]
        h.setdefault("daily_goal_ml", self._daily_goal)
        h.setdefault("today_intake_ml", 0)
        h.setdefault("today_date", "")
        h.setdefault("last_reminder_at", "")
        h.setdefault("history", [])
        h.setdefault("total_days_tracked", 0)

    # ------------------------------------------------------------------
    # Intake logging
    # ------------------------------------------------------------------

    def log_intake(self, profile: dict, ml: int = 0, now: datetime | None = None) -> dict[str, Any]:
        """Log water intake. If ml=0, use default serving size."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        h = profile["hydration"]
        today = now.date().isoformat()

        if h.get("today_date", "") != today:
            self._archive_day(profile, now)
            h["today_intake_ml"] = 0
            h["today_date"] = today

        amount = max(0, int(ml)) if ml > 0 else self._serving
        h["today_intake_ml"] = int(h.get("today_intake_ml", 0)) + amount

        goal = int(h.get("daily_goal_ml", self._daily_goal))
        current = int(h.get("today_intake_ml", 0))
        remaining = max(0, goal - current)
        pct = min(100, round(current / goal * 100, 1)) if goal > 0 else 0

        return {
            "logged_ml": amount,
            "total_today_ml": current,
            "goal_ml": goal,
            "remaining_ml": remaining,
            "progress_pct": pct,
            "goal_reached": current >= goal,
            "message": f"Logged {amount}ml. {current}/{goal}ml today ({pct}%)."
                       + (" Goal reached!" if current >= goal else f" {remaining}ml to go."),
        }

    # ------------------------------------------------------------------
    # Reminder evaluation
    # ------------------------------------------------------------------

    def should_remind(self, profile: dict, now: datetime | None = None, bedtime_hour: int = 23) -> dict[str, Any]:
        """Check if a hydration reminder should be sent now."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        h = profile["hydration"]
        today = now.date().isoformat()
        hour = now.hour

        if h.get("today_date", "") != today:
            h["today_intake_ml"] = 0
            h["today_date"] = today

        goal = int(h.get("daily_goal_ml", self._daily_goal))
        current = int(h.get("today_intake_ml", 0))
        if current >= goal:
            return {"remind": False, "reason": "Daily goal already met."}

        cutoff_hour = max(0, bedtime_hour - int(self._cutoff_hours))
        if hour >= cutoff_hour:
            return {"remind": False, "reason": "Too close to bedtime."}

        if hour < self._morning_hour:
            return {"remind": False, "reason": "Too early for reminders."}

        last_str = str(h.get("last_reminder_at", "")).strip()
        if last_str:
            try:
                last = datetime.fromisoformat(last_str)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (now - last).total_seconds() / 3600.0
                if elapsed < self._interval:
                    return {"remind": False, "reason": f"Last reminder {elapsed:.1f}h ago (interval={self._interval}h)."}
            except Exception:
                pass

        h["last_reminder_at"] = now.isoformat()
        remaining = max(0, goal - current)
        hours_left = max(1, cutoff_hour - hour)
        per_hour = remaining / hours_left

        if hour == self._morning_hour:
            message = "Good morning! Start your day with a glass of water."
        elif per_hour > 400:
            message = f"You're behind on hydration. {remaining}ml remaining — drink up!"
        else:
            message = f"Time for water! {remaining}ml remaining today."

        return {
            "remind": True,
            "message": message,
            "remaining_ml": remaining,
            "hours_until_cutoff": hours_left,
            "notification": {
                "type": "notification",
                "category": "hydration_reminder",
                "message": message,
                "priority": "low",
            },
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_today(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        now = now or _utcnow()
        self.ensure_shape(profile)
        h = profile["hydration"]
        today = now.date().isoformat()

        current = int(h.get("today_intake_ml", 0)) if h.get("today_date", "") == today else 0
        goal = int(h.get("daily_goal_ml", self._daily_goal))

        return {
            "date": today,
            "intake_ml": current,
            "goal_ml": goal,
            "remaining_ml": max(0, goal - current),
            "progress_pct": min(100, round(current / goal * 100, 1)) if goal > 0 else 0,
            "goal_reached": current >= goal,
        }

    def get_stats(self, profile: dict, days: int = 30) -> dict[str, Any]:
        self.ensure_shape(profile)
        history = profile["hydration"].get("history", [])
        cutoff = (_utcnow() - timedelta(days=max(1, days))).date().isoformat()
        recent = [d for d in history if str(d.get("date", "")) >= cutoff]

        if not recent:
            return {"days_tracked": 0, "period_days": days}

        intakes = [int(d.get("intake_ml", 0)) for d in recent]
        goals_met = sum(1 for d in recent if d.get("goal_reached", False))

        return {
            "days_tracked": len(recent),
            "period_days": days,
            "avg_intake_ml": round(sum(intakes) / len(intakes)) if intakes else 0,
            "total_intake_ml": sum(intakes),
            "goals_met": goals_met,
            "goal_success_rate": round(goals_met / len(recent) * 100, 1) if recent else 0,
            "best_day_ml": max(intakes) if intakes else 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _archive_day(self, profile: dict, now: datetime) -> None:
        h = profile["hydration"]
        prev_date = h.get("today_date", "")
        if not prev_date:
            return
        intake = int(h.get("today_intake_ml", 0))
        goal = int(h.get("daily_goal_ml", self._daily_goal))
        history = h.get("history", [])
        history.append({
            "date": prev_date,
            "intake_ml": intake,
            "goal_ml": goal,
            "goal_reached": intake >= goal,
        })
        h["history"] = history[-90:]
        h["total_days_tracked"] = len(history)
