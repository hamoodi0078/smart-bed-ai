from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from typing import Callable

try:
    from gpiozero import DigitalInputDevice
except Exception:  # pragma: no cover - optional runtime dependency
    DigitalInputDevice = None

logger = logging.getLogger("hardware.pi_sensors")

# MQTT publisher — lazy import so missing env vars don't crash sensor startup
_mqtt_client = None
_mqtt_attempted = False


def _get_mqtt():
    global _mqtt_client, _mqtt_attempted
    if _mqtt_attempted:
        return _mqtt_client
    _mqtt_attempted = True
    try:
        from integrations.mqtt_client import get_mqtt_client
        client = get_mqtt_client()
        if client.is_connected():
            _mqtt_client = client
            logger.info("pi_sensors: MQTT publishing enabled.")
        else:
            logger.debug("pi_sensors: MQTT client not connected — readings local only.")
    except Exception as exc:
        logger.debug("pi_sensors: MQTT unavailable: %s", exc)
    return _mqtt_client


@dataclass(frozen=True)
class SensorSnapshot:
    pressure_active: bool = False
    motion_active: bool = False


class NoopSensorMonitor:
    def __init__(self, reason: str):
        self._reason = str(reason or "Sensor monitor disabled.")

    def is_available(self) -> bool:
        return False

    def status_line(self) -> str:
        return self._reason

    def snapshot(self) -> SensorSnapshot:
        return SensorSnapshot()

    def start(self, on_change: Callable[[SensorSnapshot], None] | None = None) -> None:
        if callable(on_change):
            try:
                on_change(self.snapshot())
            except Exception:
                return

    def close(self) -> None:
        return


class RaspberryPiSensorMonitor:
    def __init__(
        self,
        *,
        pressure_enabled: bool,
        pressure_pin: int,
        pressure_pull_up: bool,
        pressure_active_low: bool,
        motion_enabled: bool,
        motion_pin: int,
        motion_pull_up: bool,
        motion_active_low: bool,
        poll_interval_seconds: float = 0.2,
        input_factory=None,
    ):
        self._input_factory = input_factory or DigitalInputDevice
        self._poll_interval_seconds = max(0.05, float(poll_interval_seconds))
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._status = "Sensor monitor unavailable."
        self._last_snapshot = SensorSnapshot()
        self._devices: dict[str, dict] = {}

        if not sys.platform.startswith("linux"):
            self._status = "Sensor monitor disabled: non-Linux platform."
            return
        if self._input_factory is None:
            self._status = "Sensor monitor disabled: install gpiozero on the Raspberry Pi."
            return

        try:
            if bool(pressure_enabled) and int(pressure_pin) >= 0:
                self._devices["pressure"] = {
                    "device": self._input_factory(int(pressure_pin), pull_up=bool(pressure_pull_up)),
                    "active_low": bool(pressure_active_low),
                    "pin": int(pressure_pin),
                }
            if bool(motion_enabled) and int(motion_pin) >= 0:
                self._devices["motion"] = {
                    "device": self._input_factory(int(motion_pin), pull_up=bool(motion_pull_up)),
                    "active_low": bool(motion_active_low),
                    "pin": int(motion_pin),
                }
        except Exception as exc:
            self._status = f"Sensor monitor unavailable: {exc}"
            logger.warning("Failed to initialize Raspberry Pi sensor inputs: %s", exc)
            self.close()
            return

        if not self._devices:
            self._status = "Sensor monitor disabled: no GPIO input pins configured."
            return

        labels = []
        if "pressure" in self._devices:
            labels.append(f"pressure pin {self._devices['pressure']['pin']}")
        if "motion" in self._devices:
            labels.append(f"motion pin {self._devices['motion']['pin']}")
        self._status = "Raspberry Pi sensor monitor active: " + ", ".join(labels) + "."
        self._last_snapshot = self.snapshot()

    def is_available(self) -> bool:
        return bool(self._devices)

    def status_line(self) -> str:
        return self._status

    def _read_active(self, name: str) -> bool:
        row = self._devices.get(name)
        if not row:
            return False
        try:
            raw_value = bool(getattr(row["device"], "value", 0))
        except Exception:
            return False
        return (not raw_value) if bool(row.get("active_low", False)) else raw_value

    def snapshot(self) -> SensorSnapshot:
        return SensorSnapshot(
            pressure_active=self._read_active("pressure"),
            motion_active=self._read_active("motion"),
        )

    def start(self, on_change: Callable[[SensorSnapshot], None] | None = None) -> None:
        if not self.is_available():
            if callable(on_change):
                try:
                    on_change(self.snapshot())
                except Exception:
                    return
            return
        if self._thread is not None:
            return

        callback = on_change

        def _run():
            while not self._stop_event.is_set():
                snapshot = self.snapshot()
                with self._lock:
                    last_snapshot = self._last_snapshot
                    if snapshot != last_snapshot:
                        self._last_snapshot = snapshot
                        should_emit = True
                    else:
                        should_emit = False
                if should_emit:
                    if callable(callback):
                        try:
                            callback(snapshot)
                        except Exception as exc:
                            logger.warning("Sensor snapshot callback failed: %s", exc)
                    # Publish changed readings to MQTT bus
                    mqtt = _get_mqtt()
                    if mqtt:
                        try:
                            mqtt.publish_sensor("pressure", 100.0 if snapshot.pressure_active else 0.0)
                            mqtt.publish_sensor("motion", 1.0 if snapshot.motion_active else 0.0)
                        except Exception as exc:
                            logger.debug("MQTT sensor publish failed: %s", exc)
                self._stop_event.wait(self._poll_interval_seconds)

        self._thread = threading.Thread(target=_run, name="pi-sensor-monitor", daemon=True)
        self._thread.start()
        if callable(callback):
            try:
                callback(self.snapshot())
            except Exception:
                return

    def close(self) -> None:
        self._stop_event.set()
        devices = list(self._devices.values())
        self._devices = {}
        for row in devices:
            device = row.get("device")
            if device is None:
                continue
            try:
                device.close()
            except Exception:
                continue


def build_sensor_monitor(settings):
    return RaspberryPiSensorMonitor(
        pressure_enabled=bool(settings.sensor_pressure_enabled),
        pressure_pin=int(settings.sensor_pressure_pin),
        pressure_pull_up=bool(settings.sensor_pressure_pull_up),
        pressure_active_low=bool(settings.sensor_pressure_active_low),
        motion_enabled=bool(settings.sensor_motion_enabled),
        motion_pin=int(settings.sensor_motion_pin),
        motion_pull_up=bool(settings.sensor_motion_pull_up),
        motion_active_low=bool(settings.sensor_motion_active_low),
        poll_interval_seconds=float(settings.sensor_poll_interval_seconds),
    )
