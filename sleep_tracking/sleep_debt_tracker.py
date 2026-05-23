"""Sleep debt tracking and recovery management for Smart Bed AI.

Calculates rolling sleep debt, suggests recovery plans, tracks debt payoff
progress, and generates weekend compensation schedules.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_CRITICAL_DEBT_HOURS = 10.0   # ≥ 10h cumulative debt triggers a critical alert
_HIGH_DEBT_HOURS = 5.0        # boundary between moderate and high


class SleepDebtTracker:
    """Tracks cumulative sleep debt and generates recovery recommendations."""

    def __init__(self, default_target_hours: float = 8.0):
        self._default_target = max(5.0, min(10.0, float(default_target_hours)))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("sleep", {})
        profile["sleep"].setdefault("bedtime_history", [])
        profile["sleep"].setdefault("wake_history", [])
        profile.setdefault("preferences", {})
        profile["preferences"].setdefault("sleep_target_hours", self._default_target)
        profile.setdefault("sleep_debt", {})
        debt = profile["sleep_debt"]
        debt.setdefault("last_calculated_date", "")
        debt.setdefault("cumulative_debt_hours", 0.0)
        debt.setdefault("debt_history", [])
        debt.setdefault("recovery_plan_active", False)
        debt.setdefault("recovery_target_date", "")

    def calculate_debt(self, profile: dict, days: int = 7) -> dict[str, Any]:
        """Calculate rolling sleep debt for the last N days."""
        self.ensure_shape(profile)
        target = float(profile.get("preferences", {}).get("sleep_target_hours", self._default_target) or self._default_target)
        sleep = profile.get("sleep", {})
        bed_hist = sleep.get("bedtime_history", [])
        wake_hist = sleep.get("wake_history", [])

        pairs = min(len(bed_hist), len(wake_hist), days)
        nightly: list[dict[str, Any]] = []
        total_actual = 0.0
        total_target = 0.0

        for i in range(1, pairs + 1):
            try:
                bed = datetime.fromisoformat(str(bed_hist[-i]))
                wake = datetime.fromisoformat(str(wake_hist[-i]))
                if wake <= bed:
                    continue
                hours = (wake - bed).total_seconds() / 3600.0
                if not (2.0 <= hours <= 16.0):
                    continue
                deficit = target - hours
                total_actual += hours
                total_target += target
                nightly.append({
                    "date": bed.date().isoformat(),
                    "hours_slept": round(hours, 2),
                    "target": target,
                    "deficit": round(deficit, 2),
                })
            except Exception:
                continue

        nights_count = len(nightly)
        cumulative_debt = round(total_target - total_actual, 2) if nights_count > 0 else 0.0
        avg_hours = round(total_actual / nights_count, 2) if nights_count > 0 else 0.0

        profile["sleep_debt"]["cumulative_debt_hours"] = cumulative_debt
        profile["sleep_debt"]["last_calculated_date"] = _utcnow().date().isoformat()
        self._append_debt_history(profile, cumulative_debt)

        return {
            "cumulative_debt_hours": cumulative_debt,
            "nights_analyzed": nights_count,
            "average_hours": avg_hours,
            "target_hours": target,
            "daily_deficit": round(cumulative_debt / nights_count, 2) if nights_count > 0 else 0.0,
            "nightly_breakdown": nightly,
            "status": self._debt_status(cumulative_debt),
            "message": self._debt_message(cumulative_debt, avg_hours, target),
        }

    def get_recovery_plan(self, profile: dict) -> dict[str, Any]:
        """Generate a recovery plan to pay off sleep debt."""
        self.ensure_shape(profile)
        debt = float(profile.get("sleep_debt", {}).get("cumulative_debt_hours", 0.0) or 0.0)

        if debt <= 0:
            return {
                "needed": False,
                "message": "No sleep debt! MashaAllah, keep this rhythm.",
                "debt_hours": 0.0,
            }

        strategies: list[dict[str, Any]] = []

        if debt <= 2.0:
            strategies.append({
                "name": "early_bedtime",
                "description": f"Go to bed 30 minutes early tonight to recover {min(debt, 0.5):.1f} hours.",
                "extra_sleep_per_night": 0.5,
                "nights_needed": max(1, int(debt / 0.5 + 0.5)),
            })
        elif debt <= 5.0:
            strategies.append({
                "name": "gradual_recovery",
                "description": "Go to bed 30 minutes early each night this week.",
                "extra_sleep_per_night": 0.5,
                "nights_needed": max(1, int(debt / 0.5 + 0.5)),
            })
            strategies.append({
                "name": "weekend_catchup",
                "description": "Sleep 1-1.5 extra hours on Saturday and Sunday.",
                "extra_sleep_per_night": 1.25,
                "nights_needed": max(1, int(debt / 1.25 + 0.5)),
            })
        else:
            strategies.append({
                "name": "intensive_recovery",
                "description": "Priority: Sleep 1 hour extra each night for a full week.",
                "extra_sleep_per_night": 1.0,
                "nights_needed": max(1, int(debt / 1.0 + 0.5)),
            })
            strategies.append({
                "name": "nap_supplement",
                "description": "Add a 20-minute power nap at 2 PM on workdays.",
                "extra_sleep_per_day": 0.33,
                "days_needed": max(1, int(debt / 0.33 + 0.5)),
            })

        profile["sleep_debt"]["recovery_plan_active"] = True
        target_days = strategies[0].get("nights_needed", 7)
        profile["sleep_debt"]["recovery_target_date"] = (
            _utcnow() + timedelta(days=target_days)
        ).date().isoformat()

        return {
            "needed": True,
            "debt_hours": round(debt, 2),
            "strategies": strategies,
            "recommended": strategies[0]["name"],
            "target_recovery_date": profile["sleep_debt"]["recovery_target_date"],
            "message": f"You owe {debt:.1f} hours of sleep. Let's pay it back gradually.",
        }

    def check_recovery_progress(self, profile: dict) -> dict[str, Any]:
        """Check progress on active recovery plan."""
        self.ensure_shape(profile)
        debt_data = profile.get("sleep_debt", {})
        if not debt_data.get("recovery_plan_active", False):
            return {"active": False, "message": "No active recovery plan."}

        history = debt_data.get("debt_history", [])
        if len(history) < 2:
            return {"active": True, "message": "Recovery just started. Keep going!"}

        initial = float(history[0].get("debt", 0))
        current = float(history[-1].get("debt", 0))
        reduction = initial - current

        target_date = debt_data.get("recovery_target_date", "")
        on_track = current <= 0 or reduction > 0

        if current <= 0:
            debt_data["recovery_plan_active"] = False
            return {
                "active": False,
                "completed": True,
                "message": "Sleep debt fully recovered! MashaAllah!",
                "total_recovered_hours": round(reduction, 1),
            }

        return {
            "active": True,
            "completed": False,
            "initial_debt": round(initial, 1),
            "current_debt": round(current, 1),
            "recovered_hours": round(reduction, 1),
            "target_date": target_date,
            "on_track": on_track,
            "message": f"Recovered {reduction:.1f}h so far. {current:.1f}h remaining.",
        }

    def get_weekend_compensation(self, profile: dict) -> dict[str, Any]:
        """Suggest weekend sleep compensation based on weekday debt."""
        self.ensure_shape(profile)
        debt = float(profile.get("sleep_debt", {}).get("cumulative_debt_hours", 0.0) or 0.0)

        if debt <= 0:
            return {"needed": False, "message": "No debt to compensate this weekend."}

        per_night = min(2.0, debt / 2.0)
        target = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)

        return {
            "needed": True,
            "debt_hours": round(debt, 1),
            "saturday_target_hours": round(target + per_night, 1),
            "sunday_target_hours": round(target + per_night, 1),
            "extra_per_night": round(per_night, 1),
            "message": f"Sleep {per_night:.0f} extra hours each weekend night to recover {debt:.1f}h debt.",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def check_critical_debt_alert(self, profile: dict) -> dict[str, Any]:
        """Return a critical alert when cumulative sleep debt crosses the clinical threshold.

        A 7-day debt ≥ 10 hours (roughly < 6.6 h/night average with an 8-hour target)
        is considered critically impairing — comparable in effect to 24 h total sleep
        deprivation.  This warrants a push notification and immediate intervention.

        Returns
        -------
        dict with keys:
          alert (bool)        — True when debt is critical
          severity (str)      — 'critical' | 'high' | 'moderate' | 'mild' | 'none'
          debt_hours (float)
          message (str)       — user-facing alert text
          recommended_action (str)
        """
        self.ensure_shape(profile)
        debt = float(profile.get("sleep_debt", {}).get("cumulative_debt_hours", 0.0) or 0.0)

        if debt < 0:
            return {
                "alert": False,
                "severity": "none",
                "debt_hours": 0.0,
                "message": "Sleep bank is positive — great job!",
                "recommended_action": "Maintain current sleep schedule.",
            }

        if debt >= _CRITICAL_DEBT_HOURS:
            return {
                "alert": True,
                "severity": "critical",
                "debt_hours": round(debt, 1),
                "message": (
                    f"Critical sleep debt: {debt:.1f} hours. "
                    "Cognitive function is significantly impaired. Immediate recovery required."
                ),
                "recommended_action": (
                    "Start a structured recovery plan tonight: add 1.5 hours to your sleep window "
                    "and avoid all-nighters for the next 7 days."
                ),
            }

        if debt >= _HIGH_DEBT_HOURS:
            return {
                "alert": True,
                "severity": "high",
                "debt_hours": round(debt, 1),
                "message": f"High sleep debt: {debt:.1f} hours. Recovery plan recommended.",
                "recommended_action": "Sleep 1 extra hour per night for the next week.",
            }

        if debt >= 2.0:
            return {
                "alert": False,
                "severity": "moderate",
                "debt_hours": round(debt, 1),
                "message": f"Moderate sleep debt: {debt:.1f} hours.",
                "recommended_action": "Go to bed 30 minutes earlier tonight.",
            }

        return {
            "alert": False,
            "severity": "mild",
            "debt_hours": round(debt, 1),
            "message": f"Mild sleep debt: {debt:.1f} hours.",
            "recommended_action": "An early bedtime tonight will clear this.",
        }

    def _append_debt_history(self, profile: dict, debt: float) -> None:
        history = profile["sleep_debt"].get("debt_history", [])
        history.append({
            "date": _utcnow().date().isoformat(),
            "debt": round(debt, 2),
        })
        profile["sleep_debt"]["debt_history"] = history[-90:]

    @staticmethod
    def _debt_status(debt: float) -> str:
        if debt <= 0:
            return "debt_free"
        if debt <= 2.0:
            return "mild"
        if debt < _HIGH_DEBT_HOURS:
            return "moderate"
        if debt < _CRITICAL_DEBT_HOURS:
            return "high"
        return "critical"

    @staticmethod
    def _debt_message(debt: float, avg: float, target: float) -> str:
        if debt <= 0:
            return f"No sleep debt! Avg {avg:.1f}h/night (target {target:.1f}h). MashaAllah!"
        if debt <= 2.0:
            return f"Mild debt: {debt:.1f}h. Avg {avg:.1f}h/night. Go to bed 30min early tonight."
        if debt < _HIGH_DEBT_HOURS:
            return f"Moderate debt: {debt:.1f}h. Avg {avg:.1f}h/night. Consider a recovery plan."
        if debt < _CRITICAL_DEBT_HOURS:
            return f"High debt: {debt:.1f}h. Avg {avg:.1f}h/night. Start a recovery plan tonight."
        return (
            f"CRITICAL debt: {debt:.1f}h. Avg {avg:.1f}h/night. "
            "Cognitive function impaired — immediate recovery required."
        )
