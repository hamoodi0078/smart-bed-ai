"""Stress pattern detection for Smart Bed AI.

Detects stress through multiple signals: overthinking dump frequency, restlessness
in bed, late bedtimes, short sleep, and mood keywords. Triggers automated
interventions (breathing exercises, calm scenes, coaching).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("health.stress_detector")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StressDetector:
    """Multi-signal stress detection with adaptive intervention."""

    MOOD_STRESS_KEYWORDS = {
        "stressed", "anxious", "overwhelmed", "worried", "nervous",
        "panic", "tense", "frustrated", "angry", "upset", "restless",
        "cant sleep", "can't sleep", "insomnia", "racing thoughts",
    }

    def __init__(
        self,
        *,
        stress_threshold: int = 60,
        high_stress_threshold: int = 80,
        overthinking_weight: int = 20,
        restlessness_weight: int = 15,
        late_bedtime_weight: int = 15,
        short_sleep_weight: int = 20,
        mood_keyword_weight: int = 25,
        intervention_cooldown_hours: float = 4.0,
        persistent_stress_days: int = 3,
    ):
        self._threshold = max(10, int(stress_threshold))
        self._high_threshold = max(self._threshold + 10, int(high_stress_threshold))
        self._weights = {
            "overthinking": max(1, int(overthinking_weight)),
            "restlessness": max(1, int(restlessness_weight)),
            "late_bedtime": max(1, int(late_bedtime_weight)),
            "short_sleep": max(1, int(short_sleep_weight)),
            "mood_keyword": max(1, int(mood_keyword_weight)),
        }
        self._cooldown_hours = max(1.0, float(intervention_cooldown_hours))
        self._persistent_days = max(2, int(persistent_stress_days))
        self._last_intervention_at: datetime | None = None

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("stress", {})
        stress = profile["stress"]
        stress.setdefault("history", [])
        stress.setdefault("interventions_log", [])
        stress.setdefault("total_interventions", 0)
        stress.setdefault("last_score", 0)
        stress.setdefault("last_score_date", "")

    # ------------------------------------------------------------------
    # Stress evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        profile: dict,
        *,
        restlessness_per_hour: float = 0.0,
        recent_mood_text: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Calculate stress score from multiple signals and recommend interventions."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        signals: dict[str, dict[str, Any]] = {}
        total_score = 0

        # Signal 1: Overthinking dumps frequency (last 24h)
        overthinking_count = self._count_recent_overthinking(profile, now)
        if overthinking_count >= 3:
            contribution = self._weights["overthinking"]
            signals["overthinking"] = {"count_24h": overthinking_count, "score": contribution}
            total_score += contribution
        elif overthinking_count >= 1:
            contribution = self._weights["overthinking"] // 2
            signals["overthinking"] = {"count_24h": overthinking_count, "score": contribution}
            total_score += contribution

        # Signal 2: Bed restlessness
        if restlessness_per_hour > 15:
            contribution = self._weights["restlessness"]
            signals["restlessness"] = {"per_hour": restlessness_per_hour, "score": contribution}
            total_score += contribution
        elif restlessness_per_hour > 8:
            contribution = self._weights["restlessness"] // 2
            signals["restlessness"] = {"per_hour": restlessness_per_hour, "score": contribution}
            total_score += contribution

        # Signal 3: Late bedtime pattern
        late_nights = self._count_late_nights(profile, days=5)
        if late_nights >= 3:
            contribution = self._weights["late_bedtime"]
            signals["late_bedtime"] = {"late_nights_5d": late_nights, "score": contribution}
            total_score += contribution

        # Signal 4: Short sleep pattern
        short_nights = self._count_short_sleep(profile, days=5)
        if short_nights >= 2:
            contribution = self._weights["short_sleep"]
            signals["short_sleep"] = {"short_nights_5d": short_nights, "score": contribution}
            total_score += contribution

        # Signal 5: Mood keywords
        mood_lower = str(recent_mood_text or "").strip().lower()
        matched_keywords = [kw for kw in self.MOOD_STRESS_KEYWORDS if kw in mood_lower]
        if matched_keywords:
            contribution = self._weights["mood_keyword"]
            signals["mood_keywords"] = {"matched": matched_keywords[:3], "score": contribution}
            total_score += contribution

        total_score = min(100, total_score)
        level = self._classify_level(total_score)

        # Record score
        profile["stress"]["last_score"] = total_score
        profile["stress"]["last_score_date"] = now.date().isoformat()
        self._append_history(profile, total_score, now)

        # Determine interventions
        interventions = []
        if total_score >= self._threshold:
            interventions = self._build_interventions(total_score, signals, profile, now)

        # Check for persistent stress
        persistent = self._is_persistent_stress(profile, now)

        return {
            "score": total_score,
            "level": level,
            "signals": signals,
            "interventions": interventions,
            "persistent_stress": persistent,
            "message": self._build_message(total_score, level, persistent),
        }

    # ------------------------------------------------------------------
    # Intervention builder
    # ------------------------------------------------------------------

    def _build_interventions(
        self, score: int, signals: dict, profile: dict, now: datetime
    ) -> list[dict[str, Any]]:
        if self._last_intervention_at:
            elapsed = (now - self._last_intervention_at).total_seconds() / 3600.0
            if elapsed < self._cooldown_hours:
                return []

        interventions: list[dict[str, Any]] = []

        # Always offer breathing exercise for stress
        interventions.append({
            "type": "breathing_exercise",
            "technique": "4-7-8" if score >= self._high_threshold else "4-6",
            "duration_minutes": 5,
            "message": "Let's do a quick breathing exercise to reset.",
            "priority": "high" if score >= self._high_threshold else "medium",
        })

        # Calm scene
        interventions.append({
            "type": "led_scene",
            "action": "calm_reset",
            "color": "#00CED1",
            "brightness": 0.20,
            "animation": "breathing",
        })

        # Overthinking-specific
        if "overthinking" in signals:
            interventions.append({
                "type": "prompt",
                "message": "Would you like to do an overthinking dump? Say what's on your mind.",
                "action": "overthinking_dump",
            })

        # Music suggestion
        interventions.append({
            "type": "music_suggestion",
            "query": "calm ambient meditation",
            "reason": "Calming music to reduce stress.",
        })

        # High stress: suggest professional help
        if score >= self._high_threshold and self._is_persistent_stress(profile, now):
            interventions.append({
                "type": "recommendation",
                "message": "You've been stressed for several days. Consider talking to someone you trust or a professional.",
                "priority": "high",
            })

        self._last_intervention_at = now
        self._log_intervention(profile, score, now)

        return interventions

    # ------------------------------------------------------------------
    # Signal analysis helpers
    # ------------------------------------------------------------------

    def _count_recent_overthinking(self, profile: dict, now: datetime) -> int:
        entries = profile.get("daily_life", {}).get("overthinking_entries", [])
        cutoff = (now - timedelta(hours=24)).isoformat()
        return sum(1 for e in entries if str(e.get("at", "")) >= cutoff)

    def _count_late_nights(self, profile: dict, days: int = 5) -> int:
        bed_hist = profile.get("sleep", {}).get("bedtime_history", [])
        count = 0
        for raw in bed_hist[-days:]:
            try:
                dt = datetime.fromisoformat(str(raw))
                hour = dt.hour
                if 1 <= hour <= 4:
                    count += 1
            except Exception:
                continue
        return count

    def _count_short_sleep(self, profile: dict, days: int = 5) -> int:
        bed_hist = profile.get("sleep", {}).get("bedtime_history", [])
        wake_hist = profile.get("sleep", {}).get("wake_history", [])
        pairs = min(len(bed_hist), len(wake_hist), days)
        count = 0
        for i in range(1, pairs + 1):
            try:
                bed = datetime.fromisoformat(str(bed_hist[-i]))
                wake = datetime.fromisoformat(str(wake_hist[-i]))
                if wake > bed:
                    hours = (wake - bed).total_seconds() / 3600.0
                    if 2.0 <= hours < 6.0:
                        count += 1
            except Exception:
                continue
        return count

    def _is_persistent_stress(self, profile: dict, now: datetime) -> bool:
        history = profile.get("stress", {}).get("history", [])
        cutoff = (now - timedelta(days=self._persistent_days)).date().isoformat()
        recent_high = [
            h for h in history
            if str(h.get("date", "")) >= cutoff and int(h.get("score", 0)) >= self._threshold
        ]
        unique_dates = set(str(h.get("date", "")) for h in recent_high)
        return len(unique_dates) >= self._persistent_days

    # ------------------------------------------------------------------
    # Classification & messaging
    # ------------------------------------------------------------------

    def _classify_level(self, score: int) -> str:
        if score >= self._high_threshold:
            return "high"
        if score >= self._threshold:
            return "moderate"
        if score >= 30:
            return "mild"
        return "low"

    @staticmethod
    def _build_message(score: int, level: str, persistent: bool) -> str:
        if level == "high":
            base = "Your stress level is high right now. Let's take care of you."
            if persistent:
                base += " This has been going on for a few days — please consider reaching out to someone."
            return base
        if level == "moderate":
            return "I notice some stress signals. A short breathing exercise could help."
        if level == "mild":
            return "Mild stress detected. You're doing OK, but stay mindful."
        return "Stress levels look normal. Keep up the good habits."

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _append_history(self, profile: dict, score: int, now: datetime) -> None:
        history = profile["stress"].get("history", [])
        today = now.date().isoformat()
        for h in history:
            if h.get("date") == today:
                h["score"] = max(int(h.get("score", 0)), score)
                return
        history.append({"date": today, "score": score, "timestamp": now.isoformat()})
        profile["stress"]["history"] = history[-90:]

    def _log_intervention(self, profile: dict, score: int, now: datetime) -> None:
        log = profile["stress"].get("interventions_log", [])
        log.append({"date": now.date().isoformat(), "score": score, "timestamp": now.isoformat()})
        profile["stress"]["interventions_log"] = log[-50:]
        profile["stress"]["total_interventions"] = len(log)

    def get_stats(self, profile: dict, days: int = 30) -> dict[str, Any]:
        self.ensure_shape(profile)
        history = profile["stress"].get("history", [])
        cutoff = (_utcnow() - timedelta(days=max(1, days))).date().isoformat()
        recent = [h for h in history if str(h.get("date", "")) >= cutoff]

        if not recent:
            return {"days_tracked": 0, "avg_score": 0, "high_stress_days": 0}

        scores = [int(h.get("score", 0)) for h in recent]
        return {
            "days_tracked": len(recent),
            "avg_score": round(sum(scores) / len(scores), 1),
            "max_score": max(scores),
            "high_stress_days": sum(1 for s in scores if s >= self._threshold),
            "total_interventions": int(profile["stress"].get("total_interventions", 0)),
        }
