"""Automation feedback learning engine for Smart Bed AI.

Tracks user responses (accept/decline/snooze) to automation suggestions,
learns optimal timing and context preferences, adapts automation frequency
and presentation based on historical effectiveness.
"""

from __future__ import annotations

from loguru import logger
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any



def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutomationLearningEngine:
    """Learns from user automation responses to personalize triggers and timing."""

    def __init__(
        self,
        *,
        disable_threshold_pct: float = 15.0,
        min_samples_for_learning: int = 10,
        timing_adjustment_minutes: int = 15,
        learning_window_days: int = 30,
    ):
        self._disable_threshold = max(5.0, float(disable_threshold_pct))
        self._min_samples = max(5, int(min_samples_for_learning))
        self._timing_adj = max(5, int(timing_adjustment_minutes))
        self._window_days = max(7, int(learning_window_days))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("automation_learning", {})
        al = profile["automation_learning"]
        al.setdefault("responses", [])
        al.setdefault("automation_preferences", {})
        al.setdefault("timing_adjustments", {})
        al.setdefault("monthly_report", {})

    # ------------------------------------------------------------------
    # Response recording
    # ------------------------------------------------------------------

    def record_response(
        self,
        profile: dict,
        automation_id: str,
        response: str,
        *,
        context: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Record user response to an automation trigger.

        response: 'accepted', 'declined', 'snoozed', 'never'
        """
        now = now or _utcnow()
        self.ensure_shape(profile)
        al = profile["automation_learning"]

        valid_responses = {"accepted", "declined", "snoozed", "never"}
        response = str(response).strip().lower()
        if response not in valid_responses:
            response = "declined"

        record = {
            "automation_id": str(automation_id).strip(),
            "response": response,
            "timestamp": now.isoformat(),
            "hour": now.hour,
            "weekday": now.weekday(),
            "context": dict(context) if isinstance(context, dict) else {},
        }

        al["responses"].append(record)
        cutoff = (now - timedelta(days=self._window_days * 3)).isoformat()
        al["responses"] = [r for r in al["responses"] if str(r.get("timestamp", "")) >= cutoff]
        al["responses"] = al["responses"][-2000:]

        if response == "never":
            prefs = al.setdefault("automation_preferences", {})
            prefs[automation_id] = {"disabled": True, "disabled_at": now.isoformat()}
            logger.info("Automation %s disabled by user ('never' response)", automation_id)

        self._update_timing_preference(al, automation_id, response, now)

        return {
            "recorded": True,
            "automation_id": automation_id,
            "response": response,
            "current_acceptance_rate": self._get_acceptance_rate(al, automation_id),
        }

    # ------------------------------------------------------------------
    # Learning queries
    # ------------------------------------------------------------------

    def should_trigger(self, profile: dict, automation_id: str, now: datetime | None = None) -> dict[str, Any]:
        """Determine if an automation should be triggered based on learned preferences."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        al = profile.get("automation_learning", {})

        prefs = al.get("automation_preferences", {})
        if prefs.get(automation_id, {}).get("disabled", False):
            return {"should_trigger": False, "reason": "Disabled by user."}

        rate = self._get_acceptance_rate(al, automation_id)
        if rate is not None and rate < self._disable_threshold:
            return {
                "should_trigger": False,
                "reason": f"Acceptance rate too low ({rate:.0f}%). Consider disabling.",
                "acceptance_rate": rate,
            }

        timing = al.get("timing_adjustments", {}).get(automation_id, {})
        preferred_hour = timing.get("preferred_hour")
        if preferred_hour is not None:
            hour_diff = abs(now.hour - int(preferred_hour))
            if hour_diff > 2 and hour_diff < 22:
                return {
                    "should_trigger": False,
                    "reason": f"User prefers this automation around {preferred_hour}:00.",
                    "preferred_hour": preferred_hour,
                    "delay_suggested": True,
                }

        return {
            "should_trigger": True,
            "acceptance_rate": rate,
            "preferred_hour": preferred_hour,
        }

    def get_optimal_time(self, profile: dict, automation_id: str) -> dict[str, Any]:
        """Get the optimal time to trigger an automation based on acceptance patterns."""
        self.ensure_shape(profile)
        al = profile.get("automation_learning", {})
        responses = al.get("responses", [])

        relevant = [r for r in responses if r.get("automation_id") == automation_id]
        if len(relevant) < self._min_samples:
            return {"available": False, "reason": "Not enough data."}

        accepted_hours: list[int] = [
            int(r.get("hour", 0)) for r in relevant if r.get("response") == "accepted"
        ]
        if not accepted_hours:
            return {"available": False, "reason": "No accepted responses recorded."}

        hour_counts: dict[int, int] = defaultdict(int)
        for h in accepted_hours:
            hour_counts[h] += 1

        best_hour = max(hour_counts, key=hour_counts.get)
        return {
            "available": True,
            "optimal_hour": best_hour,
            "acceptance_count_at_hour": hour_counts[best_hour],
            "total_accepted": len(accepted_hours),
        }

    def get_automation_report(self, profile: dict) -> list[dict[str, Any]]:
        """Get effectiveness report for all tracked automations."""
        self.ensure_shape(profile)
        al = profile.get("automation_learning", {})
        responses = al.get("responses", [])

        automation_ids = set(r.get("automation_id", "") for r in responses)
        report: list[dict[str, Any]] = []

        for aid in sorted(automation_ids):
            if not aid:
                continue
            relevant = [r for r in responses if r.get("automation_id") == aid]
            accepted = sum(1 for r in relevant if r.get("response") == "accepted")
            declined = sum(1 for r in relevant if r.get("response") == "declined")
            snoozed = sum(1 for r in relevant if r.get("response") == "snoozed")
            total = len(relevant)

            rate = round(accepted / total * 100, 1) if total > 0 else 0
            prefs = al.get("automation_preferences", {}).get(aid, {})
            timing = al.get("timing_adjustments", {}).get(aid, {})

            report.append({
                "automation_id": aid,
                "total_triggers": total,
                "accepted": accepted,
                "declined": declined,
                "snoozed": snoozed,
                "acceptance_rate": rate,
                "disabled": prefs.get("disabled", False),
                "preferred_hour": timing.get("preferred_hour"),
                "health": "good" if rate >= 60 else ("moderate" if rate >= 30 else "poor"),
            })

        report.sort(key=lambda x: x.get("acceptance_rate", 0), reverse=True)
        return report

    def get_monthly_insights(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Generate monthly learning insights summary."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        al = profile.get("automation_learning", {})
        responses = al.get("responses", [])

        cutoff = (now - timedelta(days=30)).isoformat()
        recent = [r for r in responses if str(r.get("timestamp", "")) >= cutoff]

        if not recent:
            return {"available": False, "message": "No automation data this month."}

        total = len(recent)
        accepted = sum(1 for r in recent if r.get("response") == "accepted")
        declined = sum(1 for r in recent if r.get("response") == "declined")

        insights: list[str] = []

        # Timing insights
        timing_adj = al.get("timing_adjustments", {})
        for aid, adj in timing_adj.items():
            if adj.get("preferred_hour") is not None:
                insights.append(f"You prefer '{aid}' around {adj['preferred_hour']}:00.")

        # Weekend vs weekday
        weekday_accepted = sum(1 for r in recent if r.get("response") == "accepted" and int(r.get("weekday", 0)) < 5)
        weekend_accepted = sum(1 for r in recent if r.get("response") == "accepted" and int(r.get("weekday", 0)) >= 5)
        weekday_total = sum(1 for r in recent if int(r.get("weekday", 0)) < 5)
        weekend_total = sum(1 for r in recent if int(r.get("weekday", 0)) >= 5)

        if weekday_total > 5 and weekend_total > 2:
            wd_rate = weekday_accepted / weekday_total * 100
            we_rate = weekend_accepted / weekend_total * 100 if weekend_total > 0 else 0
            if abs(wd_rate - we_rate) > 20:
                insights.append(
                    f"Weekday acceptance: {wd_rate:.0f}% vs Weekend: {we_rate:.0f}%. "
                    "Different weekend patterns detected."
                )

        return {
            "available": True,
            "period": "last 30 days",
            "total_triggers": total,
            "acceptance_rate": round(accepted / total * 100, 1) if total > 0 else 0,
            "declined_rate": round(declined / total * 100, 1) if total > 0 else 0,
            "insights": insights,
            "message": f"This month: {total} automations, {accepted} accepted ({accepted / total * 100:.0f}%)." if total > 0 else "",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_acceptance_rate(self, al: dict, automation_id: str) -> float | None:
        import math
        responses = al.get("responses", [])
        relevant = [r for r in responses if r.get("automation_id") == automation_id]
        if len(relevant) < self._min_samples:
            return None
        now_iso = _utcnow().isoformat()
        total_weight = 0.0
        accepted_weight = 0.0
        for r in relevant:
            ts = str(r.get("timestamp", "") or "")
            # Exponential decay: weight halves every 14 days based on lexicographic age.
            age_factor = max(0.0, (now_iso[:10] > ts[:10]) - 0) if ts else 1.0
            try:
                from datetime import datetime
                days_old = (datetime.fromisoformat(now_iso[:10]) - datetime.fromisoformat(ts[:10])).days
                weight = math.exp(-days_old / 14.0)
            except Exception:
                weight = 1.0
            total_weight += weight
            if r.get("response") == "accepted":
                accepted_weight += weight
        if total_weight == 0:
            return None
        return round(accepted_weight / total_weight * 100, 1)

    def _update_timing_preference(self, al: dict, automation_id: str, response: str, now: datetime) -> None:
        if response == "snoozed":
            timing = al.setdefault("timing_adjustments", {}).setdefault(automation_id, {})
            snooze_count = int(timing.get("snooze_count", 0)) + 1
            timing["snooze_count"] = snooze_count

            if snooze_count >= 3:
                current_pref = timing.get("preferred_hour", now.hour)
                timing["preferred_hour"] = (int(current_pref) + 1) % 24
                timing["adjusted_at"] = now.isoformat()
                logger.info(
                    "Timing adjusted for %s: preferred hour -> %d",
                    automation_id, timing["preferred_hour"],
                )

        elif response == "accepted":
            timing = al.setdefault("timing_adjustments", {}).setdefault(automation_id, {})
            accepted_hours = timing.get("accepted_hours", [])
            accepted_hours.append(now.hour)
            accepted_hours = accepted_hours[-20:]
            timing["accepted_hours"] = accepted_hours

            if len(accepted_hours) >= 5:
                from collections import Counter
                most_common = Counter(accepted_hours).most_common(1)
                if most_common:
                    timing["preferred_hour"] = most_common[0][0]
