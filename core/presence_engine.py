"""Unified presence and context engine for Smart Bed AI.

Tracks bed occupancy states, detects context (sleeping, reading, away, etc.),
manages automatic sleep session start/stop, and triggers context-specific automations.
Built on top of PressureIntelligence for all sensor-derived state.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

logger = logging.getLogger("core.presence_engine")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContextState:
    SLEEPING = "sleeping"
    WIND_DOWN = "wind_down"
    AWAKE_IN_BED = "awake_in_bed"
    READING = "reading"
    RELAXING = "relaxing"
    AWAY = "away"
    BATHROOM_TRIP = "bathroom_trip"
    GUEST_MODE = "guest_mode"
    NAP = "nap"
    UNKNOWN = "unknown"


class PresenceEngine:
    """Manages unified presence context derived from pressure sensor and system state."""

    def __init__(
        self,
        *,
        bedtime_window_start_hour: int = 21,
        bedtime_window_end_hour: int = 6,
        nap_window_start_hour: int = 11,
        nap_window_end_hour: int = 18,
        bathroom_max_minutes: float = 10.0,
        reading_min_minutes: float = 15.0,
        extended_absence_hours: float = 72.0,
        wellness_check_hours: float = 72.0,
    ):
        self._bedtime_start = int(bedtime_window_start_hour)
        self._bedtime_end = int(bedtime_window_end_hour)
        self._nap_start = int(nap_window_start_hour)
        self._nap_end = int(nap_window_end_hour)
        self._bathroom_max = float(bathroom_max_minutes)
        self._reading_min = float(reading_min_minutes)
        self._absence_threshold = float(extended_absence_hours)
        self._wellness_hours = float(wellness_check_hours)

        self._current_context = ContextState.UNKNOWN
        self._context_entered_at: datetime = _utcnow()
        self._bed_occupied = False
        self._bed_entry_time: datetime | None = None
        self._bed_exit_time: datetime | None = None
        self._lights_on = False
        self._lights_brightness: float = 0.0
        self._music_playing = False
        self._guest_mode = False
        self._quiet_hours_active = False
        self._sleep_session_active = False
        self._last_wellness_check: datetime | None = None

        self._context_callbacks: list[Callable[[str, str, dict[str, Any]], None]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_context_change(self, callback: Callable[[str, str, dict[str, Any]], None]) -> None:
        """Register callback: (old_context, new_context, metadata)."""
        if callable(callback):
            self._context_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Signal inputs (called by other components)
    # ------------------------------------------------------------------

    def update_bed_occupancy(self, occupied: bool, side: str = "unknown") -> None:
        """Called when pressure intelligence detects bed entry/exit."""
        with self._lock:
            was_occupied = self._bed_occupied
            self._bed_occupied = bool(occupied)
            now = _utcnow()

            if occupied and not was_occupied:
                self._bed_entry_time = now
                self._bed_exit_time = None
                logger.info("Bed entry detected (side=%s)", side)
            elif not occupied and was_occupied:
                self._bed_exit_time = now
                logger.info("Bed exit detected (side=%s)", side)

            self._reevaluate_context(now)

    def update_lights(self, on: bool, brightness: float = 0.0) -> None:
        with self._lock:
            self._lights_on = bool(on)
            self._lights_brightness = float(brightness)
            self._reevaluate_context(_utcnow())

    def update_music(self, playing: bool) -> None:
        with self._lock:
            self._music_playing = bool(playing)
            self._reevaluate_context(_utcnow())

    def update_guest_mode(self, active: bool) -> None:
        with self._lock:
            self._guest_mode = bool(active)
            self._reevaluate_context(_utcnow())

    def update_quiet_hours(self, active: bool) -> None:
        with self._lock:
            self._quiet_hours_active = bool(active)

    def update_sleep_session(self, active: bool) -> None:
        with self._lock:
            self._sleep_session_active = bool(active)

    # ------------------------------------------------------------------
    # Context evaluation
    # ------------------------------------------------------------------

    def _reevaluate_context(self, now: datetime) -> None:
        new_context = self._determine_context(now)

        if new_context != self._current_context:
            old = self._current_context
            self._current_context = new_context
            self._context_entered_at = now

            metadata = {
                "bed_occupied": self._bed_occupied,
                "lights_on": self._lights_on,
                "brightness": self._lights_brightness,
                "music_playing": self._music_playing,
                "guest_mode": self._guest_mode,
                "hour": now.hour,
            }

            logger.info("Context change: %s -> %s", old, new_context)
            self._fire_callbacks(old, new_context, metadata)

    def _determine_context(self, now: datetime) -> str:
        hour = now.hour

        if self._guest_mode and self._bed_occupied:
            return ContextState.GUEST_MODE

        if not self._bed_occupied:
            if self._bed_exit_time:
                absence_minutes = (now - self._bed_exit_time).total_seconds() / 60.0
                is_night = hour >= 22 or hour <= 6
                if is_night and absence_minutes <= self._bathroom_max:
                    return ContextState.BATHROOM_TRIP
            return ContextState.AWAY

        is_bedtime_window = hour >= self._bedtime_start or hour <= self._bedtime_end
        is_nap_window = self._nap_start <= hour <= self._nap_end

        if self._bed_occupied and self._sleep_session_active:
            return ContextState.SLEEPING

        if self._bed_occupied and is_bedtime_window and not self._lights_on and not self._music_playing:
            return ContextState.SLEEPING

        if self._bed_occupied and is_bedtime_window and self._lights_on and self._lights_brightness <= 0.3:
            entry_duration = (now - self._bed_entry_time).total_seconds() / 60.0 if self._bed_entry_time else 0
            if entry_duration < 30:
                return ContextState.WIND_DOWN
            return ContextState.SLEEPING

        if self._bed_occupied and self._lights_on and self._lights_brightness > 0.2:
            if self._bed_entry_time:
                in_bed_minutes = (now - self._bed_entry_time).total_seconds() / 60.0
                if in_bed_minutes >= self._reading_min and not self._music_playing:
                    return ContextState.READING

        if self._bed_occupied and self._music_playing:
            return ContextState.RELAXING

        if self._bed_occupied and is_nap_window:
            return ContextState.NAP

        if self._bed_occupied:
            return ContextState.AWAKE_IN_BED

        return ContextState.UNKNOWN

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    def get_context(self) -> dict[str, Any]:
        with self._lock:
            now = _utcnow()
            duration = (now - self._context_entered_at).total_seconds()
            return {
                "context": self._current_context,
                "duration_seconds": round(duration, 1),
                "duration_minutes": round(duration / 60.0, 1),
                "bed_occupied": self._bed_occupied,
                "lights_on": self._lights_on,
                "brightness": self._lights_brightness,
                "music_playing": self._music_playing,
                "guest_mode": self._guest_mode,
                "sleep_session_active": self._sleep_session_active,
                "quiet_hours_active": self._quiet_hours_active,
            }

    def get_context_name(self) -> str:
        return self._current_context

    def is_sleeping(self) -> bool:
        return self._current_context == ContextState.SLEEPING

    def is_away(self) -> bool:
        return self._current_context == ContextState.AWAY

    def should_suppress_notifications(self) -> bool:
        """Return True if current context means notifications should be silenced."""
        return self._current_context in (
            ContextState.SLEEPING,
            ContextState.GUEST_MODE,
        ) or self._quiet_hours_active

    def should_auto_start_sleep_session(self) -> bool:
        """Return True if conditions indicate sleep session should start automatically."""
        if self._sleep_session_active:
            return False
        if not self._bed_occupied:
            return False
        now = _utcnow()
        hour = now.hour
        is_bedtime = hour >= self._bedtime_start or hour <= self._bedtime_end
        if not is_bedtime:
            return False
        if self._bed_entry_time:
            in_bed_minutes = (now - self._bed_entry_time).total_seconds() / 60.0
            return in_bed_minutes >= 5 and not self._lights_on
        return False

    def should_auto_end_sleep_session(self) -> bool:
        """Return True if conditions indicate sleep session should end automatically."""
        if not self._sleep_session_active:
            return False
        if self._bed_occupied:
            return False
        if not self._bed_exit_time:
            return False
        now = _utcnow()
        absence_minutes = (now - self._bed_exit_time).total_seconds() / 60.0
        hour = now.hour
        is_morning = 5 <= hour <= 12
        return is_morning and absence_minutes >= 5

    def should_send_wellness_check(self) -> bool:
        """Return True if bed has been empty long enough to send wellness check."""
        if self._bed_occupied:
            return False
        if not self._bed_exit_time:
            return False
        now = _utcnow()
        absence_hours = (now - self._bed_exit_time).total_seconds() / 3600.0
        if absence_hours < self._wellness_hours:
            return False
        if self._last_wellness_check:
            since_last = (now - self._last_wellness_check).total_seconds() / 3600.0
            if since_last < 24:
                return False
        return True

    def mark_wellness_check_sent(self) -> None:
        self._last_wellness_check = _utcnow()

    def get_automation_context(self) -> dict[str, Any]:
        """Return context dict suitable for passing to automation evaluators."""
        ctx = self.get_context()
        return {
            "presence_context": ctx["context"],
            "bed_occupied": ctx["bed_occupied"],
            "is_sleeping": self.is_sleeping(),
            "is_away": self.is_away(),
            "suppress_notifications": self.should_suppress_notifications(),
            "auto_start_sleep": self.should_auto_start_sleep_session(),
            "auto_end_sleep": self.should_auto_end_sleep_session(),
            "wellness_check_due": self.should_send_wellness_check(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fire_callbacks(self, old: str, new: str, metadata: dict[str, Any]) -> None:
        for cb in self._context_callbacks:
            try:
                cb(old, new, metadata)
            except Exception as exc:
                logger.error("Context change callback error: %s", exc)
