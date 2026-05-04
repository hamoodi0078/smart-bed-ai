"""Achievement and milestone system for Smart Bed AI.

Tracks user milestones across sleep, prayer, feature usage, streaks,
and automation engagement. Awards badges, unlocks features, and
celebrates progress.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("gamification.achievement_engine")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


ACHIEVEMENTS = {
    # Sleep tracking milestones
    "first_week": {
        "name": "First Week Complete",
        "description": "Tracked 7 nights of sleep",
        "category": "sleep",
        "threshold": 7,
        "reward": "custom_scene_builder",
    },
    "monthly_champion": {
        "name": "Monthly Champion",
        "description": "Tracked 30 nights of sleep",
        "category": "sleep",
        "threshold": 30,
        "reward": "advanced_sleep_analytics",
    },
    "sleep_master": {
        "name": "Sleep Master",
        "description": "Tracked 100 nights of sleep",
        "category": "sleep",
        "threshold": 100,
        "reward": "exclusive_scene_pack",
    },
    "year_of_excellence": {
        "name": "Year of Excellence",
        "description": "Tracked 365 nights of sleep",
        "category": "sleep",
        "threshold": 365,
        "reward": "lifetime_discount_50",
    },
    # Sleep quality
    "quality_sleeper": {
        "name": "Quality Sleeper",
        "description": "7 nights with sleep score >80",
        "category": "quality",
        "threshold": 7,
        "reward": "sleep_insights_badge",
    },
    "elite_sleeper": {
        "name": "Elite Sleeper",
        "description": "30 nights average score >85",
        "category": "quality",
        "threshold": 30,
        "reward": "community_feature",
    },
    # Prayer consistency
    "prayer_streak_7": {
        "name": "Prayer Streak Started",
        "description": "7 consecutive days of prayer reminders acknowledged",
        "category": "prayer",
        "threshold": 7,
        "reward": "special_prayer_scenes",
    },
    "devoted_worshipper": {
        "name": "Devoted Worshipper",
        "description": "30 days of prayer consistency",
        "category": "prayer",
        "threshold": 30,
        "reward": "ramadan_scenes",
    },
    "prayer_warrior": {
        "name": "Prayer Warrior",
        "description": "90 days of prayer consistency",
        "category": "prayer",
        "threshold": 90,
        "reward": "custom_adhan_library",
    },
    # Feature discovery
    "explorer": {
        "name": "Explorer",
        "description": "Used 5 different features",
        "category": "features",
        "threshold": 5,
        "reward": "feature_badge",
    },
    "power_user": {
        "name": "Power User",
        "description": "Used 10 different features",
        "category": "features",
        "threshold": 10,
        "reward": "beta_access",
    },
    # Automation
    "automation_believer": {
        "name": "Automation Believer",
        "description": "Accepted 50 automation suggestions",
        "category": "automation",
        "threshold": 50,
        "reward": "advanced_ai_coaching",
    },
    "fully_automated": {
        "name": "Fully Automated",
        "description": "Accepted 100 automation suggestions",
        "category": "automation",
        "threshold": 100,
        "reward": "custom_automation_builder",
    },
    # Streaks
    "consistent_7": {
        "name": "Consistent Sleeper",
        "description": "7-night bedtime consistency streak",
        "category": "streak",
        "threshold": 7,
        "reward": "streak_badge",
    },
    "consistent_30": {
        "name": "Iron Discipline",
        "description": "30-night bedtime consistency streak",
        "category": "streak",
        "threshold": 30,
        "reward": "premium_scene",
    },
    # Wellness
    "breathing_10": {
        "name": "Zen Beginner",
        "description": "Completed 10 breathing exercises",
        "category": "wellness",
        "threshold": 10,
        "reward": "extended_breathing_library",
    },
    "debt_free": {
        "name": "Debt Free",
        "description": "Cleared all sleep debt",
        "category": "wellness",
        "threshold": 1,
        "reward": "celebration_animation",
    },
}


class AchievementEngine:
    """Tracks and awards achievements based on user activity milestones."""

    def __init__(self):
        self._definitions = dict(ACHIEVEMENTS)

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("achievements", {})
        ach = profile["achievements"]
        ach.setdefault("unlocked", [])
        ach.setdefault("progress", {})
        ach.setdefault("total_points", 0)
        ach.setdefault("level", 1)

    # ------------------------------------------------------------------
    # Progress tracking
    # ------------------------------------------------------------------

    def update_progress(
        self, profile: dict, achievement_id: str, value: int = 1, now: datetime | None = None
    ) -> dict[str, Any] | None:
        """Increment progress for an achievement. Returns unlock info if newly unlocked."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        ach = profile["achievements"]

        if achievement_id not in self._definitions:
            return None

        unlocked_ids = [u.get("id", "") for u in ach.get("unlocked", [])]
        if achievement_id in unlocked_ids:
            return None

        definition = self._definitions[achievement_id]
        progress = ach.get("progress", {})
        current = int(progress.get(achievement_id, 0)) + max(0, int(value))
        progress[achievement_id] = current

        if current >= definition["threshold"]:
            return self._unlock(profile, achievement_id, definition, now)

        return None

    def set_progress(
        self, profile: dict, achievement_id: str, value: int, now: datetime | None = None
    ) -> dict[str, Any] | None:
        """Set absolute progress for an achievement."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        ach = profile["achievements"]

        if achievement_id not in self._definitions:
            return None

        unlocked_ids = [u.get("id", "") for u in ach.get("unlocked", [])]
        if achievement_id in unlocked_ids:
            return None

        definition = self._definitions[achievement_id]
        ach["progress"][achievement_id] = max(0, int(value))

        if int(value) >= definition["threshold"]:
            return self._unlock(profile, achievement_id, definition, now)

        return None

    # ------------------------------------------------------------------
    # Batch evaluation (called periodically)
    # ------------------------------------------------------------------

    def evaluate_all(self, profile: dict, now: datetime | None = None) -> list[dict[str, Any]]:
        """Evaluate all achievement conditions and return newly unlocked ones."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        newly_unlocked: list[dict[str, Any]] = []

        metrics = self._gather_metrics(profile)

        metric_map = {
            "first_week": metrics.get("total_sleep_nights", 0),
            "monthly_champion": metrics.get("total_sleep_nights", 0),
            "sleep_master": metrics.get("total_sleep_nights", 0),
            "year_of_excellence": metrics.get("total_sleep_nights", 0),
            "quality_sleeper": metrics.get("high_score_nights", 0),
            "elite_sleeper": metrics.get("high_score_nights_30", 0),
            "prayer_streak_7": metrics.get("prayer_streak", 0),
            "devoted_worshipper": metrics.get("prayer_streak", 0),
            "prayer_warrior": metrics.get("prayer_streak", 0),
            "explorer": metrics.get("features_used", 0),
            "power_user": metrics.get("features_used", 0),
            "automation_believer": metrics.get("automations_accepted", 0),
            "fully_automated": metrics.get("automations_accepted", 0),
            "consistent_7": metrics.get("consistency_streak", 0),
            "consistent_30": metrics.get("consistency_streak", 0),
            "breathing_10": metrics.get("breathing_completed", 0),
            "debt_free": 1 if metrics.get("sleep_debt", 1) <= 0 else 0,
        }

        for aid, current_value in metric_map.items():
            result = self.set_progress(profile, aid, current_value, now)
            if result:
                newly_unlocked.append(result)

        return newly_unlocked

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_unlocked(self, profile: dict) -> list[dict[str, Any]]:
        self.ensure_shape(profile)
        return list(profile["achievements"].get("unlocked", []))

    def get_all_progress(self, profile: dict) -> list[dict[str, Any]]:
        self.ensure_shape(profile)
        ach = profile["achievements"]
        progress = ach.get("progress", {})
        unlocked_ids = {u.get("id", "") for u in ach.get("unlocked", [])}

        result: list[dict[str, Any]] = []
        for aid, definition in self._definitions.items():
            current = int(progress.get(aid, 0))
            threshold = definition["threshold"]
            result.append({
                "id": aid,
                "name": definition["name"],
                "description": definition["description"],
                "category": definition["category"],
                "current": current,
                "threshold": threshold,
                "progress_pct": min(100, round(current / threshold * 100, 1)) if threshold > 0 else 0,
                "unlocked": aid in unlocked_ids,
                "reward": definition["reward"],
            })
        return result

    def get_stats(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        ach = profile["achievements"]
        unlocked = len(ach.get("unlocked", []))
        total = len(self._definitions)
        return {
            "total_achievements": total,
            "unlocked": unlocked,
            "locked": total - unlocked,
            "completion_pct": round(unlocked / total * 100, 1) if total > 0 else 0,
            "total_points": int(ach.get("total_points", 0)),
            "level": int(ach.get("level", 1)),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _unlock(self, profile: dict, aid: str, definition: dict, now: datetime) -> dict[str, Any]:
        ach = profile["achievements"]
        entry = {
            "id": aid,
            "name": definition["name"],
            "description": definition["description"],
            "category": definition["category"],
            "reward": definition["reward"],
            "unlocked_at": now.isoformat(),
        }
        ach["unlocked"].append(entry)

        points = {"sleep": 50, "quality": 75, "prayer": 100, "features": 30,
                  "automation": 60, "streak": 80, "wellness": 40}.get(definition["category"], 50)
        ach["total_points"] = int(ach.get("total_points", 0)) + points
        ach["level"] = 1 + int(ach.get("total_points", 0)) // 200

        logger.info("Achievement unlocked: %s (%s)", definition["name"], aid)

        entry["celebration"] = {
            "type": "led_scene",
            "action": "achievement_celebration",
            "color": "#FFD700",
            "brightness": 0.50,
            "animation": "fireworks",
            "duration_seconds": 10,
        }
        entry["notification"] = {
            "type": "notification",
            "category": "achievement",
            "message": f"Achievement Unlocked: {definition['name']}! {definition['description']}",
            "priority": "high",
        }
        entry["voice"] = {
            "type": "voice",
            "message": f"MashaAllah! Achievement unlocked: {definition['name']}!",
            "volume": 0.5,
        }

        return entry

    @staticmethod
    def _gather_metrics(profile: dict) -> dict[str, Any]:
        sleep = profile.get("sleep", {})
        bed_hist = sleep.get("bedtime_history", [])
        wake_hist = sleep.get("wake_history", [])

        total_nights = min(len(bed_hist), len(wake_hist))

        scores = profile.get("sleep_scores", [])
        if not isinstance(scores, list):
            scores = []
        high_score = sum(1 for s in scores if isinstance(s, (int, float)) and s >= 80)
        high_score_30 = sum(1 for s in scores[-30:] if isinstance(s, (int, float)) and s >= 85)

        islamic = profile.get("islamic", {})
        prayer_stats = islamic.get("prayer_stats", {})
        prayer_ack = int(prayer_stats.get("acknowledged_count", 0))

        features = profile.get("subscription", {}).get("features_used", [])
        al = profile.get("automation_learning", {})
        accepted = sum(1 for r in al.get("responses", []) if r.get("response") == "accepted")

        debt = float(profile.get("sleep_debt", {}).get("cumulative_debt_hours", 1))

        return {
            "total_sleep_nights": total_nights,
            "high_score_nights": high_score,
            "high_score_nights_30": high_score_30,
            "prayer_streak": prayer_ack,
            "features_used": len(features) if isinstance(features, list) else 0,
            "automations_accepted": accepted,
            "consistency_streak": 0,
            "breathing_completed": 0,
            "sleep_debt": debt,
        }
