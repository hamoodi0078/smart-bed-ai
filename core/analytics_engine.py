"""Event tracking and analytics engine for Smart Bed AI runtime.

Records user interactions, automation triggers, scene activations, sleep events,
and feature usage. Provides queries for engagement scoring, trend analysis,
and weekly/monthly analytics summaries.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.analytics_engine")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalyticsEngine:
    """Lightweight event analytics with file-backed persistence."""

    EVENT_TYPES = {
        "scene_activated",
        "automation_triggered",
        "automation_accepted",
        "automation_declined",
        "voice_command",
        "sleep_session_start",
        "sleep_session_end",
        "prayer_reminder_sent",
        "prayer_reminder_acknowledged",
        "wind_down_started",
        "wind_down_completed",
        "alarm_triggered",
        "alarm_snoozed",
        "alarm_dismissed",
        "breathing_exercise_started",
        "breathing_exercise_completed",
        "mood_logged",
        "feature_used",
        "notification_sent",
        "notification_opened",
        "app_opened",
        "bed_entry",
        "bed_exit",
        "nap_detected",
        "guest_mode_activated",
        "guest_mode_deactivated",
        "partner_detected",
        "achievement_unlocked",
        "subscription_event",
        "error_occurred",
        "health_check_alert",
        "backup_completed",
    }

    def __init__(self, *, data_dir: Path, max_events_in_memory: int = 5000):
        self._data_dir = Path(data_dir).resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._data_dir / "analytics_events.json"
        self._summary_path = self._data_dir / "analytics_summary.json"
        self._max_memory = max(500, int(max_events_in_memory))
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._load_events()

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def track(
        self,
        event_type: str,
        *,
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an analytics event. Returns the event dict."""
        event = {
            "event_type": str(event_type or "unknown").strip(),
            "user_id": str(user_id or "").strip(),
            "timestamp": _utcnow().isoformat(),
            "metadata": dict(metadata) if isinstance(metadata, dict) else {},
        }
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_memory:
                self._events = self._events[-self._max_memory:]
            self._persist_events()
        return event

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_events(
        self,
        *,
        event_type: str = "",
        user_id: str = "",
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query events with optional filters."""
        with self._lock:
            results = list(self._events)

        if event_type:
            results = [e for e in results if e.get("event_type") == event_type]
        if user_id:
            results = [e for e in results if e.get("user_id") == user_id]
        if since:
            since_iso = since.isoformat() if since.tzinfo else since.replace(tzinfo=timezone.utc).isoformat()
            results = [e for e in results if str(e.get("timestamp", "")) >= since_iso]

        return results[-max(1, int(limit)):]

    def count_events(
        self,
        event_type: str,
        *,
        user_id: str = "",
        days: int = 7,
    ) -> int:
        """Count events of a given type within the last N days."""
        since = _utcnow() - timedelta(days=max(1, days))
        events = self.get_events(event_type=event_type, user_id=user_id, since=since, limit=99999)
        return len(events)

    def events_by_type(self, *, user_id: str = "", days: int = 7) -> dict[str, int]:
        """Return event counts grouped by type within the last N days."""
        since = _utcnow() - timedelta(days=max(1, days))
        events = self.get_events(user_id=user_id, since=since, limit=99999)
        counts: dict[str, int] = defaultdict(int)
        for e in events:
            counts[str(e.get("event_type", "unknown"))] += 1
        return dict(counts)

    def events_by_hour(self, *, user_id: str = "", days: int = 7) -> dict[int, int]:
        """Return event counts grouped by hour of day."""
        since = _utcnow() - timedelta(days=max(1, days))
        events = self.get_events(user_id=user_id, since=since, limit=99999)
        counts: dict[int, int] = defaultdict(int)
        for e in events:
            try:
                ts = datetime.fromisoformat(str(e.get("timestamp", "")))
                counts[ts.hour] += 1
            except Exception:
                pass
        return dict(counts)

    def daily_active_events(self, *, user_id: str = "", days: int = 30) -> list[dict[str, Any]]:
        """Return daily event count for the last N days."""
        since = _utcnow() - timedelta(days=max(1, days))
        events = self.get_events(user_id=user_id, since=since, limit=99999)
        daily: dict[str, int] = defaultdict(int)
        for e in events:
            try:
                ts = datetime.fromisoformat(str(e.get("timestamp", "")))
                daily[ts.date().isoformat()] += 1
            except Exception:
                pass
        return [{"date": k, "events": v} for k, v in sorted(daily.items())]

    # ------------------------------------------------------------------
    # Engagement scoring
    # ------------------------------------------------------------------

    def calculate_engagement_score(self, user_id: str, days: int = 7) -> dict[str, Any]:
        """Calculate a 0-100 engagement score based on recent activity patterns."""
        counts = self.events_by_type(user_id=user_id, days=days)
        total_events = sum(counts.values())

        weights = {
            "sleep_session_end": 15,
            "voice_command": 10,
            "scene_activated": 8,
            "automation_accepted": 12,
            "wind_down_completed": 10,
            "prayer_reminder_acknowledged": 8,
            "breathing_exercise_completed": 10,
            "mood_logged": 5,
            "app_opened": 3,
            "bed_entry": 5,
        }

        weighted_score = 0.0
        for event_type, weight in weights.items():
            count = counts.get(event_type, 0)
            contribution = min(count * weight, weight * 3)
            weighted_score += contribution

        max_possible = sum(w * 3 for w in weights.values())
        normalized = min(100, int((weighted_score / max_possible) * 100)) if max_possible > 0 else 0

        active_days = len(set(
            datetime.fromisoformat(str(e.get("timestamp", ""))).date().isoformat()
            for e in self.get_events(user_id=user_id, since=_utcnow() - timedelta(days=days), limit=99999)
            if e.get("timestamp")
        ))

        return {
            "score": normalized,
            "total_events": total_events,
            "active_days": active_days,
            "period_days": days,
            "event_breakdown": dict(counts),
            "label": self._engagement_label(normalized),
        }

    @staticmethod
    def _engagement_label(score: int) -> str:
        if score >= 80:
            return "Highly Engaged"
        if score >= 60:
            return "Active"
        if score >= 40:
            return "Moderate"
        if score >= 20:
            return "Low"
        return "Inactive"

    # ------------------------------------------------------------------
    # Feature adoption
    # ------------------------------------------------------------------

    def feature_adoption(self, user_id: str, days: int = 30) -> dict[str, Any]:
        """Track which features the user has used."""
        feature_events = {
            "sleep_tracking": ["sleep_session_start", "sleep_session_end"],
            "voice_control": ["voice_command"],
            "scenes": ["scene_activated"],
            "automations": ["automation_triggered", "automation_accepted"],
            "wind_down": ["wind_down_started", "wind_down_completed"],
            "prayer_mode": ["prayer_reminder_sent", "prayer_reminder_acknowledged"],
            "breathing": ["breathing_exercise_started", "breathing_exercise_completed"],
            "mood_tracking": ["mood_logged"],
            "guest_mode": ["guest_mode_activated"],
            "partner_mode": ["partner_detected"],
            "nap_detection": ["nap_detected"],
        }

        counts = self.events_by_type(user_id=user_id, days=days)
        adopted: dict[str, bool] = {}
        usage: dict[str, int] = {}

        for feature, event_types in feature_events.items():
            total = sum(counts.get(et, 0) for et in event_types)
            adopted[feature] = total > 0
            usage[feature] = total

        total_features = len(feature_events)
        adopted_count = sum(1 for v in adopted.values() if v)

        return {
            "total_features": total_features,
            "adopted_count": adopted_count,
            "adoption_rate": round(adopted_count / total_features * 100, 1) if total_features > 0 else 0,
            "features": adopted,
            "usage_counts": usage,
        }

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------

    def sleep_trend(self, user_id: str, days: int = 30) -> list[dict[str, Any]]:
        """Return daily sleep session data for trend visualization."""
        since = _utcnow() - timedelta(days=max(1, days))
        events = self.get_events(event_type="sleep_session_end", user_id=user_id, since=since, limit=99999)
        trend: list[dict[str, Any]] = []
        for e in events:
            meta = e.get("metadata", {})
            try:
                ts = datetime.fromisoformat(str(e.get("timestamp", "")))
                trend.append({
                    "date": ts.date().isoformat(),
                    "sleep_score": meta.get("sleep_score"),
                    "total_hours": meta.get("total_hours"),
                    "quality_rating": meta.get("quality_rating"),
                })
            except Exception:
                pass
        return trend

    def automation_effectiveness(self, user_id: str, days: int = 30) -> dict[str, Any]:
        """Calculate automation acceptance vs decline rates."""
        accepted = self.count_events("automation_accepted", user_id=user_id, days=days)
        declined = self.count_events("automation_declined", user_id=user_id, days=days)
        triggered = self.count_events("automation_triggered", user_id=user_id, days=days)
        total_responses = accepted + declined

        return {
            "total_triggered": triggered,
            "total_accepted": accepted,
            "total_declined": declined,
            "acceptance_rate": round(accepted / total_responses * 100, 1) if total_responses > 0 else 0,
            "period_days": days,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_events(self) -> None:
        if not self._events_path.exists():
            return
        try:
            with open(self._events_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                self._events = data[-self._max_memory:]
        except (OSError, json.JSONDecodeError):
            self._events = []

    def _persist_events(self) -> None:
        try:
            with open(self._events_path, "w", encoding="utf-8") as fh:
                json.dump(self._events[-self._max_memory:], fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error("Failed to persist analytics events: %s", exc)

    def flush(self) -> None:
        """Force persist all events to disk."""
        with self._lock:
            self._persist_events()
