"""Zigbee coordinator for Danah Smart Bed via zigpy.

Connects to a USB Zigbee coordinator (Sonoff Zigbee 3.0, ConBee II, CC2531, etc.),
discovers paired sensors, and bridges their readings to:
  1. The MQTT bus (danah/zigbee/<ieee>/<cluster>)
  2. The SensorBridge / PressureIntelligence engines directly

Supported Zigbee radios (auto-detected from ZIGBEE_RADIO env var):
  - ezsp    → Sonoff Zigbee 3.0, HUSBZB-1, Elelabs
  - znp     → CC2531, CC2652
  - deconz  → ConBee I/II, RaspBee
  - zigate  → ZiGate USB
  - xbee    → XBee radios

Usage:
    Set env vars:
        ZIGBEE_RADIO=ezsp
        ZIGBEE_PORT=/dev/ttyUSB0    (or COM3 on Windows)
        ZIGBEE_DATABASE=runtime_data/zigbee.db
    Then:
        coordinator = ZigbeeCoordinator()
        await coordinator.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any, Callable

logger = logging.getLogger("integrations.zigbee_coordinator")

# ---------------------------------------------------------------------------
# Optional imports — zigpy + radio-specific libs
# ---------------------------------------------------------------------------

try:
    import zigpy  # type: ignore
    import zigpy.config as zigpy_config  # type: ignore
    from zigpy.zcl.clusters.measurement import (  # type: ignore
        TemperatureMeasurement,
        RelativeHumidity,
        IlluminanceMeasurement,
        OccupancySensing,
        PressureMeasurement,
    )

    _ZIGPY_AVAILABLE = True
except ImportError:
    _ZIGPY_AVAILABLE = False
    logger.warning("zigpy not installed — Zigbee coordinator disabled.")

_RADIO_MODULES: dict[str, str] = {
    "ezsp": "bellows.zigbee.application",
    "znp": "zigpy_znp.zigbee.application",
    "deconz": "zigpy_deconz.zigbee.application",
    "zigate": "zigpy_zigate.zigbee.application",
    "xbee": "zigpy_xbee.zigbee.application",
}

# ---------------------------------------------------------------------------
# Sensor type mapping: Zigbee ZCL cluster IDs → Danah sensor types
# ---------------------------------------------------------------------------

_CLUSTER_MAP = {
    0x0402: "temperature",  # Temperature Measurement
    0x0405: "humidity",  # Relative Humidity
    0x0400: "illuminance",  # Illuminance
    0x0406: "motion",  # Occupancy Sensing
    0x0403: "pressure",  # Pressure Measurement
    0x0001: "battery",  # Power Configuration
}

# Attribute IDs for measured value
_MEASURED_VALUE_ATTR = 0x0000


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class ZigbeeCoordinator:
    """Manages a Zigbee radio, device registry, and sensor event routing."""

    def __init__(
        self,
        *,
        radio: str = "",
        port: str = "",
        database_path: str = "",
        channel: int = 15,
    ):
        self._radio = str(radio or os.getenv("ZIGBEE_RADIO", "ezsp")).strip().lower()
        self._port = str(port or os.getenv("ZIGBEE_PORT", "/dev/ttyUSB0")).strip()
        self._db = str(
            database_path or os.getenv("ZIGBEE_DATABASE", "runtime_data/zigbee.db")
        ).strip()
        self._channel = max(11, min(26, int(channel)))
        self._app: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._devices: dict[str, dict[str, Any]] = {}
        self._sensor_callbacks: list[Callable[[str, float, str], None]] = []
        self._mqtt_client: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start Zigbee coordinator in a background thread."""
        if not _ZIGPY_AVAILABLE:
            logger.error(
                "zigpy not installed. Run: pip install zigpy zigpy-znp bellows zigpy-deconz"
            )
            return False
        if not self._port:
            logger.warning("ZIGBEE_PORT not set — Zigbee coordinator disabled.")
            return False
        if self._running:
            return True

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="zigbee-coordinator", daemon=True
        )
        self._thread.start()
        logger.info("Zigbee coordinator starting on %s via %s", self._port, self._radio)
        return True

    def stop(self) -> None:
        self._running = False
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start_app())
        except Exception as exc:
            logger.error("Zigbee coordinator loop error: %s", exc)
        finally:
            self._loop.close()

    # ------------------------------------------------------------------
    # Application init
    # ------------------------------------------------------------------

    async def _start_app(self) -> None:
        module_path = _RADIO_MODULES.get(self._radio)
        if not module_path:
            logger.error("Unknown Zigbee radio: %s. Valid: %s", self._radio, list(_RADIO_MODULES))
            return

        try:
            import importlib

            radio_module = importlib.import_module(module_path)
            ControllerApplication = radio_module.ControllerApplication
        except ImportError as exc:
            logger.error(
                "Zigbee radio library not installed for '%s'. err=%s\nInstall: pip install %s",
                self._radio,
                exc,
                {"ezsp": "bellows", "znp": "zigpy-znp", "deconz": "zigpy-deconz"}.get(
                    self._radio, "zigpy"
                ),
            )
            return

        config = {
            zigpy_config.CONF_DEVICE: {
                zigpy_config.CONF_DEVICE_PATH: self._port,
            },
            "database_path": self._db,
        }

        try:
            self._app = await ControllerApplication.new(config, auto_form=True)
            self._app.add_listener(self._DeviceListener(self))
            await self._app.startup(auto_form=True)
            logger.info(
                "Zigbee coordinator started. %d device(s) in registry.",
                len(self._app.devices),
            )
            # Register existing paired devices
            for ieee, device in self._app.devices.items():
                self._register_device(str(ieee), device)

            # Keep running
            while self._running:
                await asyncio.sleep(1)
        except Exception as exc:
            logger.error("Zigbee app start failed: %s", exc)

    async def _shutdown(self) -> None:
        if self._app:
            try:
                await self._app.shutdown()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Device registry
    # ------------------------------------------------------------------

    def _register_device(self, ieee: str, device: Any) -> None:
        model = getattr(device, "model", "") or ""
        manufacturer = getattr(device, "manufacturer", "") or ""
        self._devices[ieee] = {
            "ieee": ieee,
            "model": model,
            "manufacturer": manufacturer,
            "nwk": getattr(device, "nwk", 0),
        }
        logger.info("Zigbee device registered: %s %s (%s)", manufacturer, model, ieee)

    def get_devices(self) -> list[dict[str, Any]]:
        return list(self._devices.values())

    # ------------------------------------------------------------------
    # Sensor event handling
    # ------------------------------------------------------------------

    def on_sensor_reading(self, callback: Callable[[str, float, str], None]) -> None:
        """Register callback: callback(sensor_type, value, ieee_address)."""
        self._sensor_callbacks.append(callback)

    def set_mqtt_client(self, client: Any) -> None:
        self._mqtt_client = client

    def _handle_sensor_report(self, ieee: str, cluster_id: int, attr_id: int, value: Any) -> None:
        sensor_type = _CLUSTER_MAP.get(cluster_id)
        if not sensor_type or attr_id != _MEASURED_VALUE_ATTR:
            return

        # ZCL value scaling
        scaled = _scale_zcl_value(cluster_id, value)
        logger.debug(
            "Zigbee sensor %s %s=%.2f (cluster=0x%04x)", ieee, sensor_type, scaled, cluster_id
        )

        # Publish to MQTT
        if self._mqtt_client:
            try:
                topic = f"danah/zigbee/{ieee}/{sensor_type}"
                self._mqtt_client.publish(
                    topic, {"value": scaled, "ieee": ieee, "type": sensor_type}
                )
                # Also publish to standard sensor topic
                self._mqtt_client.publish_sensor(sensor_type, scaled)
            except Exception as exc:
                logger.warning("Zigbee MQTT publish failed: %s", exc)

        # Fire registered callbacks
        for cb in self._sensor_callbacks:
            try:
                cb(sensor_type, scaled, ieee)
            except Exception as exc:
                logger.warning("Zigbee sensor callback error: %s", exc)

    # ------------------------------------------------------------------
    # Inner listener class (zigpy device listener)
    # ------------------------------------------------------------------

    class _DeviceListener:
        def __init__(self, coordinator: "ZigbeeCoordinator"):
            self._coord = coordinator

        def device_joined(self, device) -> None:
            ieee = str(device.ieee)
            self._coord._register_device(ieee, device)
            logger.info("Zigbee device joined: %s", ieee)

        def device_left(self, device) -> None:
            ieee = str(device.ieee)
            self._coord._devices.pop(ieee, None)
            logger.info("Zigbee device left: %s", ieee)

        def attribute_updated(self, device, cluster, attr_id, value) -> None:
            ieee = str(device.ieee)
            cluster_id = cluster.cluster_id
            self._coord._handle_sensor_report(ieee, cluster_id, attr_id, value)

        def device_initialized(self, device) -> None:
            ieee = str(device.ieee)
            self._coord._register_device(ieee, device)


