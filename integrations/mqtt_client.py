"""MQTT client for Danah Smart Bed IoT bus.

Acts as the central pub/sub hub connecting:
  - Raspberry Pi GPIO sensors  (publishers)
  - Zigbee sensors via zigpy   (publishers)
  - Smart home devices          (subscribers)
  - Sleep intelligence engine   (subscriber + publisher)
  - LED / light commands        (subscribers)

Topic layout:
  danah/sensors/pressure        float 0-100
  danah/sensors/motion          1 or 0
  danah/sensors/temperature     float °C
  danah/sensors/humidity        float %RH
  danah/sensors/heart_rate      float bpm
  danah/bed/occupancy           JSON {"state": "both|left|right|empty"}
  danah/bed/events              JSON {"event": "bed_entry|wake|...", "side": "..."}
  danah/commands/led            JSON {"op": "set_color|set_brightness", ...}
  danah/commands/lights_out     1
  danah/commands/bedtime_mode   1
  danah/zigbee/<ieee>/<cluster> JSON device payload
  danah/system/status           JSON health ping
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("integrations.mqtt_client")

try:
    import paho.mqtt.client as mqtt  # type: ignore

    _PAHO_AVAILABLE = True
except ImportError:
    mqtt = None  # type: ignore
    _PAHO_AVAILABLE = False
    logger.warning("paho-mqtt not installed — MQTT bus disabled.")

# ---------------------------------------------------------------------------
# Topic constants
# ---------------------------------------------------------------------------


class Topics:
    PRESSURE = "danah/sensors/pressure"
    MOTION = "danah/sensors/motion"
    TEMPERATURE = "danah/sensors/temperature"
    HUMIDITY = "danah/sensors/humidity"
    HEART_RATE = "danah/sensors/heart_rate"
    OCCUPANCY = "danah/bed/occupancy"
    BED_EVENTS = "danah/bed/events"
    LED_COMMAND = "danah/commands/led"
    LIGHTS_OUT = "danah/commands/lights_out"
    BEDTIME_MODE = "danah/commands/bedtime_mode"
    ZIGBEE_PREFIX = "danah/zigbee"
    SYSTEM_STATUS = "danah/system/status"


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class MQTTClient:
    """Thread-safe paho-mqtt wrapper with auto-reconnect and typed pub/sub."""

    def __init__(
        self,
        *,
        host: str = "",
        port: int = 1883,
        username: str = "",
        password: str = "",
        client_id: str = "danah-smart-bed",
        keepalive: int = 60,
        tls: bool = False,
        reconnect_delay_seconds: float = 5.0,
    ):
        self._host = str(host or os.getenv("MQTT_HOST", "localhost")).strip()
        self._port = int(port or int(os.getenv("MQTT_PORT", "1883")))
        self._username = str(username or os.getenv("MQTT_USERNAME", "")).strip()
        self._password = str(password or os.getenv("MQTT_PASSWORD", "")).strip()
        self._client_id = str(client_id).strip()
        self._keepalive = max(10, int(keepalive))
        self._tls = bool(tls or os.getenv("MQTT_TLS", "0") == "1")
        self._reconnect_delay = max(1.0, float(reconnect_delay_seconds))

        self._client: Any = None
        self._connected = False
        self._lock = threading.RLock()
        self._subscriptions: dict[str, list[Callable[[str, Any], None]]] = {}
        self._reconnect_thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        if not _PAHO_AVAILABLE:
            logger.error("paho-mqtt not installed. Run: pip install paho-mqtt")
            return False
        if not self._host:
            logger.warning("MQTT_HOST not set — MQTT bus disabled.")
            return False

        with self._lock:
            if self._connected:
                return True
            try:
                self._client = mqtt.Client(client_id=self._client_id, clean_session=True)
                if self._username:
                    self._client.username_pw_set(self._username, self._password or None)
                if self._tls:
                    self._client.tls_set()
                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                self._client.on_message = self._on_message
                self._client.reconnect_delay_set(min_delay=1, max_delay=30)
                self._client.connect(self._host, self._port, self._keepalive)
                self._running = True
                self._client.loop_start()
                logger.info(
                    "MQTT connecting to %s:%d as '%s'", self._host, self._port, self._client_id
                )
                return True
            except Exception as exc:
                logger.error("MQTT connect failed: %s", exc)
                self._client = None
                return False

    def disconnect(self) -> None:
        self._running = False
        with self._lock:
            if self._client:
                try:
                    self._client.loop_stop()
                    self._client.disconnect()
                except Exception:
                    pass
                self._client = None
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False) -> bool:
        with self._lock:
            if not self._client or not self._connected:
                return False
            try:
                if isinstance(payload, (dict, list)):
                    payload = json.dumps(payload)
                elif not isinstance(payload, (str, bytes, bytearray)):
                    payload = str(payload)
                result = self._client.publish(topic, payload, qos=qos, retain=retain)
                return result.rc == 0
            except Exception as exc:
                logger.warning("MQTT publish failed topic=%s: %s", topic, exc)
                return False

    def publish_sensor(self, sensor_type: str, value: float) -> bool:
        topic = f"danah/sensors/{sensor_type}"
        return self.publish(topic, round(float(value), 3))

    def publish_bed_event(self, event: str, side: str = "", extra: dict | None = None) -> bool:
        payload: dict[str, Any] = {"event": event, "side": side}
        if extra:
            payload.update(extra)
        return self.publish(Topics.BED_EVENTS, payload)

    def publish_occupancy(self, state: str) -> bool:
        return self.publish(Topics.OCCUPANCY, {"state": state}, retain=True)

    def publish_led_command(self, op: str, **kwargs: Any) -> bool:
        return self.publish(Topics.LED_COMMAND, {"op": op, **kwargs})

    def publish_status(self, status: dict[str, Any]) -> bool:
        return self.publish(Topics.SYSTEM_STATUS, status, retain=True)

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, callback: Callable[[str, Any], None], qos: int = 0) -> None:
        """Register a callback for a topic (supports wildcards + and #)."""
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
                if self._client and self._connected:
                    self._client.subscribe(topic, qos)
            self._subscriptions[topic].append(callback)

    def subscribe_sensors(self, callback: Callable[[str, Any], None]) -> None:
        """Subscribe to all danah/sensors/# topics."""
        self.subscribe("danah/sensors/#", callback)

    def subscribe_commands(self, callback: Callable[[str, Any], None]) -> None:
        """Subscribe to all danah/commands/# topics."""
        self.subscribe("danah/commands/#", callback)

    def subscribe_bed_events(self, callback: Callable[[str, Any], None]) -> None:
        self.subscribe(Topics.BED_EVENTS, callback)

    def subscribe_zigbee(self, callback: Callable[[str, Any], None]) -> None:
        self.subscribe(f"{Topics.ZIGBEE_PREFIX}/#", callback)

    # ------------------------------------------------------------------
    # paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected to %s:%d", self._host, self._port)
            with self._lock:
                for topic in self._subscriptions:
                    try:
                        client.subscribe(topic)
                    except Exception as exc:
                        logger.warning("Re-subscribe failed for %s: %s", topic, exc)
            self.publish_status({"online": True, "client_id": self._client_id})
        else:
            rc_messages = {
                1: "incorrect protocol version",
                2: "invalid client identifier",
                3: "server unavailable",
                4: "bad username/password",
                5: "not authorised",
            }
            logger.error("MQTT connection refused: %s", rc_messages.get(rc, f"rc={rc}"))

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc != 0 and self._running:
            logger.warning("MQTT unexpected disconnect rc=%d — will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg) -> None:
        topic = str(msg.topic)
        try:
            raw = msg.payload.decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                payload = raw
        except Exception:
            payload = msg.payload

        with self._lock:
            matched: list[Callable] = []
            for pattern, callbacks in self._subscriptions.items():
                if _topic_matches(pattern, topic):
                    matched.extend(callbacks)

        for cb in matched:
            try:
                cb(topic, payload)
            except Exception as exc:
                logger.warning("MQTT callback error topic=%s: %s", topic, exc)


# ---------------------------------------------------------------------------
# Topic matching (supports + and # wildcards)
# ---------------------------------------------------------------------------


def _topic_matches(pattern: str, topic: str) -> bool:
    pat_parts = pattern.split("/")
    top_parts = topic.split("/")
    if pat_parts[-1] == "#":
        return top_parts[: len(pat_parts) - 1] == pat_parts[:-1]
    if len(pat_parts) != len(top_parts):
        return False
    return all(p == t or p == "+" for p, t in zip(pat_parts, top_parts))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client: MQTTClient | None = None
_client_lock = threading.Lock()


def get_mqtt_client() -> MQTTClient:
    """Return the module-level MQTT client singleton."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = MQTTClient()
                _client.connect()
    return _client
