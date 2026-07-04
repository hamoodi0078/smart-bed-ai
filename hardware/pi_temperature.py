"""AM2301A (DHT22) temperature and humidity sensor driver.

Reads temperature (°C) and relative humidity (%) from an AM2301A / DHT22
sensor connected to a Raspberry Pi GPIO pin.

Requires:
  pip install adafruit-circuitpython-dht
  sudo apt-get install libgpiod2

The sensor sometimes returns transient read errors — this is normal.  The
driver retries automatically and returns ``None`` when no valid reading is
available.

Environment / settings used:
  SENSOR_TEMPERATURE_PIN  (default: GPIO 4)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("hardware.pi_temperature")

# Lazy-loaded sensor library — not available on non-Pi environments
_adafruit_dht: Any = None
_board: Any = None

try:
    import adafruit_dht  # type: ignore[import-untyped]
    import board as _board_module  # type: ignore[import-untyped]

    _adafruit_dht = adafruit_dht
    _board = _board_module
except ImportError:
    logger.debug("adafruit-circuitpython-dht not installed — temperature sensor disabled.")
except Exception as _exc:
    logger.debug("Temperature sensor library load error: %s", _exc)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemperatureReading:
    """A single temperature + humidity reading."""

    temperature_c: float | None = None
    humidity_pct: float | None = None
    valid: bool = False


# ---------------------------------------------------------------------------
# GPIO pin helper
# ---------------------------------------------------------------------------

_PIN_MAP: dict[int, Any] = {}


def _board_pin(gpio_number: int) -> Any:
    """Resolve a BCM GPIO number to a ``board`` pin object."""
    if gpio_number in _PIN_MAP:
        return _PIN_MAP[gpio_number]
    if _board is None:
        return None
    pin = getattr(_board, f"D{gpio_number}", None)
    if pin is not None:
        _PIN_MAP[gpio_number] = pin
    return pin


# ---------------------------------------------------------------------------
# Sensor monitor
# ---------------------------------------------------------------------------


class TemperatureSensorMonitor:
    """Polls an AM2301A / DHT22 sensor at a configurable interval."""

    def __init__(
        self,
        *,
        gpio_pin: int = 4,
        poll_interval_seconds: float = 5.0,
        max_retries: int = 3,
    ):
        self._gpio_pin = int(gpio_pin)
        self._poll_interval = max(2.0, float(poll_interval_seconds))
        self._max_retries = max(1, int(max_retries))
        self._sensor: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last: TemperatureReading = TemperatureReading()
        self._status = "Temperature sensor not initialised."
        self._callbacks: list[Callable[[TemperatureReading], None]] = []

        if _adafruit_dht is None:
            self._status = "Temperature sensor disabled: adafruit-circuitpython-dht not installed."
            return

        board_pin = _board_pin(self._gpio_pin)
        if board_pin is None:
            self._status = f"Temperature sensor disabled: GPIO {self._gpio_pin} not found on board."
            return

        try:
            self._sensor = _adafruit_dht.DHT22(board_pin, use_pulseio=False)
            self._status = f"AM2301A sensor ready on GPIO {self._gpio_pin}."
        except Exception as exc:
            self._status = f"Temperature sensor init failed: {exc}"
            logger.warning("AM2301A init error on GPIO %d: %s", self._gpio_pin, exc)

    # -- Public API --------------------------------------------------------

    def is_available(self) -> bool:
        return self._sensor is not None

    def status_line(self) -> str:
        return self._status

    def read(self) -> TemperatureReading:
        """Take a single reading (blocking, with retries)."""
        if self._sensor is None:
            return TemperatureReading()
        for attempt in range(self._max_retries):
            try:
                temp = self._sensor.temperature
                hum = self._sensor.humidity
                if temp is not None and hum is not None:
                    reading = TemperatureReading(
                        temperature_c=round(float(temp), 1),
                        humidity_pct=round(float(hum), 1),
                        valid=True,
                    )
                    with self._lock:
                        self._last = reading
                    return reading
            except RuntimeError as exc:
                # DHT sensors commonly throw RuntimeError on transient read
                logger.debug("AM2301A read retry %d/%d: %s", attempt + 1, self._max_retries, exc)
                time.sleep(0.5)
            except Exception as exc:
                logger.warning("AM2301A unexpected read error: %s", exc)
                break
        return TemperatureReading()

    @property
    def last_reading(self) -> TemperatureReading:
        with self._lock:
            return self._last

    def start(self, callback: Callable[[TemperatureReading], None] | None = None) -> None:
        """Start background polling thread."""
        if callback is not None:
            self._callbacks.append(callback)
        if self._thread is not None or self._sensor is None:
            return

        def _run() -> None:
            logger.info(
                "AM2301A polling started (GPIO %d, every %.1fs).",
                self._gpio_pin,
                self._poll_interval,
            )
            while not self._stop.is_set():
                reading = self.read()
                if reading.valid:
                    for cb in self._callbacks:
                        try:
                            cb(reading)
                        except Exception as exc:
                            logger.warning("Temperature callback error: %s", exc)
                self._stop.wait(self._poll_interval)

        self._thread = threading.Thread(target=_run, name="am2301a-poll", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop polling and release the sensor."""
        self._stop.set()
        if self._sensor is not None:
            try:
                self._sensor.exit()
            except Exception:
                pass
            self._sensor = None


# ---------------------------------------------------------------------------
# Noop fallback (matches the same interface)
# ---------------------------------------------------------------------------


class NoopTemperatureMonitor:
    """Placeholder used when the real sensor is unavailable."""

    def __init__(self, reason: str = "Temperature sensor disabled."):
        self._reason = reason

    def is_available(self) -> bool:
        return False

    def status_line(self) -> str:
        return self._reason

    def read(self) -> TemperatureReading:
        return TemperatureReading()

    @property
    def last_reading(self) -> TemperatureReading:
        return TemperatureReading()

    def start(self, callback: Callable[[TemperatureReading], None] | None = None) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_temperature_monitor(settings: Any) -> TemperatureSensorMonitor | NoopTemperatureMonitor:
    """Create a temperature monitor from app settings.

    Expected settings attributes:
      sensor_temperature_enabled: bool
      sensor_temperature_pin: int     (BCM GPIO number, default 4)
      sensor_temperature_poll_interval_seconds: float  (default 5.0)
    """
    enabled = getattr(settings, "sensor_temperature_enabled", False)
    if not enabled:
        return NoopTemperatureMonitor("Temperature sensor disabled by configuration.")

    pin = int(getattr(settings, "sensor_temperature_pin", 4))
    interval = float(getattr(settings, "sensor_temperature_poll_interval_seconds", 5.0))

    monitor = TemperatureSensorMonitor(gpio_pin=pin, poll_interval_seconds=interval)
    if not monitor.is_available():
        return NoopTemperatureMonitor(monitor.status_line())
    return monitor
