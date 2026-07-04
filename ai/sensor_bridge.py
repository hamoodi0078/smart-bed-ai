"""Sensor event bridge for Danah Smart Bed.

Classifies hardware events into semantic actions and routes them to the AI.

Sources accepted:
  1. GPIO  — direct call via classify_event() from RaspberryPiSensorMonitor
  2. MQTT  — auto-subscribed when attach_mqtt() is called
  3. Zigbee — routed through MQTT (danah/sensors/# topic)

All sources funnel into the same classify_event() logic so the AI layer
sees one consistent event stream regardless of how the sensor is connected.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from loguru import logger


class SensorBridge:
    """Modular hardware-event bridge for pressure/motion-driven proactive greetings."""

    def __init__(self):
        self._last_morning_date = ""
        self._last_evening_date = ""
        self._event_callbacks: list[Callable[[str], None]] = []

        # Latest readings from any source
        self._pressure_active = False
        self._motion_active = False
        self._temperature: float | None = None
        self._humidity: float | None = None
        self._heart_rate: float | None = None

        # MQTT motion threshold — Zigbee occupancy clusters send 0 or 1
        self._motion_threshold = 0.5

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_event(self, callback: Callable[[str], None]) -> None:
        """Register a callback that fires whenever a semantic event is classified.

        callback receives the event name string, e.g. 'bed_entered_evening'.
        """
        if callable(callback):
            self._event_callbacks.append(callback)

    # ------------------------------------------------------------------
    # MQTT integration
    # ------------------------------------------------------------------

    def attach_mqtt(self, mqtt_client: Any) -> None:
        """Subscribe to all sensor topics on the MQTT bus.

        Call once after mqtt_client.connect() returns True.
        """
        try:
            mqtt_client.subscribe_sensors(self._on_mqtt_sensor)
            mqtt_client.subscribe_bed_events(self._on_mqtt_bed_event)
            logger.info("SensorBridge attached to MQTT bus.")
        except Exception as exc:
            logger.warning("SensorBridge MQTT attach failed: %s", exc)

    def _on_mqtt_sensor(self, topic: str, payload: Any) -> None:
        """Handle incoming danah/sensors/+ messages."""
        sensor_type = topic.split("/")[-1]
        value = _extract_value(payload)
        if value is None:
            return

        now = datetime.now()

        if sensor_type == "pressure":
            # Pressure > 5 units = someone on the bed
            self._pressure_active = float(value) > 5.0
            event = self.classify_event(self._pressure_active, self._motion_active, now)
            if event:
                self._fire(event)

        elif sensor_type == "motion":
            self._motion_active = float(value) >= self._motion_threshold
            event = self.classify_event(self._pressure_active, self._motion_active, now)
            if event:
                self._fire(event)

        elif sensor_type == "temperature":
            self._temperature = float(value)
            logger.debug("MQTT temperature: %.1f°C", self._temperature)

        elif sensor_type == "humidity":
            self._humidity = float(value)
            logger.debug("MQTT humidity: %.1f%%", self._humidity)

        elif sensor_type == "heart_rate":
            self._heart_rate = float(value)
            logger.debug("MQTT heart_rate: %.0f bpm", self._heart_rate)

    def _on_mqtt_bed_event(self, _topic: str, payload: Any) -> None:
        """Handle pre-classified bed events published externally."""
        if isinstance(payload, dict):
            event = str(payload.get("event", "")).strip()
        else:
            event = str(payload or "").strip()
        if event:
            logger.debug("MQTT bed event received: %s", event)
            self._fire(event)

    # ------------------------------------------------------------------
    # Core event classification (GPIO path — unchanged public API)
    # ------------------------------------------------------------------

    def classify_event(
        self,
        pressure_active: bool,
        motion_active: bool,
        now: datetime | None = None,
    ) -> str:
        now = now or datetime.now()
        if not (pressure_active or motion_active):
            return ""

        today = now.date().isoformat()
        if 18 <= now.hour <= 23:
            if self._last_evening_date != today:
                self._last_evening_date = today
                return "bed_entered_evening"
        if 5 <= now.hour <= 11:
            if self._last_morning_date != today:
                self._last_morning_date = today
                return "wake_detected_morning"
        return ""

    # ------------------------------------------------------------------
    # Direct hardware sensor integration (GPIO drivers)
    # ------------------------------------------------------------------

    def update_temperature(self, temperature_c: float, humidity_pct: float | None = None) -> None:
        """Accept a reading from the AM2301A driver (or any source)."""
        self._temperature = float(temperature_c)
        if humidity_pct is not None:
            self._humidity = float(humidity_pct)
        logger.debug(
            "SensorBridge temperature updated: %.1f°C, humidity: %s%%",
            self._temperature,
            self._humidity,
        )

    def update_heart_rate(self, heart_rate_bpm: float, spo2_pct: float | None = None) -> None:
        """Accept a reading from the MAX30102 driver (or any source)."""
        self._heart_rate = float(heart_rate_bpm)
        if spo2_pct is not None:
            self._spo2 = float(spo2_pct)
        logger.debug(
            "SensorBridge heart rate updated: %.0f bpm, SpO2: %s%%",
            self._heart_rate,
            getattr(self, "_spo2", None),
        )

    # ------------------------------------------------------------------
    # Environmental data accessors (populated by MQTT/Zigbee/GPIO)
    # ------------------------------------------------------------------

    def get_temperature(self) -> float | None:
        return self._temperature

    def get_humidity(self) -> float | None:
        return self._humidity

    def get_heart_rate(self) -> float | None:
        return self._heart_rate

    def get_spo2(self) -> float | None:
        return getattr(self, "_spo2", None)

    def get_environment_summary(self) -> dict[str, Any]:
        return {
            "temperature_c": self._temperature,
            "humidity_pct": self._humidity,
            "heart_rate_bpm": self._heart_rate,
            "spo2_pct": getattr(self, "_spo2", None),
            "pressure_active": self._pressure_active,
            "motion_active": self._motion_active,
        }

    # ------------------------------------------------------------------
    # Proactive greeting (unchanged)
    # ------------------------------------------------------------------

    @staticmethod
    def tts_profile_for_time(now: datetime | None = None) -> dict:
        now = now or datetime.now()
        if now.hour >= 23 or now.hour < 6:
            return {
                "profile_override": "whisper",
                "pace_multiplier": 0.9,
                "volume_multiplier": 0.58,
                "label": "night_whisper",
            }
        return {
            "profile_override": "default",
            "pace_multiplier": 1.0,
            "volume_multiplier": 1.0,
            "label": "default",
        }

    def proactive_greeting(self, event_name: str, user_name: str = "") -> str:
        name = str(user_name or "").strip()
        prefix = f"{name}, " if name else ""
        if event_name == "bed_entered_evening":
            return (
                f"{prefix}welcome in. I can start a calm evening wind-down whenever you are ready."
            )
        if event_name == "wake_detected_morning":
            return f"{prefix}good morning. I can start a gentle wake routine and today plan in under one minute."
        return ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, event: str) -> None:
        for cb in self._event_callbacks:
            try:
                cb(event)
            except Exception as exc:
                logger.warning("SensorBridge event callback error: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_value(payload: Any) -> float | None:
    if isinstance(payload, (int, float)):
        return float(payload)
    if isinstance(payload, str):
        try:
            return float(payload)
        except ValueError:
            return None
    if isinstance(payload, dict):
        for key in ("value", "val", "v", "reading"):
            if key in payload:
                try:
                    return float(payload[key])
                except (TypeError, ValueError):
                    pass
    return None