# ---------------------------------------------------------------------------
# ZCL value scaling helpers
# ---------------------------------------------------------------------------


def _scale_zcl_value(cluster_id: int, raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0

    # Temperature: raw is in 0.01°C units
    if cluster_id == 0x0402:
        return round(v / 100.0, 2)

    # Humidity: raw is in 0.01% units
    if cluster_id == 0x0405:
        return round(v / 100.0, 2)

    # Occupancy: 1 = occupied, 0 = clear
    if cluster_id == 0x0406:
        return 1.0 if v else 0.0

    # Pressure: raw is in hPa
    if cluster_id == 0x0403:
        return round(v, 2)

    # Illuminance: raw is 10000 * log10(lux) + 1
    if cluster_id == 0x0400:
        import math

        try:
            return round(10 ** ((v - 1) / 10000), 2)
        except Exception:
            return v

    # Battery: raw is in 100mV units
    if cluster_id == 0x0001:
        return round(v / 10.0, 1)

    return round(v, 3)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_coordinator: ZigbeeCoordinator | None = None
_coord_lock = threading.Lock()


def get_coordinator() -> ZigbeeCoordinator:
    global _coordinator
    if _coordinator is None:
        with _coord_lock:
            if _coordinator is None:
                _coordinator = ZigbeeCoordinator()
    return _coordinator
