"""Dual pressure sensor partner detection engine for Smart Bed AI.

Manages partner identification via left/right pressure sensors,
separate sleep tracking per partner, preference profiles, and
couple sleep goal tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("core.partner_engine")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PartnerEngine:
    """Manages dual-user partner mode with individual tracking and couple goals."""

    def __init__(self):
        self._partner1_side = "left"
        self._partner2_side = "right"
        self._both_present = False
        self._active_partner = ""

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("partner_mode", {})
        pm = profile["partner_mode"]
        pm.setdefault("enabled", False)
        pm.setdefault("partner1", {
            "name": "Partner 1",
            "side": "left",
            "wake_time": "07:00",
            "sleep_target_hours": 8.0,
            "scene_preferences": {},
            "sleep_history": [],
        })
        pm.setdefault("partner2", {
            "name": "Partner 2",
            "side": "right",
            "wake_time": "07:00",
            "sleep_target_hours": 8.0,
            "scene_preferences": {},
            "sleep_history": [],
        })
        pm.setdefault("couple_goals", {
            "active_challenges": [],
            "achievements": [],
            "shared_bedtime_target": "23:00",
            "streak_both_met_goal": 0,
        })
        pm.setdefault("compromise_settings", {
            "brightness_strategy": "average",
            "sound_strategy": "quieter",
            "wake_strategy": "staggered",
        })

    # ------------------------------------------------------------------
    # Partner identification
    # ------------------------------------------------------------------

    def identify_from_pressure(
        self, profile: dict, left_occupied: bool, right_occupied: bool
    ) -> dict[str, Any]:
        """Identify which partner(s) are in bed based on pressure zones."""
        self.ensure_shape(profile)
        pm = profile.get("partner_mode", {})
        if not pm.get("enabled", False):
            return {"partner_mode": False}

        p1_side = str(pm.get("partner1", {}).get("side", "left"))
        p2_side = str(pm.get("partner2", {}).get("side", "right"))

        p1_present = left_occupied if p1_side == "left" else right_occupied
        p2_present = right_occupied if p2_side == "right" else left_occupied
        self._both_present = p1_present and p2_present

        present: list[str] = []
        if p1_present:
            present.append(pm.get("partner1", {}).get("name", "Partner 1"))
        if p2_present:
            present.append(pm.get("partner2", {}).get("name", "Partner 2"))

        return {
            "partner_mode": True,
            "partner1_present": p1_present,
            "partner2_present": p2_present,
            "both_present": self._both_present,
            "present_names": present,
            "active_partners": len(present),
        }

    def is_both_present(self) -> bool:
        return self._both_present

    # ------------------------------------------------------------------
    # Individual sleep tracking
    # ------------------------------------------------------------------

    def record_sleep(
        self, profile: dict, partner: str, hours: float, score: int, now: datetime | None = None
    ) -> dict[str, Any]:
        """Record sleep data for a specific partner."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        pm = profile["partner_mode"]

        partner_key = "partner1" if partner in ("partner1", "1", "left") else "partner2"
        p_data = pm.get(partner_key, {})

        entry = {
            "date": now.date().isoformat(),
            "hours": round(float(hours), 2),
            "score": max(0, min(100, int(score))),
            "target": float(p_data.get("sleep_target_hours", 8.0)),
        }

        history = p_data.get("sleep_history", [])
        history.append(entry)
        p_data["sleep_history"] = history[-90:]

        self._update_couple_streak(profile, now)

        return {
            "recorded": True,
            "partner": partner_key,
            "name": p_data.get("name", partner_key),
            "entry": entry,
        }

    def get_partner_stats(self, profile: dict, partner: str, days: int = 7) -> dict[str, Any]:
        """Get sleep stats for a specific partner."""
        self.ensure_shape(profile)
        pm = profile.get("partner_mode", {})
        partner_key = "partner1" if partner in ("partner1", "1", "left") else "partner2"
        p_data = pm.get(partner_key, {})
        history = p_data.get("sleep_history", [])

        cutoff = (_utcnow() - timedelta(days=max(1, days))).date().isoformat()
        recent = [h for h in history if str(h.get("date", "")) >= cutoff]

        if not recent:
            return {"name": p_data.get("name", ""), "nights": 0}

        hours_list = [float(h.get("hours", 0)) for h in recent]
        scores = [int(h.get("score", 0)) for h in recent]
        target = float(p_data.get("sleep_target_hours", 8.0))
        met_goal = sum(1 for h in hours_list if h >= target)

        return {
            "name": p_data.get("name", partner_key),
            "nights": len(recent),
            "avg_hours": round(sum(hours_list) / len(hours_list), 1) if hours_list else 0,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "target_hours": target,
            "goal_met_nights": met_goal,
            "goal_rate": round(met_goal / len(recent) * 100, 1) if recent else 0,
        }

    def get_comparison(self, profile: dict, days: int = 7) -> dict[str, Any]:
        """Side-by-side comparison of both partners' sleep stats."""
        self.ensure_shape(profile)
        p1 = self.get_partner_stats(profile, "partner1", days)
        p2 = self.get_partner_stats(profile, "partner2", days)

        return {
            "partner1": p1,
            "partner2": p2,
            "period_days": days,
            "combined_avg_score": round(
                ((p1.get("avg_score", 0) or 0) + (p2.get("avg_score", 0) or 0)) / 2, 1
            ),
            "both_met_goal": p1.get("goal_rate", 0) >= 70 and p2.get("goal_rate", 0) >= 70,
        }

    # ------------------------------------------------------------------
    # Couple goals
    # ------------------------------------------------------------------

    def add_couple_challenge(self, profile: dict, challenge: dict[str, Any]) -> dict[str, Any]:
        """Add a shared couple challenge."""
        self.ensure_shape(profile)
        goals = profile["partner_mode"]["couple_goals"]
        challenges = goals.get("active_challenges", [])

        entry = {
            "name": str(challenge.get("name", "")).strip(),
            "description": str(challenge.get("description", "")).strip(),
            "target_days": max(1, int(challenge.get("target_days", 7))),
            "started_at": _utcnow().isoformat(),
            "progress_days": 0,
            "completed": False,
        }
        challenges.append(entry)
        goals["active_challenges"] = challenges[-10:]

        return {"added": True, "challenge": entry}

    def update_challenge_progress(self, profile: dict, now: datetime | None = None) -> list[dict[str, Any]]:
        """Check and update couple challenge progress. Returns newly completed challenges."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        goals = profile["partner_mode"]["couple_goals"]
        challenges = goals.get("active_challenges", [])
        completed: list[dict[str, Any]] = []

        comparison = self.get_comparison(profile, days=1)
        both_slept_well = (
            (comparison["partner1"].get("avg_score", 0) or 0) >= 70
            and (comparison["partner2"].get("avg_score", 0) or 0) >= 70
        )

        for ch in challenges:
            if ch.get("completed", False):
                continue
            if both_slept_well:
                ch["progress_days"] = int(ch.get("progress_days", 0)) + 1
            if ch["progress_days"] >= ch.get("target_days", 7):
                ch["completed"] = True
                ch["completed_at"] = now.isoformat()
                completed.append(ch)
                goals.setdefault("achievements", []).append({
                    "name": ch.get("name", ""),
                    "completed_at": now.isoformat(),
                })

        return completed

    def get_couple_achievements(self, profile: dict) -> list[dict[str, Any]]:
        self.ensure_shape(profile)
        return list(profile["partner_mode"]["couple_goals"].get("achievements", []))

    # ------------------------------------------------------------------
    # Default couple challenges
    # ------------------------------------------------------------------

    @staticmethod
    def get_default_challenges() -> list[dict[str, Any]]:
        return [
            {"name": "Sync Sleepers", "description": "Both in bed by 11 PM for 7 nights", "target_days": 7},
            {"name": "Dream Team", "description": "Combined sleep score >170 for 7 nights", "target_days": 7},
            {"name": "Early Birds", "description": "Both wake before 7 AM for 5 days", "target_days": 5},
            {"name": "Perfect Week", "description": "Both meet sleep goals every night for 7 days", "target_days": 7},
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_couple_streak(self, profile: dict, now: datetime) -> None:
        goals = profile["partner_mode"].get("couple_goals", {})
        comparison = self.get_comparison(profile, days=1)
        both_met = comparison.get("both_met_goal", False)
        if both_met:
            goals["streak_both_met_goal"] = int(goals.get("streak_both_met_goal", 0)) + 1
        else:
            goals["streak_both_met_goal"] = 0
