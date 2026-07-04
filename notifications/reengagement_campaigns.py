"""Re-engagement and churn prevention campaigns for Smart Bed AI.

Detects inactive users, runs tiered re-engagement campaigns,
identifies churn risk signals, and manages win-back offers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("notifications.reengagement_campaigns")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReengagementCampaigns:
    """Manages automated re-engagement and churn prevention flows."""

    def __init__(
        self,
        *,
        level1_inactive_days: int = 3,
        level2_inactive_days: int = 7,
        level3_inactive_days: int = 14,
        level4_inactive_days: int = 30,
        campaign_cooldown_hours: float = 48.0,
    ):
        self._levels = {
            1: max(1, int(level1_inactive_days)),
            2: max(2, int(level2_inactive_days)),
            3: max(3, int(level3_inactive_days)),
            4: max(7, int(level4_inactive_days)),
        }
        self._cooldown = max(12.0, float(campaign_cooldown_hours))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("reengagement", {})
        re = profile["reengagement"]
        re.setdefault("last_active_at", "")
        re.setdefault("last_campaign_at", "")
        re.setdefault("last_campaign_level", 0)
        re.setdefault("campaigns_sent", [])
        re.setdefault("paused", False)
        re.setdefault("win_back_offered", False)

    # ------------------------------------------------------------------
    # Activity tracking
    # ------------------------------------------------------------------

    def record_activity(self, profile: dict, now: datetime | None = None) -> None:
        """Record that user was active (resets inactivity timer)."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        profile["reengagement"]["last_active_at"] = now.isoformat()
        profile["reengagement"]["last_campaign_level"] = 0

    def get_inactive_days(self, profile: dict, now: datetime | None = None) -> int:
        """Calculate days since last activity."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        last_str = profile["reengagement"].get("last_active_at", "")
        if not last_str:
            return 0
        try:
            last = datetime.fromisoformat(last_str)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            return max(0, (now - last).days)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Campaign evaluation
    # ------------------------------------------------------------------

    def evaluate(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Evaluate if a re-engagement campaign should be sent.

        Returns a result dict always. Check ``result["status"]`` for
        ``"sent"`` vs ``"skipped"`` (with a ``"reason"`` key).
        """
        now = now or _utcnow()
        self.ensure_shape(profile)
        re = profile.get("reengagement", {})

        if re.get("paused", False):
            return {"status": "skipped", "reason": "campaigns_paused"}

        if not self._can_send(re, now):
            return {"status": "skipped", "reason": "cooldown_active"}

        inactive_days = self.get_inactive_days(profile, now)
        last_level = int(re.get("last_campaign_level", 0))

        level = 0
        if inactive_days >= self._levels[4]:
            level = 4
        elif inactive_days >= self._levels[3]:
            level = 3
        elif inactive_days >= self._levels[2]:
            level = 2
        elif inactive_days >= self._levels[1]:
            level = 1

        if level == 0:
            return {
                "status": "skipped",
                "reason": "not_inactive_enough",
                "inactive_days": inactive_days,
            }
        if level <= last_level:
            return {
                "status": "skipped",
                "reason": "level_already_sent",
                "level": level,
                "inactive_days": inactive_days,
            }

        actions = self._build_campaign(level, inactive_days, profile)
        if not actions:
            return {"status": "skipped", "reason": "no_actions_built", "level": level}

        re["last_campaign_at"] = now.isoformat()
        re["last_campaign_level"] = level
        re["campaigns_sent"].append(
            {
                "level": level,
                "inactive_days": inactive_days,
                "sent_at": now.isoformat(),
            }
        )
        re["campaigns_sent"] = re["campaigns_sent"][-50:]

        logger.info("Re-engagement campaign level %d sent (inactive %d days)", level, inactive_days)
        return {
            "status": "sent",
            "level": level,
            "inactive_days": inactive_days,
            "actions": actions,
        }

    # ------------------------------------------------------------------
    # Campaign builders
    # ------------------------------------------------------------------

    def _build_campaign(
        self, level: int, inactive_days: int, profile: dict
    ) -> list[dict[str, Any]]:
        if level == 1:
            return [
                {
                    "type": "notification",
                    "category": "reengagement_gentle",
                    "message": "We miss you! Everything OK? Your prayer reminders are waiting.",
                    "priority": "medium",
                    "channels": ["push"],
                }
            ]

        if level == 2:
            features_used = len(profile.get("subscription", {}).get("features_used", []))
            return [
                {
                    "type": "notification",
                    "category": "reengagement_value",
                    "message": f"It's been {inactive_days} days. You've used {features_used} features — come back and discover more!",
                    "priority": "medium",
                    "channels": ["push", "email"],
                }
            ]

        if level == 3:
            return [
                {
                    "type": "notification",
                    "category": "reengagement_survey",
                    "message": f"We haven't seen you in {inactive_days} days. What made you stop? We'd love to improve.",
                    "priority": "high",
                    "channels": ["push", "email", "whatsapp"],
                },
                {
                    "type": "prompt",
                    "action": "show_feedback_survey",
                    "options": [
                        "Too complicated",
                        "Not useful enough",
                        "Technical issues",
                        "Just busy",
                    ],
                },
            ]

        if level == 4:
            return [
                {
                    "type": "notification",
                    "category": "reengagement_final",
                    "message": "We're here when you're ready. Your sleep data is safely stored.",
                    "priority": "low",
                    "channels": ["email"],
                }
            ]

        return []

    # ------------------------------------------------------------------
    # Churn detection
    # ------------------------------------------------------------------

    def detect_churn_risk(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Analyze signals that suggest user may churn."""
        now = now or _utcnow()
        self.ensure_shape(profile)

        signals: list[str] = []
        risk_score = 0

        inactive_days = self.get_inactive_days(profile, now)
        if inactive_days >= 7:
            signals.append(f"inactive_{inactive_days}_days")
            risk_score += min(40, inactive_days * 3)

        al = profile.get("automation_learning", {})
        responses = al.get("responses", [])
        recent_declined = sum(1 for r in responses[-20:] if r.get("response") == "declined")
        if recent_declined >= 10:
            signals.append("high_decline_rate")
            risk_score += 20

        stress = profile.get("stress", {})
        if int(stress.get("last_score", 0)) >= 80:
            signals.append("high_stress")
            risk_score += 10

        sleep = profile.get("sleep_debt", {})
        if float(sleep.get("cumulative_debt_hours", 0)) > 10:
            signals.append("severe_sleep_debt")
            risk_score += 10

        risk_score = min(100, risk_score)
        level = "high" if risk_score >= 60 else ("medium" if risk_score >= 30 else "low")

        return {
            "risk_score": risk_score,
            "risk_level": level,
            "signals": signals,
            "inactive_days": inactive_days,
            "intervention_recommended": risk_score >= 40,
        }

    # ------------------------------------------------------------------
    # Cancel prevention
    # ------------------------------------------------------------------

    def get_cancel_prevention_flow(self, profile: dict, reason: str = "") -> dict[str, Any]:
        """Generate cancel prevention options when user tries to cancel."""
        self.ensure_shape(profile)
        reason = str(reason).strip().lower()

        options: list[dict[str, Any]] = []

        if "expensive" in reason or "price" in reason or "cost" in reason:
            options.append(
                {
                    "type": "offer",
                    "name": "discount",
                    "message": "How about 30% off your next 3 months?",
                    "action": "apply_discount_30",
                }
            )

        if "not using" in reason or "don't use" in reason:
            options.append(
                {
                    "type": "offer",
                    "name": "tutorial",
                    "message": "Let us show you features that could help. Quick 5-min setup?",
                    "action": "start_tutorial",
                }
            )

        if "technical" in reason or "bug" in reason:
            options.append(
                {
                    "type": "offer",
                    "name": "support",
                    "message": "We're sorry! Let's fix this immediately. Connect with support?",
                    "action": "connect_support",
                }
            )

        options.append(
            {
                "type": "offer",
                "name": "pause",
                "message": "Instead of canceling, pause for 30 days? Your data stays safe.",
                "action": "pause_subscription",
            }
        )
        options.append(
            {
                "type": "offer",
                "name": "downgrade",
                "message": "Try the free tier first — you can always upgrade again.",
                "action": "downgrade_to_free",
            }
        )

        return {
            "reason": reason,
            "options": options,
            "win_back_guarantee": "Cancel now and return free within 60 days.",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _can_send(self, re: dict, now: datetime) -> bool:
        last_str = str(re.get("last_campaign_at", "")).strip()
        if not last_str:
            return True
        try:
            last = datetime.fromisoformat(last_str)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (now - last).total_seconds() / 3600.0
            return elapsed >= self._cooldown
        except Exception:
            return True

    def get_stats(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        re = profile.get("reengagement", {})
        return {
            "inactive_days": self.get_inactive_days(profile),
            "campaigns_sent_total": len(re.get("campaigns_sent", [])),
            "last_campaign_level": int(re.get("last_campaign_level", 0)),
            "paused": re.get("paused", False),
        }
