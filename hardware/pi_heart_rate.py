"""MAX30102 heart-rate and SpO₂ sensor driver.

Reads heart rate (BPM) and blood oxygen saturation (SpO₂ %) from a MAX30102
pulse oximeter connected to the Raspberry Pi via I²C.

Requires:
  pip install max30102 hrcalc
  I²C must be enabled on the Pi:  sudo raspi-config → Interface Options → I2C

Environment / settings used:
  SENSOR_HEART_RATE_ENABLED   (default: False)
  SENSOR_HEART_RATE_SAMPLE_COUNT (default: 100  — frames per reading batch)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("hardware.pi_heart_rate")

# Lazy-loaded sensor libraries
_max30102_mod: Any = None
_hrcalc_mod: Any = None

try:
    import max30102 as _max30102_import  # type: ignore[import-untyped]
    import hrcalc as _hrcalc_import  # type: ignore[import-untyped]

    _max30102_mod = _max30102_import
    _hrcalc_mod = _hrcalc_import
except ImportError:
    logger.debug("max30102 / hrcalc not installed — heart-rate sensor disabled.")
except Exception as _exc:
    logger.debug("Heart-rate sensor library load error: %s", _exc)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HeartRateReading:
    """A single heart-rate + SpO₂ reading."""
    heart_rate_bpm: float | None = None
    spo2_pct: float | None = None
    heart_rate_valid: bool = False
    spo2_valid: bool = False
    valid: bool = False


# ---------------------------------------------------------------------------
# Sensor monitor
# ---------------------------------------------------------------------------

class HeartRateSensorMonitor:
    """Polls a MAX30102 sensor via I²C at a configurable interval."""

    def __init__(
        self,
        *,
        sample_count: int = 100,
        poll_interval_seconds: float = 5.0,
        max_retries: int = 2,
    ):
        self._sample_count = max(25, int(sample_count))
        self._poll_interval = max(2.0, float(poll_interval_seconds))
        self._max_retries = max(1, int(max_retries))
        self._sensor: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last: HeartRateReading = HeartRateReading()
        self._status = "Heart-rate sensor not initialised."
        self._callbacks: list[Callable[[HeartRateReading], None]] = []

        if _max30102_mod is None or _hrcalc_mod is None:
            self._status = "Heart-rate sensor disabled: install max30102 and hrcalc packages."
            return

        try:
            self._sensor = _max30102_mod.MAX30102()
            self._status = "MAX30102 heart-rate sensor ready (I²C)."
            logger.info("MAX30102 initialised successfully.")
        except Exception as exc:
            self._status = f"Heart-rate sensor init failed: {exc}"
            logger.warning("MAX30102 init error: %s", exc)

    # -- Public API --------------------------------------------------------

    def is_available(self) -> bool:
        return self._sensor is not None

    def status_line(self) -> str:
        return self._status

    def read(self) -> HeartRateReading:
        """Take a single reading (blocking, may take 2-4 s)."""
        if self._sensor is None:
            return HeartRateReading()

        for attempt in range(self._max_retries):
            try:
                red, ir = self._sensor.read_sequential(self._sample_count)
                hr, hr_valid, spo2, spo2_valid = _hrcalc_mod.calc_hr_and_spo2(ir, red)
                reading = HeartRateReading(
                    heart_rate_bpm=round(float(hr), 1) if hr_valid else None,
                    spo2_pct=round(float(spo2), 1) if spo2_valid else None,
                    heart_rate_valid=bool(hr_valid),
                    spo2_valid=bool(spo2_valid),
                    valid=bool(hr_valid or spo2_valid),
                )
                with self._lock:
                    self._last = reading
                return reading

            except Exception as exc:
                logger.debug(
                    "MAX30102 read retry %d/%d: %s", attempt + 1, self._max_retries, exc
                )
                time.sleep(0.5)

        return HeartRateReading()

    @property
    def last_reading(self) -> HeartRateReading:
        with self._lock:
            return self._last

    def start(self, callback: Callable[[HeartRateReading], None] | None = None) -> None:
        """Start background polling thread."""
        if callback is not None:
            self._callbacks.append(callback)
        if self._thread is not None or self._sensor is None:
            return

        def _run() -> None:
            logger.info(
                "MAX30102 polling started (every %.1fs, %d samples/batch).",
                self._poll_interval,
                self._sample_count,
            )
            while not self._stop.is_set():
                reading = self.read()
                if reading.valid:
                    for cb in self._callbacks:
                        try:
                            cb(reading)
                        except Exception as exc:
                            logger.warning("Heart-rate callback error: %s", exc)
                self._stop.wait(self._poll_interval)

        self._thread = threading.Thread(target=_run, name="max30102-poll", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop polling and release the sensor."""
        self._stop.set()
        if self._sensor is not None:
            try:
                self._sensor.shutdown()
            except Exception:
                pass
            self._sensor = None


# ---------------------------------------------------------------------------
# Noop fallback
# ---------------------------------------------------------------------------

class NoopHeartRateMonitor:
    """Placeholder used when the real sensor is unavailable."""

    def __init__(self, reason: str = "Heart-rate sensor disabled."):
        self._reason = reason

    def is_available(self) -> bool:
        return False

    def status_line(self) -> str:
        return self._reason

    def read(self) -> HeartRateReading:
        return HeartRateReading()

    @property
    def last_reading(self) -> HeartRateReading:
        return HeartRateReading()

    def start(self, callback: Callable[[HeartRateReading], None] | None = None) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_heart_rate_monitor(settings: Any) -> HeartRateSensorMonitor | NoopHeartRateMonitor:
    """Create a heart-rate monitor from app settings.

    Expected settings attributes:
      sensor_heart_rate_enabled: bool
      sensor_heart_rate_sample_count: int   (default 100)
      sensor_heart_rate_poll_interval_seconds: float (default 5.0)
    """
    enabled = getattr(settings, "sensor_heart_rate_enabled", False)
    if not enabled:
        return NoopHeartRateMonitor("Heart-rate sensor disabled by configuration.")

    sample_count = int(getattr(settings, "sensor_heart_rate_sample_count", 100))
    interval = float(getattr(settings, "sensor_heart_rate_poll_interval_seconds", 5.0))

    monitor = HeartRateSensorMonitor(
        sample_count=sample_count,
        poll_interval_seconds=interval,
    )
    if not monitor.is_available():
        return NoopHeartRateMonitor(monitor.status_line())
    return monitor
