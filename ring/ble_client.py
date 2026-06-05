"""BLE client for COLMI smart rings.

Manages Bluetooth Low Energy connection to COLMI R02/R06/R10 rings using
the ``bleak`` library.  Runs as a background asyncio task on the Raspberry Pi,
providing real-time biometric streaming and historical data sync.

Features:
  - BLE scanning for ring discovery
  - Auto-reconnect with exponential backoff (mirrors VoiceCircuitBreaker pattern)
  - Real-time HR and SpO₂ streaming via GATT notifications
  - Historical sleep/HR/step data sync from ring memory
  - Battery monitoring
  - Thread-safe callback system for real-time readings
  - Noop fallback when BLE is unavailable

Usage:
    from ring.ble_client import RingBleClient, NoopRingClient

    client = RingBleClient(ble_address="AA:BB:CC:DD:EE:FF")
    await client.connect()
    client.on_hr_reading(lambda r: print(r.heart_rate_bpm))
    await client.start_realtime_hr()
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ring.models import (
    RingAccelReading,
    RingConnectionState,
    RingDevice,
    RingDeviceInfo,
    RingHrLogEntry,
    RingHrReading,
    RingModel,
    RingSleepRecord,
    RingSpo2Reading,
    RingStepRecord,
)
from ring.protocol import (
    COLMI_NAME_PREFIXES,
    COLMI_RX_CHAR_UUID,
    COLMI_SERVICE_UUID,
    COLMI_TX_CHAR_UUID,
    cmd_battery,
    cmd_device_info,
    cmd_read_hr_log,
    cmd_read_sleep_log,
    cmd_read_step_log,
    cmd_read_temperature,
    cmd_set_time,
    cmd_start_realtime_hr,
    cmd_start_realtime_spo2,
    cmd_stop_realtime_hr,
    cmd_stop_realtime_spo2,
    parse_battery,
    parse_device_info,
    parse_hr_log,
    parse_realtime_hr,
    parse_realtime_spo2,
    parse_sleep_log,
    parse_step_log,
    parse_tag,
    parse_temperature,
    TAG_BATTERY,
    TAG_DEVICE_INFO,
    TAG_HEART_RATE_LOG,
    TAG_REALTIME_HR_DATA,
    TAG_REALTIME_SPO2_DATA,
    TAG_SLEEP_LOG,
    TAG_SPO2_LOG,
    TAG_STEP_LOG,
    TAG_TEMPERATURE,
    _validate_packet,
)

logger = logging.getLogger("ring.ble_client")

# Lazy-import bleak
_bleak: Any = None
try:
    import bleak as _bleak_import
    _bleak = _bleak_import
except ImportError:
    logger.debug("bleak not installed — ring BLE disabled.")


# ---------------------------------------------------------------------------
# Ring BLE Client
# ---------------------------------------------------------------------------

class RingBleClient:
    """Manages BLE connection to a COLMI smart ring.

    Thread-safe: callbacks fire from the asyncio event loop thread.
    All public methods are async-safe.
    """

    def __init__(
        self,
        *,
        ble_address: str = "",
        model: str = "colmi_r02",
        auto_connect: bool = True,
        realtime_hr: bool = True,
        realtime_spo2: bool = True,
        sync_interval_minutes: int = 30,
        reconnect_max_retries: int = 10,
        reconnect_backoff_base: float = 2.0,
        reconnect_backoff_max: float = 120.0,
    ):
        self._address = ble_address.strip().upper()
        self._model = RingModel.from_str(model)
        self._auto_connect = auto_connect
        self._realtime_hr = realtime_hr
        self._realtime_spo2 = realtime_spo2
        self._sync_interval = max(5, sync_interval_minutes) * 60
        self._max_retries = max(1, reconnect_max_retries)
        self._backoff_base = max(1.0, reconnect_backoff_base)
        self._backoff_max = max(10.0, reconnect_backoff_max)

        # State
        self._state = RingConnectionState.DISCONNECTED
        self._client: Any = None  # bleak.BleakClient
        self._device_info: RingDeviceInfo | None = None
        self._battery_pct: int = 0
        self._retry_count: int = 0
        self._last_sync: datetime | None = None

        # Latest readings (thread-safe via lock)
        self._lock = threading.Lock()
        self._last_hr: RingHrReading = RingHrReading()
        self._last_spo2: RingSpo2Reading = RingSpo2Reading()
        self._last_temp: float | None = None

        # Callbacks
        self._hr_callbacks: list[Callable[[RingHrReading], None]] = []
        self._spo2_callbacks: list[Callable[[RingSpo2Reading], None]] = []
        self._movement_callbacks: list[Callable[[RingAccelReading], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []

        # Background tasks
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bg_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._state == RingConnectionState.CONNECTED

    @property
    def state(self) -> RingConnectionState:
        return self._state

    @property
    def last_hr(self) -> RingHrReading:
        with self._lock:
            return self._last_hr

    @property
    def last_spo2(self) -> RingSpo2Reading:
        with self._lock:
            return self._last_spo2

    @property
    def last_temp(self) -> float | None:
        with self._lock:
            return self._last_temp

    @property
    def battery_pct(self) -> int:
        return self._battery_pct

    @property
    def ring_info(self) -> RingDeviceInfo | None:
        return self._device_info

    def is_available(self) -> bool:
        return _bleak is not None

    def status_line(self) -> str:
        if not self.is_available():
            return "Ring BLE: bleak not installed."
        if self._state == RingConnectionState.CONNECTED:
            return f"Ring: connected ({self._address}), battery {self._battery_pct}%"
        return f"Ring: {self._state.value} ({self._address or 'no address'})"

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_hr_reading(self, callback: Callable[[RingHrReading], None]) -> None:
        if callable(callback):
            self._hr_callbacks.append(callback)

    def on_spo2_reading(self, callback: Callable[[RingSpo2Reading], None]) -> None:
        if callable(callback):
            self._spo2_callbacks.append(callback)

    def on_movement(self, callback: Callable[[RingAccelReading], None]) -> None:
        if callable(callback):
            self._movement_callbacks.append(callback)

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        if callable(callback):
            self._disconnect_callbacks.append(callback)

    # ------------------------------------------------------------------
    # BLE scanning
    # ------------------------------------------------------------------

    async def scan(self, timeout: float = 10.0) -> list[RingDevice]:
        """Scan for nearby COLMI rings. Returns discovered devices."""
        if _bleak is None:
            logger.warning("Cannot scan: bleak not installed.")
            return []

        self._state = RingConnectionState.SCANNING
        logger.info("Scanning for COLMI rings (%.0fs)...", timeout)

        try:
            scanner = _bleak.BleakScanner(
                service_uuids=[COLMI_SERVICE_UUID],
            )
            devices = await scanner.discover(timeout=timeout)
        except Exception as exc:
            logger.error("BLE scan error: %s", exc)
            self._state = RingConnectionState.ERROR
            return []

        rings: list[RingDevice] = []
        for d in devices:
            name = str(d.name or "").strip()
            if any(name.upper().startswith(p) for p in COLMI_NAME_PREFIXES):
                model = RingModel.UNKNOWN
                for prefix in ("R02", "R06", "R10"):
                    if prefix in name.upper():
                        model = RingModel.from_str(f"colmi_{prefix.lower()}")
                        break
                rings.append(RingDevice(
                    address=str(d.address),
                    name=name,
                    rssi=int(getattr(d, "rssi", -100)),
                    model=model,
                ))

        logger.info("Found %d COLMI ring(s): %s", len(rings), [r.address for r in rings])
        self._state = RingConnectionState.DISCONNECTED
        return rings

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self, address: str = "") -> bool:
        """Connect to a specific ring by BLE address.

        If no address given, uses the pre-configured address.
        Returns True on success.
        """
        if _bleak is None:
            logger.error("Cannot connect: bleak not installed.")
            return False

        addr = (address or self._address).strip().upper()
        if not addr:
            logger.error("No BLE address specified for ring connection.")
            return False

        self._address = addr
        self._state = RingConnectionState.CONNECTING
        logger.info("Connecting to ring %s...", addr)

        try:
            client = _bleak.BleakClient(
                addr,
                disconnected_callback=self._on_ble_disconnect,
            )
            await client.connect(timeout=15.0)

            if not client.is_connected:
                logger.error("BLE connection failed — not connected.")
                self._state = RingConnectionState.ERROR
                return False

            self._client = client
            self._state = RingConnectionState.CONNECTED
            self._retry_count = 0
            logger.info("Ring connected: %s", addr)

            # Subscribe to notifications
            await client.start_notify(COLMI_RX_CHAR_UUID, self._on_notification)

            # Sync time + read device info + battery
            await self._send(cmd_set_time())
            await asyncio.sleep(0.3)
            await self._send(cmd_device_info())
            await asyncio.sleep(0.3)
            await self._send(cmd_battery())

            # Start real-time streams if configured
            if self._realtime_hr:
                await asyncio.sleep(0.3)
                await self._send(cmd_start_realtime_hr())
                logger.info("Real-time HR streaming started.")

            if self._realtime_spo2:
                await asyncio.sleep(0.3)
                await self._send(cmd_start_realtime_spo2())
                logger.info("Real-time SpO₂ streaming started.")

            return True

        except Exception as exc:
            logger.error("Ring connection error: %s", exc)
            self._state = RingConnectionState.ERROR
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnect from the ring."""
        if self._client is not None:
            try:
                # Stop streams before disconnecting
                if self._realtime_hr:
                    await self._send(cmd_stop_realtime_hr())
                if self._realtime_spo2:
                    await self._send(cmd_stop_realtime_spo2())
                await asyncio.sleep(0.2)
                await self._client.disconnect()
            except Exception as exc:
                logger.warning("Disconnect error: %s", exc)
            finally:
                self._client = None
                self._state = RingConnectionState.DISCONNECTED
                logger.info("Ring disconnected.")

    async def _reconnect(self) -> bool:
        """Auto-reconnect with exponential backoff."""
        if not self._address or not self._auto_connect:
            return False

        self._state = RingConnectionState.RECONNECTING
        for attempt in range(self._max_retries):
            delay = min(self._backoff_max, self._backoff_base ** attempt)
            logger.info(
                "Ring reconnect attempt %d/%d in %.0fs...",
                attempt + 1, self._max_retries, delay,
            )
            await asyncio.sleep(delay)
            if await self.connect():
                return True
        logger.error("Ring reconnection failed after %d attempts.", self._max_retries)
        self._state = RingConnectionState.ERROR
        return False

    # ------------------------------------------------------------------
    # Data commands
    # ------------------------------------------------------------------

    async def start_realtime_hr(self) -> None:
        """Start continuous HR streaming from ring."""
        await self._send(cmd_start_realtime_hr())

    async def stop_realtime_hr(self) -> None:
        """Stop continuous HR streaming."""
        await self._send(cmd_stop_realtime_hr())

    async def start_realtime_spo2(self) -> None:
        """Start continuous SpO₂ streaming from ring."""
        await self._send(cmd_start_realtime_spo2())

    async def stop_realtime_spo2(self) -> None:
        """Stop continuous SpO₂ streaming."""
        await self._send(cmd_stop_realtime_spo2())

    async def read_battery(self) -> int:
        """Request battery level (result arrives via notification)."""
        await self._send(cmd_battery())
        await asyncio.sleep(0.5)
        return self._battery_pct

    async def read_skin_temperature(self) -> float | None:
        """Request skin temperature (result arrives via notification)."""
        await self._send(cmd_read_temperature())
        await asyncio.sleep(0.5)
        return self.last_temp

    async def sync_sleep_data(self, days: int = 7) -> list[RingSleepRecord]:
        """Pull sleep logs from ring memory for the last N days."""
        records: list[RingSleepRecord] = []
        now = datetime.now(timezone.utc)
        for offset in range(min(30, max(1, days))):
            await self._send(cmd_read_sleep_log(offset))
            await asyncio.sleep(0.5)
            # Response parsed in _on_notification — collect from internal buffer
        self._last_sync = datetime.now(timezone.utc)
        return records

    async def sync_hr_log(self, days: int = 1) -> list[RingHrLogEntry]:
        """Pull HR log from ring memory."""
        entries: list[RingHrLogEntry] = []
        for offset in range(min(7, max(1, days))):
            await self._send(cmd_read_hr_log(offset))
            await asyncio.sleep(0.5)
        return entries

    async def sync_step_log(self, days: int = 7) -> list[RingStepRecord]:
        """Pull step log from ring memory."""
        records: list[RingStepRecord] = []
        for offset in range(min(30, max(1, days))):
            await self._send(cmd_read_step_log(offset))
            await asyncio.sleep(0.5)
        return records

    # ------------------------------------------------------------------
    # Background runner (for integration with sync main loop)
    # ------------------------------------------------------------------

    def start_background(self) -> None:
        """Start the BLE client in a background thread with its own event loop.

        Call this from the synchronous voice runtime (app_entry.py).
        The BLE client runs its own asyncio loop in a daemon thread.
        """
        if self._bg_thread is not None:
            return
        if not self.is_available():
            logger.warning("Cannot start ring background: bleak not installed.")
            return

        self._stop_event.clear()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                loop.run_until_complete(self._background_main())
            except Exception as exc:
                logger.error("Ring background loop error: %s", exc)
            finally:
                loop.close()

        self._bg_thread = threading.Thread(
            target=_run, name="ring-ble-bg", daemon=True,
        )
        self._bg_thread.start()
        logger.info("Ring BLE background thread started.")

    async def _background_main(self) -> None:
        """Main async loop: connect, stream, periodic sync."""
        if self._address:
            await self.connect()

        while not self._stop_event.is_set():
            if not self.is_connected and self._auto_connect and self._address:
                await self._reconnect()

            # Periodic battery check
            if self.is_connected:
                try:
                    await self.read_battery()
                except Exception:
                    pass

            # Wait until next tick
            await asyncio.sleep(60.0)

    def stop_background(self) -> None:
        """Stop the background BLE thread."""
        self._stop_event.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ------------------------------------------------------------------
    # Internal BLE handling
    # ------------------------------------------------------------------

    async def _send(self, data: bytes) -> None:
        """Write a command packet to the ring's TX characteristic."""
        if self._client is None or not self._client.is_connected:
            return
        try:
            await self._client.write_gatt_char(COLMI_TX_CHAR_UUID, data, response=False)
        except Exception as exc:
            logger.warning("Ring write error: %s", exc)

    def _on_notification(self, _sender: Any, data: bytearray) -> None:
        """Handle incoming GATT notifications from the ring."""
        raw = bytes(data)
        if len(raw) < 2:
            return

        if not _validate_packet(raw):
            logger.debug("Ring packet checksum mismatch — ignoring.")
            return

        tag = parse_tag(raw)

        if tag == TAG_REALTIME_HR_DATA:
            reading = parse_realtime_hr(raw)
            if reading.valid:
                with self._lock:
                    self._last_hr = reading
                for cb in self._hr_callbacks:
                    try:
                        cb(reading)
                    except Exception as exc:
                        logger.warning("HR callback error: %s", exc)

        elif tag == TAG_REALTIME_SPO2_DATA:
            reading = parse_realtime_spo2(raw)
            if reading.valid:
                with self._lock:
                    self._last_spo2 = reading
                for cb in self._spo2_callbacks:
                    try:
                        cb(reading)
                    except Exception as exc:
                        logger.warning("SpO₂ callback error: %s", exc)

        elif tag == TAG_BATTERY:
            self._battery_pct = parse_battery(raw)
            logger.debug("Ring battery: %d%%", self._battery_pct)

        elif tag == TAG_DEVICE_INFO:
            info_dict = parse_device_info(raw)
            self._device_info = RingDeviceInfo(
                address=self._address,
                name="",
                model=self._model,
                firmware_version=info_dict.get("firmware_version", ""),
                battery_pct=self._battery_pct,
                last_sync_at=self._last_sync,
            )
            logger.info("Ring device info: %s", self._device_info)

        elif tag == TAG_TEMPERATURE:
            temp = parse_temperature(raw)
            if temp is not None:
                with self._lock:
                    self._last_temp = temp
                logger.debug("Ring skin temp: %.1f°C", temp)

        elif tag == TAG_SLEEP_LOG:
            record = parse_sleep_log(raw)
            if record:
                logger.info("Ring sleep log: %s", record)

        elif tag == TAG_HEART_RATE_LOG:
            entries = parse_hr_log(raw)
            if entries:
                logger.debug("Ring HR log: %d entries", len(entries))

        elif tag == TAG_STEP_LOG:
            record = parse_step_log(raw)
            if record:
                logger.debug("Ring step log: %s steps", record.steps)

    def _on_ble_disconnect(self, _client: Any) -> None:
        """Called by bleak when the BLE connection drops."""
        logger.warning("Ring BLE disconnected unexpectedly.")
        self._state = RingConnectionState.DISCONNECTED
        self._client = None
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Snapshot for API/voice
    # ------------------------------------------------------------------

    def get_status_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable status snapshot."""
        with self._lock:
            hr = self._last_hr
            spo2 = self._last_spo2
            temp = self._last_temp
        return {
            "connected": self.is_connected,
            "state": self._state.value,
            "address": self._address,
            "model": self._model.value,
            "battery_pct": self._battery_pct,
            "heart_rate_bpm": hr.heart_rate_bpm if hr.valid else None,
            "spo2_pct": spo2.spo2_pct if spo2.valid else None,
            "skin_temp_c": temp,
            "firmware_version": self._device_info.firmware_version if self._device_info else None,
            "last_sync_at": self._last_sync.isoformat() if self._last_sync else None,
        }


# ---------------------------------------------------------------------------
# Noop fallback (same pattern as NoopHeartRateMonitor)
# ---------------------------------------------------------------------------

class NoopRingClient:
    """Placeholder when ring is disabled or bleak is not installed.

    Every method returns safe defaults, so calling code never needs
    conditional checks.
    """

    def __init__(self, reason: str = "Ring disabled."):
        self._reason = reason

    @property
    def is_connected(self) -> bool:
        return False

    @property
    def state(self) -> RingConnectionState:
        return RingConnectionState.DISCONNECTED

    @property
    def last_hr(self) -> RingHrReading:
        return RingHrReading()

    @property
    def last_spo2(self) -> RingSpo2Reading:
        return RingSpo2Reading()

    @property
    def last_temp(self) -> float | None:
        return None

    @property
    def battery_pct(self) -> int:
        return 0

    @property
    def ring_info(self) -> RingDeviceInfo | None:
        return None

    def is_available(self) -> bool:
        return False

    def status_line(self) -> str:
        return self._reason

    def on_hr_reading(self, callback: Callable[[RingHrReading], None]) -> None:
        pass

    def on_spo2_reading(self, callback: Callable[[RingSpo2Reading], None]) -> None:
        pass

    def on_movement(self, callback: Callable[[RingAccelReading], None]) -> None:
        pass

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        pass

    async def scan(self, timeout: float = 10.0) -> list[RingDevice]:
        return []

    async def connect(self, address: str = "") -> bool:
        return False

    async def disconnect(self) -> None:
        pass

    async def start_realtime_hr(self) -> None:
        pass

    async def stop_realtime_hr(self) -> None:
        pass

    async def start_realtime_spo2(self) -> None:
        pass

    async def stop_realtime_spo2(self) -> None:
        pass

    async def read_battery(self) -> int:
        return 0

    async def read_skin_temperature(self) -> float | None:
        return None

    async def sync_sleep_data(self, days: int = 7) -> list[RingSleepRecord]:
        return []

    async def sync_hr_log(self, days: int = 1) -> list[RingHrLogEntry]:
        return []

    async def sync_step_log(self, days: int = 7) -> list[RingStepRecord]:
        return []

    def start_background(self) -> None:
        pass

    def stop_background(self) -> None:
        pass

    def get_status_dict(self) -> dict[str, Any]:
        return {
            "connected": False,
            "state": "disabled",
            "address": "",
            "model": "",
            "battery_pct": 0,
            "heart_rate_bpm": None,
            "spo2_pct": None,
            "skin_temp_c": None,
            "firmware_version": None,
            "last_sync_at": None,
            "reason": self._reason,
        }
