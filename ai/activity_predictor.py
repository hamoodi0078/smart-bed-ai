"""Activity pattern learning and prediction for Smart Bed AI.

Learns user activity patterns (reading, napping, praying, relaxing) based on
time-of-day and day-of-week, predicts upcoming activities, and auto-suggests
appropriate scenes when confidence exceeds threshold.
"""

from __future__ import annotations

from loguru import logger
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


ACTIVITY_SCENES = {
    "reading": {
        "color": "#FFF8DC",
        "brightness": 0.40,
        "animation": "solid",
        "name": "Reading Mode",
    },
    "nap": {"color": "#FF8C00", "brightness": 0.05, "animation": "breathing", "name": "Nap Mode"},
    "prayer": {
        "color": "#FFF5E0",
        "brightness": 0.15,
        "animation": "gentle_pulse",
        "name": "Prayer Mode",
    },
    "relaxing": {
        "color": "#00CED1",
        "brightness": 0.15,
        "animation": "slow_pulse",
        "name": "Relaxation",
    },
    "focus": {"color": "#90EE90", "brightness": 0.50, "animation": "solid", "name": "Focus Mode"},
    "meditation": {
        "color": "#E6E6FA",
        "brightness": 0.10,
        "animation": "breathing",
        "name": "Meditation",
    },
    "wind_down": {
        "color": "#FFC87C",
        "brightness": 0.20,
        "animation": "breathing",
        "name": "Wind Down",
    },
}

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ActivityPredictor:
    """Learns and predicts user activity patterns for proactive scene suggestions."""

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.65,
        auto_activate_threshold: float = 0.85,
        min_observations: int = 3,
        learning_window_weeks: int = 4,
        prediction_window_minutes: int = 15,
    ):
        self._confidence_threshold = max(0.3, min(1.0, float(confidence_threshold)))
        self._auto_threshold = max(self._confidence_threshold + 0.1, float(auto_activate_threshold))
        self._min_obs = max(2, int(min_observations))
        self._learning_weeks = max(1, int(learning_window_weeks))
        self._prediction_window = max(5, int(prediction_window_minutes))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("activity_patterns", {})
        ap = profile["activity_patterns"]
        ap.setdefault("observations", [])
        ap.setdefault("predictions_accepted", 0)
        ap.setdefault("predictions_declined", 0)
        ap.setdefault("auto_activated_count", 0)

    # ------------------------------------------------------------------
    # Observation recording
    # ------------------------------------------------------------------

    def record_activity(
        self, profile: dict, activity: str, now: datetime | None = None, duration_minutes: float = 0
    ) -> dict[str, Any]:
        """Record an observed activity with time context."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        ap = profile["activity_patterns"]

        observation = {
            "activity": str(activity).strip().lower(),
            "hour": now.hour,
            "minute": now.minute,
            "weekday": now.weekday(),
            "date": now.date().isoformat(),
            "timestamp": now.isoformat(),
            "duration_minutes": round(float(duration_minutes), 1),
        }

        ap["observations"].append(observation)
        cutoff_dt = now - timedelta(weeks=self._learning_weeks)

        def _parse_ts(s: str) -> datetime | None:
            try:
                dt = datetime.fromisoformat(str(s or ""))
                return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
            except Exception:
                return None

        cutoff_naive = cutoff_dt.replace(tzinfo=None) if cutoff_dt.tzinfo is not None else cutoff_dt
        ap["observations"] = [
            o
            for o in ap["observations"]
            if (ts := _parse_ts(o.get("timestamp", ""))) is not None and ts >= cutoff_naive
        ]
        ap["observations"] = ap["observations"][-500:]

        return {
            "recorded": True,
            "activity": observation["activity"],
            "observations_total": len(ap["observations"]),
        }

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Predict the most likely activity for the current time slot."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        ap = profile["activity_patterns"]
        observations = ap.get("observations", [])

        if len(observations) < self._min_obs:
            return {"prediction": None, "confidence": 0, "reason": "Not enough observations yet."}

        hour = now.hour
        weekday = now.weekday()
        slot_start = hour * 60 + now.minute - self._prediction_window
        slot_end = hour * 60 + now.minute + self._prediction_window

        matches: list[dict] = []
        for obs in observations:
            obs_minutes = int(obs.get("hour", 0)) * 60 + int(obs.get("minute", 0))
            obs_weekday = int(obs.get("weekday", -1))

            time_match = slot_start <= obs_minutes <= slot_end
            day_match = obs_weekday == weekday

            if time_match:
                weight = 2.0 if day_match else 1.0
                matches.append({"activity": obs.get("activity", ""), "weight": weight})

        if not matches:
            return {"prediction": None, "confidence": 0, "reason": "No matching patterns found."}

        activity_scores: dict[str, float] = defaultdict(float)
        for m in matches:
            activity_scores[m["activity"]] += m["weight"]

        total_weight = sum(activity_scores.values())
        best_activity = max(activity_scores, key=activity_scores.get)
        confidence = activity_scores[best_activity] / total_weight if total_weight > 0 else 0

        scene = ACTIVITY_SCENES.get(best_activity)
        should_suggest = confidence >= self._confidence_threshold and len(matches) >= self._min_obs
        should_auto = confidence >= self._auto_threshold and len(matches) >= self._min_obs * 2

        result: dict[str, Any] = {
            "prediction": best_activity,
            "confidence": round(confidence, 3),
            "observations_matched": len(matches),
            "should_suggest": should_suggest,
            "should_auto_activate": should_auto,
            "day": WEEKDAY_NAMES[weekday],
            "time_slot": f"{hour:02d}:{now.minute:02d}",
        }

        if should_suggest and scene:
            result["suggested_scene"] = {
                "activity": best_activity,
                "scene_name": scene["name"],
                "color": scene["color"],
                "brightness": scene["brightness"],
                "animation": scene["animation"],
            }
            if should_auto:
                result["message"] = (
                    f"Auto-activating {scene['name']} (confidence {confidence:.0%})."
                )
            else:
                result["message"] = f"Ready for {scene['name']}? (based on your usual pattern)"

        return result

    def record_prediction_response(self, profile: dict, accepted: bool) -> None:
        """Record whether user accepted or declined a prediction."""
        self.ensure_shape(profile)
        ap = profile["activity_patterns"]
        if accepted:
            ap["predictions_accepted"] = int(ap.get("predictions_accepted", 0)) + 1
        else:
            ap["predictions_declined"] = int(ap.get("predictions_declined", 0)) + 1

    # ------------------------------------------------------------------
    # Pattern analysis
    # ------------------------------------------------------------------

    def get_patterns(self, profile: dict) -> list[dict[str, Any]]:
        """Return discovered activity patterns sorted by frequency."""
        self.ensure_shape(profile)
        observations = profile["activity_patterns"].get("observations", [])

        pattern_counts: dict[str, dict[str, Any]] = {}
        for obs in observations:
            activity = str(obs.get("activity", "")).strip()
            hour = int(obs.get("hour", 0))
            weekday = int(obs.get("weekday", 0))
            key = f"{activity}:{hour}:{weekday}"

            if key not in pattern_counts:
                pattern_counts[key] = {
                    "activity": activity,
                    "hour": hour,
                    "weekday": weekday,
                    "day_name": WEEKDAY_NAMES[weekday] if 0 <= weekday <= 6 else "?",
                    "count": 0,
                    "avg_duration": 0,
                    "durations": [],
                }
            pattern_counts[key]["count"] += 1
            dur = float(obs.get("duration_minutes", 0))
            if dur > 0:
                pattern_counts[key]["durations"].append(dur)

        patterns = []
        for p in pattern_counts.values():
            durations = p.pop("durations", [])
            if durations:
                p["avg_duration_minutes"] = round(sum(durations) / len(durations), 1)
            else:
                p["avg_duration_minutes"] = 0
            patterns.append(p)

        patterns.sort(key=lambda x: x["count"], reverse=True)
        return patterns[:20]

    def get_stats(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        ap = profile["activity_patterns"]
        observations = ap.get("observations", [])
        accepted = int(ap.get("predictions_accepted", 0))
        declined = int(ap.get("predictions_declined", 0))
        total_responses = accepted + declined

        activities = set(str(o.get("activity", "")) for o in observations)

        return {
            "total_observations": len(observations),
            "unique_activities": len(activities),
            "activities_list": sorted(activities),
            "predictions_accepted": accepted,
            "predictions_declined": declined,
            "acceptance_rate": round(accepted / total_responses * 100, 1)
            if total_responses > 0
            else 0,
            "auto_activated": int(ap.get("auto_activated_count", 0)),
            "discovered_patterns": len(self.get_patterns(profile)),
        }
