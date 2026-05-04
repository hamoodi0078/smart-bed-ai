"""Trial lifecycle automation for Smart Bed AI subscriptions.

Manages the 14-day free trial journey with timed touchpoints,
feature discovery prompts, value reminders, and upgrade nudges.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("subscriptions.trial_automation")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrialAutomation:
    """Manages automated trial lifecycle engagement touchpoints."""

    TRIAL_DAYS = 14

    def __init__(self, *, trial_days: int = 14):
        self._trial_days = max(7, int(trial_days))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("subscription", {})
        sub = profile["subscription"]
        sub.setdefault("plan", "trial")
        sub.setdefault("trial_start_date", "")
        sub.setdefault("trial_end_date", "")
        sub.setdefault("touchpoints_sent", [])
        sub.setdefault("features_used", [])
        sub.setdefault("upgrade_offered", False)
        sub.setdefault("converted", False)

    # ------------------------------------------------------------------
    # Trial setup
    # ------------------------------------------------------------------

    def start_trial(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Initialize a new trial period."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        sub = profile["subscription"]
        sub["plan"] = "trial"
        sub["trial_start_date"] = now.date().isoformat()
        sub["trial_end_date"] = (now + timedelta(days=self._trial_days)).date().isoformat()
        sub["touchpoints_sent"] = []
        sub["converted"] = False

        return {
            "started": True,
            "trial_end": sub["trial_end_date"],
            "days": self._trial_days,
            "actions": [{
                "type": "notification",
                "category": "trial_welcome",
                "message": "Welcome to Dana! Your premium trial starts now. Explore all features!",
                "priority": "high",
            }, {
                "type": "voice",
                "message": "Welcome to Dana! Let's set up your profile for the best experience.",
                "volume": 0.5,
            }],
        }

    # ------------------------------------------------------------------
    # Trial evaluation (called daily)
    # ------------------------------------------------------------------

    def evaluate(self, profile: dict, now: datetime | None = None) -> dict[str, Any] | None:
        """Evaluate trial status and return appropriate touchpoint actions."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        sub = profile.get("subscription", {})

        if sub.get("plan") != "trial" or sub.get("converted", False):
            return None

        start_str = sub.get("trial_start_date", "")
        if not start_str:
            return None

        try:
            start = datetime.fromisoformat(start_str)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except Exception:
            return None

        day = (now.date() - start.date()).days + 1
        sent = set(sub.get("touchpoints_sent", []))
        features = sub.get("features_used", [])

        touchpoint_key = f"day_{day}"
        if touchpoint_key in sent:
            return None

        actions = self._get_touchpoint(day, features, sub)
        if not actions:
            return None

        sub["touchpoints_sent"] = list(sent | {touchpoint_key})
        return {"day": day, "touchpoint": touchpoint_key, "actions": actions}

    def _get_touchpoint(self, day: int, features: list, sub: dict) -> list[dict[str, Any]] | None:
        if day == 1:
            return [{
                "type": "notification",
                "category": "trial_day1",
                "message": "Day 1: Explore voice commands, sleep tracking, and prayer automation!",
                "priority": "medium",
            }]

        if day == 3:
            unused = self._find_unused_features(features)
            tip = f"Try {unused[0]}!" if unused else "You're exploring great!"
            return [{
                "type": "notification",
                "category": "trial_day3",
                "message": f"Day 3 of your trial. {tip} Features used: {len(features)}.",
                "priority": "medium",
            }]

        if day == 7:
            return [{
                "type": "notification",
                "category": "trial_midpoint",
                "message": "Halfway through your trial! You've used {} features. See your sleep improvement so far.".format(len(features)),
                "priority": "high",
            }]

        if day == 11:
            return [{
                "type": "notification",
                "category": "trial_expiring_soon",
                "message": "Trial ends in 3 days. After that, you'll lose premium features like smart wake and AI coaching.",
                "priority": "high",
            }, {
                "type": "prompt",
                "action": "show_upgrade_comparison",
                "message": "Compare free vs premium features",
            }]

        if day == 13:
            return [{
                "type": "notification",
                "category": "trial_last_day_warning",
                "message": "Last full day of your trial tomorrow! Subscribe today for 20% off your first month.",
                "priority": "high",
            }]

        if day == self._trial_days:
            return [{
                "type": "notification",
                "category": "trial_expired",
                "message": "Your trial has ended. Upgrade anytime to restore premium features.",
                "priority": "high",
            }, {
                "type": "system",
                "action": "downgrade_to_free",
            }]

        if day == self._trial_days + 1:
            return [{
                "type": "notification",
                "category": "post_trial_day1",
                "message": "Miss the smart wake feature? Upgrade to get it back anytime.",
                "priority": "low",
            }]

        if day == self._trial_days + 3:
            return [{
                "type": "notification",
                "category": "post_trial_day3",
                "message": "Your sleep insights are waiting. Upgrade to continue tracking improvements.",
                "priority": "low",
            }]

        if day == self._trial_days + 7:
            return [{
                "type": "notification",
                "category": "post_trial_week1",
                "message": "It's been a week since your trial ended. Come back with a special offer!",
                "priority": "low",
            }]

        return None

    # ------------------------------------------------------------------
    # Feature tracking
    # ------------------------------------------------------------------

    def track_feature_used(self, profile: dict, feature: str) -> None:
        """Record that a premium feature was used during trial."""
        self.ensure_shape(profile)
        sub = profile["subscription"]
        features = sub.get("features_used", [])
        feature = str(feature).strip()
        if feature and feature not in features:
            features.append(feature)
        sub["features_used"] = features

    def get_trial_status(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Get current trial status summary."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        sub = profile.get("subscription", {})

        if sub.get("plan") != "trial":
            return {"in_trial": False, "plan": sub.get("plan", "free")}

        start_str = sub.get("trial_start_date", "")
        end_str = sub.get("trial_end_date", "")
        if not start_str or not end_str:
            return {"in_trial": False}

        try:
            end = datetime.fromisoformat(end_str).date()
            days_remaining = (end - now.date()).days
        except Exception:
            days_remaining = 0

        return {
            "in_trial": days_remaining > 0,
            "plan": "trial",
            "start_date": start_str,
            "end_date": end_str,
            "days_remaining": max(0, days_remaining),
            "features_used": len(sub.get("features_used", [])),
            "touchpoints_sent": len(sub.get("touchpoints_sent", [])),
        }

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def mark_converted(self, profile: dict, plan: str = "premium") -> dict[str, Any]:
        self.ensure_shape(profile)
        sub = profile["subscription"]
        sub["plan"] = str(plan).strip()
        sub["converted"] = True
        sub["converted_at"] = _utcnow().isoformat()
        return {"converted": True, "plan": plan}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_unused_features(used: list) -> list[str]:
        all_features = [
            "smart_wake", "sleep_tracking", "prayer_automation", "ai_coaching",
            "breathing_exercises", "mood_tracking", "circadian_lighting",
            "nap_detection", "weekly_report", "partner_mode",
        ]
        return [f for f in all_features if f not in used][:3]
