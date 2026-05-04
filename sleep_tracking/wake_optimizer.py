"""Pressure-sensor-based smart wake optimizer for Smart Bed AI.

Monitors pressure fluctuations before alarm time to detect light sleep phases,
then triggers gentle wake sequences during optimal windows. No motion sensor needed.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np
from loguru import logger


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PressureReading:
    """Single pressure sensor reading with timestamp."""

    __slots__ = ("value", "timestamp")

    def __init__(self, value: float, timestamp: datetime | None = None):
        self.value = float(value)
        self.timestamp = timestamp or _utcnow()


class WakeOptimizer:
    """Detects light sleep phases using pressure sensor data for optimal wake timing.

    Algorithm:
    - Collects pressure readings at regular intervals
    - Detects 'restlessness' = pressure fluctuations >threshold in a sliding window
    - Light sleep = restlessness events >2 in a 15-minute window
    - Triggers wake during detected light sleep within pre-alarm window (15-30min)
    """

    def __init__(
        self,
        *,
        pre_alarm_window_minutes: int = 30,
        min_wake_before_alarm_minutes: int = 5,
        restlessness_threshold_pct: float = 5.0,
        restlessness_window_seconds: int = 300,
        light_sleep_event_threshold: int = 2,
        light_sleep_window_minutes: int = 15,
        baseline_window_size: int = 60,
    ):
        self._pre_alarm_minutes = max(5, int(pre_alarm_window_minutes))
        self._min_before_alarm = max(2, int(min_wake_before_alarm_minutes))
        self._restlessness_pct = max(1.0, float(restlessness_threshold_pct))
        self._restlessness_window = max(60, int(restlessness_window_seconds))
        self._light_sleep_events = max(1, int(light_sleep_event_threshold))
        self._light_sleep_window = max(5, int(light_sleep_window_minutes))
        self._baseline_window = max(10, int(baseline_window_size))

        self._readings: deque[PressureReading] = deque(maxlen=3600)
        self._baseline: float = 0.0
        self._restlessness_events: deque[datetime] = deque(maxlen=200)
        self._lock = threading.Lock()
        self._alarm_time: datetime | None = None
        self._wake_triggered = False
        self._wake_callback: Callable[[], None] | None = None
        self._monitoring = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_alarm(self, alarm_time: datetime) -> None:
        """Set the next alarm time to optimize wake around."""
        with self._lock:
            if alarm_time.tzinfo is None:
                alarm_time = alarm_time.replace(tzinfo=timezone.utc)
            self._alarm_time = alarm_time
            self._wake_triggered = False
        logger.info("Wake optimizer alarm set: {}", alarm_time.isoformat())

    def set_wake_callback(self, callback: Callable[[], None]) -> None:
        """Set callback to invoke when optimal wake window is detected."""
        self._wake_callback = callback

    def clear_alarm(self) -> None:
        with self._lock:
            self._alarm_time = None
            self._wake_triggered = False

    # ------------------------------------------------------------------
    # Pressure data ingestion
    # ------------------------------------------------------------------

    def record_pressure(self, value: float, timestamp: datetime | None = None) -> None:
        """Record a pressure sensor reading."""
        reading = PressureReading(value, timestamp)
        with self._lock:
            self._readings.append(reading)
            self._update_baseline()
            self._check_restlessness(reading)
            self._evaluate_wake_window()

    def _update_baseline(self) -> None:
        """Compute rolling baseline from recent stable readings."""
        recent = list(self._readings)[-self._baseline_window:]
        if len(recent) < 5:
            return
        self._baseline = float(np.mean([r.value for r in recent]))

    def _check_restlessness(self, reading: PressureReading) -> None:
        """Detect if current reading deviates significantly from baseline."""
        if self._baseline <= 0:
            return
        deviation_pct = abs(reading.value - self._baseline) / self._baseline * 100.0
        if deviation_pct >= self._restlessness_pct:
            self._restlessness_events.append(reading.timestamp)

    def _evaluate_wake_window(self) -> None:
        """Check if we're in the pre-alarm window and light sleep is detected."""
        if self._wake_triggered or self._alarm_time is None:
            return

        now = _utcnow()
        time_to_alarm = (self._alarm_time - now).total_seconds() / 60.0

        if time_to_alarm < self._min_before_alarm or time_to_alarm > self._pre_alarm_minutes:
            return

        if self._is_light_sleep(now):
            self._wake_triggered = True
            logger.info(
                "Light sleep detected %.1f min before alarm. Triggering gentle wake.",
                time_to_alarm,
            )
            if callable(self._wake_callback):
                try:
                    self._wake_callback()
                except Exception as exc:
                    logger.error("Wake callback error: {}", exc)

    def _is_light_sleep(self, now: datetime) -> bool:
        """Check if restlessness events indicate light sleep phase."""
        window_start = now - timedelta(minutes=self._light_sleep_window)
        recent_events = [
            ts for ts in self._restlessness_events
            if ts >= window_start
        ]
        return len(recent_events) >= self._light_sleep_events

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            now = _utcnow()
            readings_count = len(self._readings)
            recent_restlessness = sum(
                1 for ts in self._restlessness_events
                if (now - ts).total_seconds() < 900
            )
            time_to_alarm = None
            if self._alarm_time:
                time_to_alarm = round((self._alarm_time - now).total_seconds() / 60.0, 1)

            return {
                "monitoring": self._monitoring,
                "alarm_set": self._alarm_time is not None,
                "alarm_time": self._alarm_time.isoformat() if self._alarm_time else None,
                "minutes_to_alarm": time_to_alarm,
                "wake_triggered": self._wake_triggered,
                "baseline_pressure": round(self._baseline, 2),
                "readings_count": readings_count,
                "recent_restlessness_events": recent_restlessness,
                "is_light_sleep": self._is_light_sleep(now),
                "in_wake_window": (
                    time_to_alarm is not None
                    and self._min_before_alarm <= time_to_alarm <= self._pre_alarm_minutes
                ),
            }

    def get_restlessness_score(self, window_minutes: int = 60) -> float:
        """Return restlessness events per hour for the given window."""
        now = _utcnow()
        window_start = now - timedelta(minutes=max(1, window_minutes))
        events = np.asarray(list(self._restlessness_events))
        count = int(np.sum(events >= window_start)) if events.size > 0 else 0
        hours = max(0.01, window_minutes / 60.0)
        return round(count / hours, 2)

    def get_sleep_quality_estimate(self) -> dict[str, Any]:
        """Estimate sleep quality from pressure data collected overnight."""
        now = _utcnow()
        readings = list(self._readings)
        if len(readings) < 30:
            return {"quality": "unknown", "message": "Not enough pressure data."}

        total_hours = (readings[-1].timestamp - readings[0].timestamp).total_seconds() / 3600.0
        if total_hours < 1.0:
            return {"quality": "unknown", "message": "Monitoring period too short."}

        restlessness_per_hour = self.get_restlessness_score(int(total_hours * 60))

        if restlessness_per_hour < 3:
            quality = "deep"
            score = 90
        elif restlessness_per_hour < 8:
            quality = "moderate"
            score = 70
        elif restlessness_per_hour < 15:
            quality = "light"
            score = 50
        else:
            quality = "restless"
            score = 30

        return {
            "quality": quality,
            "estimated_score": score,
            "restlessness_per_hour": restlessness_per_hour,
            "monitoring_hours": round(total_hours, 2),
            "total_readings": len(readings),
        }

    # ------------------------------------------------------------------
    # Progressive wake sequence definition
    # ------------------------------------------------------------------

    @staticmethod
    def get_wake_sequence(alarm_time: datetime) -> list[dict[str, Any]]:
        """Return the progressive wake sequence steps with absolute times."""
        steps = [
            {
                "phase": "dream_awareness",
                "offset_minutes": -15,
                "led_brightness": 0.03,
                "led_color": "#FFB347",
                "sound_volume": 0.1,
                "sound_type": "nature_ambient",
                "description": "Ultra-dim amber glow with barely audible nature sounds",
            },
            {
                "phase": "gentle_approach",
                "offset_minutes": -10,
                "led_brightness": 0.10,
                "led_color": "#FFDAB9",
                "sound_volume": 0.3,
                "sound_type": "birds_chirping",
                "description": "Warm peach sunrise simulation with bird sounds",
            },
            {
                "phase": "morning_embrace",
                "offset_minutes": -5,
                "led_brightness": 0.30,
                "led_color": "#FFF8DC",
                "sound_volume": 0.5,
                "sound_type": "gentle_stream",
                "description": "Soft yellow-white with gentle stream and birds",
            },
            {
                "phase": "awakening",
                "offset_minutes": -2,
                "led_brightness": 0.60,
                "led_color": "#FFFACD",
                "sound_volume": 0.7,
                "sound_type": "morning_instrumental",
                "description": "Bright warm white with uplifting instrumental",
            },
            {
                "phase": "full_wake",
                "offset_minutes": 0,
                "led_brightness": 0.80,
                "led_color": "#F5F5F5",
                "sound_volume": 0.9,
                "sound_type": "morning_energy",
                "description": "Energizing cool white with morning greeting",
            },
        ]

        for step in steps:
            offset = timedelta(minutes=step["offset_minutes"])
            step["trigger_time"] = (alarm_time + offset).isoformat()

        return steps

    # ------------------------------------------------------------------
    # Background monitoring
    # ------------------------------------------------------------------

    def start_monitoring(self, pressure_read_fn: Callable[[], float], poll_seconds: float = 5.0) -> None:
        """Start continuous pressure monitoring in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._monitoring = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            args=(pressure_read_fn, max(1.0, poll_seconds)),
            daemon=True,
            name="wake_optimizer_monitor",
        )
        self._thread.start()

    def stop_monitoring(self) -> None:
        self._monitoring = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def _monitor_loop(self, read_fn: Callable[[], float], interval: float) -> None:
        while not self._stop_event.is_set():
            try:
                value = read_fn()
                self.record_pressure(value)
            except Exception as exc:
                logger.error("Pressure read error: {}", exc)
            self._stop_event.wait(timeout=interval)
        self._monitoring = False
