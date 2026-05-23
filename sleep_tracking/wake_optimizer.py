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

try:
    import antropy as ant
    _ANTROPY_AVAILABLE = True
except ImportError:
    ant = None  # type: ignore[assignment]
    _ANTROPY_AVAILABLE = False


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

        # HRV data for recovery-quality scoring (RMSSD in ms)
        self._hrv_readings: list[float] = []

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
                "signal_complexity": self.get_signal_complexity(),
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
        """Estimate sleep quality from pressure data collected overnight.

        When antropy is available the estimate is refined with signal entropy:
        low-entropy (regular) pressure patterns indicate deeper, more restorative
        sleep; high entropy indicates fragmented or light sleep.
        """
        readings = list(self._readings)
        if len(readings) < 30:
            return {"quality": "unknown", "message": "Not enough pressure data."}

        total_hours = (readings[-1].timestamp - readings[0].timestamp).total_seconds() / 3600.0
        if total_hours < 1.0:
            return {"quality": "unknown", "message": "Monitoring period too short."}

        restlessness_per_hour = self.get_restlessness_score(int(total_hours * 60))

        # Base score from restlessness event frequency.
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

        complexity = self.get_signal_complexity()
        entropy_penalty = 0
        if complexity.get("available"):
            perm_e = complexity["perm_entropy"]
            # perm_entropy is normalised [0,1]; >0.85 indicates fragmented signal.
            if perm_e > 0.85:
                entropy_penalty = 10
            elif perm_e > 0.75:
                entropy_penalty = 5
            # Upgrade "moderate" to "light" when signal entropy is high.
            if entropy_penalty >= 10 and quality == "moderate":
                quality = "light"

        # Blend in HRV quality score when data is available (weighted 40% HRV / 60% pressure)
        hrv_result = self.get_hrv_quality_score()
        pressure_score = max(0, score - entropy_penalty)
        if hrv_result.get("available"):
            hrv_score = hrv_result["score"]
            blended_score = int(pressure_score * 0.6 + hrv_score * 0.4)
            if hrv_result["recovery_rating"] in ("poor", "below_average") and quality == "moderate":
                quality = "light"
        else:
            blended_score = pressure_score
            hrv_result = None

        return {
            "quality": quality,
            "estimated_score": blended_score,
            "pressure_score": pressure_score,
            "restlessness_per_hour": restlessness_per_hour,
            "monitoring_hours": round(total_hours, 2),
            "total_readings": len(readings),
            "signal_complexity": complexity,
            "hrv_quality": hrv_result,
        }

    def record_hrv_reading(self, rmssd_ms: float) -> None:
        """Record an HRV RMSSD measurement in milliseconds.

        RMSSD (Root Mean Square of Successive Differences) is the primary
        time-domain metric for autonomic recovery.  Normal overnight RMSSD
        in healthy adults is 30-100 ms.
        """
        value = float(rmssd_ms)
        if value > 0:
            with self._lock:
                self._hrv_readings.append(value)
                # Keep only the last 24 hours of readings (avoid unbounded growth)
                if len(self._hrv_readings) > 1000:
                    self._hrv_readings = self._hrv_readings[-1000:]

    def get_hrv_quality_score(self) -> dict[str, Any]:
        """Derive a sleep quality score from nightly HRV RMSSD values.

        Scoring rubric (evidence-based thresholds from peer-reviewed literature):
        ≥ 60 ms  → excellent recovery (score 90-100)
        40-59 ms → good recovery     (score 70-89)
        25-39 ms → moderate recovery (score 50-69)
        15-24 ms → below-average     (score 30-49)
        < 15 ms  → poor recovery     (score 0-29)

        Returns
        -------
        dict with keys: available, avg_rmssd, min_rmssd, max_rmssd, score,
                        recovery_rating, recommendation, n_readings.
        """
        with self._lock:
            readings = list(self._hrv_readings)

        if not readings:
            return {
                "available": False,
                "reason": "No HRV data recorded yet. Call record_hrv_reading() with RMSSD values.",
            }

        arr = np.asarray(readings, dtype=float)
        avg_rmssd = float(arr.mean())
        min_rmssd = float(arr.min())
        max_rmssd = float(arr.max())
        trend = "stable"
        if len(readings) >= 4:
            mid = len(readings) // 2
            first_half = float(arr[:mid].mean())
            second_half = float(arr[mid:].mean())
            if second_half > first_half + 3.0:
                trend = "improving"
            elif second_half < first_half - 3.0:
                trend = "declining"

        # Map RMSSD to 0-100 score
        if avg_rmssd >= 60:
            score = min(100, int(90 + (avg_rmssd - 60) / 4))
            rating = "excellent"
            recommendation = "Excellent HRV recovery. Your autonomic nervous system is well-rested."
        elif avg_rmssd >= 40:
            score = int(70 + (avg_rmssd - 40) / 2)
            rating = "good"
            recommendation = "Good HRV recovery. Maintain consistent sleep schedule for further improvement."
        elif avg_rmssd >= 25:
            score = int(50 + (avg_rmssd - 25) / 1.5)
            rating = "moderate"
            recommendation = "Moderate HRV. Consider earlier bedtime and reducing evening stress."
        elif avg_rmssd >= 15:
            score = int(30 + (avg_rmssd - 15) / 1)
            rating = "below_average"
            recommendation = "Below-average HRV. Prioritize sleep consistency, avoid alcohol and late screens."
        else:
            score = max(0, int(avg_rmssd * 2))
            rating = "poor"
            recommendation = "Poor HRV recovery. Consult a physician if this persists. Prioritize sleep hygiene."

        return {
            "available": True,
            "avg_rmssd_ms": round(avg_rmssd, 1),
            "min_rmssd_ms": round(min_rmssd, 1),
            "max_rmssd_ms": round(max_rmssd, 1),
            "score": max(0, min(100, score)),
            "recovery_rating": rating,
            "trend": trend,
            "recommendation": recommendation,
            "n_readings": len(readings),
        }

    def get_signal_complexity(self, window: int = 512) -> dict[str, Any]:
        """Compute entropy-based complexity metrics on recent pressure readings.

        Uses the last *window* samples for efficiency.  Returns a dict with:
        - available (bool): False when antropy is not installed or data is too short.
        - sample_entropy (float): regularity measure; low = more regular = deeper sleep.
        - perm_entropy (float): normalised permutation entropy in [0, 1].
        - svd_entropy (float): singular-value entropy of the signal.
        - num_zerocross (int): zero-crossings of the mean-centred signal.
        - complexity_label (str): 'low' | 'medium' | 'high'.
        """
        if not _ANTROPY_AVAILABLE:
            return {"available": False, "reason": "antropy not installed"}

        readings = list(self._readings)
        if len(readings) < 20:
            return {"available": False, "reason": "insufficient data"}

        values = np.array([r.value for r in readings[-window:]], dtype=np.float64)
        std = values.std()
        if std < 1e-9:
            return {"available": False, "reason": "signal is constant"}

        # Normalise so entropy measures are scale-independent.
        signal = (values - values.mean()) / std

        try:
            samp_e = float(ant.sample_entropy(signal))
            perm_e = float(ant.perm_entropy(signal, normalize=True))
            svd_e = float(ant.svd_entropy(signal, normalize=True))
            zerocross = int(ant.num_zerocross(signal))
        except Exception as exc:
            logger.debug("antropy computation error: {}", exc)
            return {"available": False, "reason": str(exc)}

        # Map to a coarse label for easy downstream consumption.
        if perm_e < 0.6:
            label = "low"
        elif perm_e < 0.78:
            label = "medium"
        else:
            label = "high"

        return {
            "available": True,
            "sample_entropy": round(samp_e, 4),
            "perm_entropy": round(perm_e, 4),
            "svd_entropy": round(svd_e, 4),
            "num_zerocross": zerocross,
            "complexity_label": label,
            "window_samples": len(signal),
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
