"""Advanced pressure sensor intelligence for Smart Bed AI.

Dual-zone pressure analysis for occupancy detection, partner identification,
restlessness scoring, bed entry/exit events, and sleep position tracking.
Works without motion sensor — all intelligence derived from pressure data.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("hardware.pressure_intelligence")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OccupancyState(Enum):
    EMPTY = "empty"
    LEFT_ONLY = "left_only"
    RIGHT_ONLY = "right_only"
    BOTH = "both"
    UNCERTAIN = "uncertain"


@dataclass
class PressureSnapshot:
    left: float = 0.0
    right: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)

    @property
    def total(self) -> float:
        return self.left + self.right


@dataclass
class OccupancyEvent:
    event_type: str  # bed_entry, bed_exit, partner_arrived, partner_left
    side: str  # left, right, both
    timestamp: datetime = field(default_factory=_utcnow)
    duration_seconds: float = 0.0


class PressureIntelligence:
    """Advanced dual-zone pressure sensor analysis engine."""

    def __init__(
        self,
        *,
        occupancy_threshold_pct: float = 40.0,
        entry_rise_pct: float = 50.0,
        exit_drop_pct: float = 70.0,
        entry_window_seconds: float = 5.0,
        exit_window_seconds: float = 5.0,
        restlessness_threshold_pct: float = 10.0,
        major_movement_threshold_pct: float = 20.0,
        history_max_size: int = 7200,
        baseline_window_size: int = 120,
    ):
        self._occupancy_pct = max(10.0, float(occupancy_threshold_pct))
        self._entry_rise_pct = max(20.0, float(entry_rise_pct))
        self._exit_drop_pct = max(30.0, float(exit_drop_pct))
        self._entry_window = max(1.0, float(entry_window_seconds))
        self._exit_window = max(1.0, float(exit_window_seconds))
        self._restlessness_pct = max(3.0, float(restlessness_threshold_pct))
        self._major_pct = max(10.0, float(major_movement_threshold_pct))
        self._max_history = max(100, int(history_max_size))
        self._baseline_window = max(10, int(baseline_window_size))

        self._history: deque[PressureSnapshot] = deque(maxlen=self._max_history)
        self._events: deque[OccupancyEvent] = deque(maxlen=500)
        self._baseline_left: float = 0.0
        self._baseline_right: float = 0.0
        self._current_state = OccupancyState.EMPTY
        self._state_entered_at: datetime = _utcnow()
        self._lock = threading.Lock()

        self._on_entry_callbacks: list[Callable[[OccupancyEvent], None]] = []
        self._on_exit_callbacks: list[Callable[[OccupancyEvent], None]] = []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def on_bed_entry(self, callback: Callable[[OccupancyEvent], None]) -> None:
        if callable(callback):
            self._on_entry_callbacks.append(callback)

    def on_bed_exit(self, callback: Callable[[OccupancyEvent], None]) -> None:
        if callable(callback):
            self._on_exit_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def record(self, left: float, right: float, timestamp: datetime | None = None) -> None:
        """Record a dual-zone pressure reading."""
        snap = PressureSnapshot(
            left=float(left), right=float(right), timestamp=timestamp or _utcnow()
        )
        with self._lock:
            self._history.append(snap)
            self._update_baselines()
            self._evaluate_state_change(snap)

    def record_single(
        self, value: float, side: str = "left", timestamp: datetime | None = None
    ) -> None:
        """Record a single-sensor reading (maps to one side, other side = 0)."""
        if side == "right":
            self.record(left=0.0, right=float(value), timestamp=timestamp)
        else:
            self.record(left=float(value), right=0.0, timestamp=timestamp)

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_occupancy_state(self) -> OccupancyState:
        return self._current_state

    def get_occupancy_dict(self) -> dict[str, Any]:
        with self._lock:
            now = _utcnow()
            duration = (now - self._state_entered_at).total_seconds()
            last = self._history[-1] if self._history else PressureSnapshot()
            return {
                "state": self._current_state.value,
                "left_pressure": round(last.left, 2),
                "right_pressure": round(last.right, 2),
                "baseline_left": round(self._baseline_left, 2),
                "baseline_right": round(self._baseline_right, 2),
                "state_duration_seconds": round(duration, 1),
                "readings_count": len(self._history),
                "left_occupied": self._is_side_occupied(last.left, self._baseline_left),
                "right_occupied": self._is_side_occupied(last.right, self._baseline_right),
            }

    def get_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)[-max(1, limit) :]
        return [
            {
                "event_type": e.event_type,
                "side": e.side,
                "timestamp": e.timestamp.isoformat(),
                "duration_seconds": round(e.duration_seconds, 1),
            }
            for e in events
        ]

    def is_bed_occupied(self) -> bool:
        return self._current_state not in (OccupancyState.EMPTY, OccupancyState.UNCERTAIN)

    def is_partner_present(self) -> bool:
        return self._current_state == OccupancyState.BOTH

    def which_side_occupied(self) -> str:
        state = self._current_state
        if state == OccupancyState.LEFT_ONLY:
            return "left"
        if state == OccupancyState.RIGHT_ONLY:
            return "right"
        if state == OccupancyState.BOTH:
            return "both"
        return "none"

    # ------------------------------------------------------------------
    # Restlessness analysis
    # ------------------------------------------------------------------

    def get_restlessness_score(
        self, window_minutes: int = 60, side: str = "both"
    ) -> dict[str, Any]:
        """Calculate restlessness events per hour for a given window."""
        with self._lock:
            now = _utcnow()
            cutoff = now - timedelta(minutes=max(1, window_minutes))
            recent = [s for s in self._history if s.timestamp >= cutoff]

        if len(recent) < 10:
            return {"score": 0.0, "events": 0, "quality": "unknown", "message": "Not enough data."}

        events = 0
        for i in range(1, len(recent)):
            prev = recent[i - 1]
            curr = recent[i]

            if side in ("left", "both") and self._baseline_left > 0:
                left_change = abs(curr.left - prev.left) / self._baseline_left * 100.0
                if left_change >= self._restlessness_pct:
                    events += 1

            if side in ("right", "both") and self._baseline_right > 0:
                right_change = abs(curr.right - prev.right) / self._baseline_right * 100.0
                if right_change >= self._restlessness_pct:
                    events += 1

        hours = max(0.01, window_minutes / 60.0)
        per_hour = round(events / hours, 2)

        if per_hour < 3:
            quality = "deep_sleep"
        elif per_hour < 8:
            quality = "normal"
        elif per_hour < 15:
            quality = "light_sleep"
        else:
            quality = "restless"

        return {
            "score": per_hour,
            "events": events,
            "window_minutes": window_minutes,
            "quality": quality,
            "side": side,
        }

    def get_movement_summary(self, hours: int = 8) -> dict[str, Any]:
        """Summarize movements detected over a period (for sleep quality)."""
        with self._lock:
            cutoff = _utcnow() - timedelta(hours=max(1, hours))
            recent = [s for s in self._history if s.timestamp >= cutoff]

        if len(recent) < 20:
            return {"micro_movements": 0, "major_movements": 0, "position_changes": 0}

        micro = 0
        major = 0
        position_changes = 0

        for i in range(1, len(recent)):
            prev = recent[i - 1]
            curr = recent[i]
            total_prev = max(0.01, prev.total)
            total_change_pct = abs(curr.total - prev.total) / total_prev * 100.0

            if self._restlessness_pct <= total_change_pct < self._major_pct:
                micro += 1
            elif total_change_pct >= self._major_pct:
                major += 1

            if prev.left > prev.right and curr.right > curr.left:
                position_changes += 1
            elif prev.right > prev.left and curr.left > curr.right:
                position_changes += 1

        return {
            "micro_movements": micro,
            "major_movements": major,
            "position_changes": position_changes,
            "period_hours": hours,
            "total_readings": len(recent),
        }

    # ------------------------------------------------------------------
    # Absence detection
    # ------------------------------------------------------------------

    def get_absence_duration_seconds(self) -> float:
        """Return seconds since bed became empty. 0 if occupied."""
        if self._current_state != OccupancyState.EMPTY:
            return 0.0
        return (_utcnow() - self._state_entered_at).total_seconds()

    def is_extended_absence(self, threshold_hours: float = 72.0) -> bool:
        """Check if bed has been empty for longer than threshold."""
        return self.get_absence_duration_seconds() >= threshold_hours * 3600.0

    def is_bathroom_trip(self, max_minutes: float = 10.0) -> bool:
        """Detect short absence consistent with bathroom trip during night."""
        if self._current_state != OccupancyState.EMPTY:
            return False
        now = _utcnow()
        absence = (now - self._state_entered_at).total_seconds() / 60.0
        is_night = now.hour >= 22 or now.hour <= 6
        return is_night and 0 < absence <= max_minutes

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------

    def _update_baselines(self) -> None:
        recent = list(self._history)[-self._baseline_window :]
        if len(recent) < 5:
            return
        left_vals = [s.left for s in recent if s.left > 0]
        right_vals = [s.right for s in recent if s.right > 0]
        if left_vals:
            self._baseline_left = sum(left_vals) / len(left_vals)
        if right_vals:
            self._baseline_right = sum(right_vals) / len(right_vals)

    def _is_side_occupied(self, value: float, baseline: float) -> bool:
        if baseline <= 0:
            return value > 0
        return (value / baseline * 100.0) >= self._occupancy_pct

    def _evaluate_state_change(self, snap: PressureSnapshot) -> None:
        left_occ = self._is_side_occupied(snap.left, self._baseline_left)
        right_occ = self._is_side_occupied(snap.right, self._baseline_right)

        if left_occ and right_occ:
            new_state = OccupancyState.BOTH
        elif left_occ:
            new_state = OccupancyState.LEFT_ONLY
        elif right_occ:
            new_state = OccupancyState.RIGHT_ONLY
        else:
            new_state = OccupancyState.EMPTY

        if new_state == self._current_state:
            return

        old_state = self._current_state
        now = snap.timestamp
        duration = (now - self._state_entered_at).total_seconds()

        event = self._classify_transition(old_state, new_state, now, duration)
        if event:
            self._events.append(event)
            self._fire_callbacks(event)

        self._current_state = new_state
        self._state_entered_at = now
        logger.info("Occupancy: %s -> %s (after %.0fs)", old_state.value, new_state.value, duration)

    def _classify_transition(
        self, old: OccupancyState, new: OccupancyState, ts: datetime, duration: float
    ) -> OccupancyEvent | None:
        if old == OccupancyState.EMPTY and new != OccupancyState.EMPTY:
            side = (
                "left"
                if new == OccupancyState.LEFT_ONLY
                else ("right" if new == OccupancyState.RIGHT_ONLY else "both")
            )
            return OccupancyEvent(event_type="bed_entry", side=side, timestamp=ts)

        if old != OccupancyState.EMPTY and new == OccupancyState.EMPTY:
            side = (
                "left"
                if old == OccupancyState.LEFT_ONLY
                else ("right" if old == OccupancyState.RIGHT_ONLY else "both")
            )
            return OccupancyEvent(
                event_type="bed_exit", side=side, timestamp=ts, duration_seconds=duration
            )

        if (
            old in (OccupancyState.LEFT_ONLY, OccupancyState.RIGHT_ONLY)
            and new == OccupancyState.BOTH
        ):
            arriving = "right" if old == OccupancyState.LEFT_ONLY else "left"
            return OccupancyEvent(event_type="partner_arrived", side=arriving, timestamp=ts)

        if old == OccupancyState.BOTH and new in (
            OccupancyState.LEFT_ONLY,
            OccupancyState.RIGHT_ONLY,
        ):
            leaving = "right" if new == OccupancyState.LEFT_ONLY else "left"
            return OccupancyEvent(
                event_type="partner_left", side=leaving, timestamp=ts, duration_seconds=duration
            )

        return None

    def _fire_callbacks(self, event: OccupancyEvent) -> None:
        callbacks = (
            self._on_entry_callbacks
            if event.event_type in ("bed_entry", "partner_arrived")
            else self._on_exit_callbacks
        )
        for cb in callbacks:
            try:
                cb(event)
            except Exception as exc:
                logger.error("Pressure callback error: %s", exc)
