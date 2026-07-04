"""Unified Smart Home Device Controller for Danah Smart Bed.

Manages: Philips Hue, TP-Link Kasa, Xiaomi Mi, Tuya, Apple TV, Chromecast.

All device drivers are imported lazily with graceful fallbacks — if a library
is not installed or a device is unreachable, that driver is silently skipped
and the rest continue to work.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("integrations.smart_home")

# ---------------------------------------------------------------------------
# Optional driver imports — every one is wrapped so missing libs don't crash
# ---------------------------------------------------------------------------

try:
    from phue import Bridge as HueBridge  # type: ignore

    _HUE_AVAILABLE = True
except ImportError:
    HueBridge = None
    _HUE_AVAILABLE = False

try:
    from kasa import SmartBulb, SmartStrip, Discover  # type: ignore

    _KASA_AVAILABLE = True
except ImportError:
    SmartBulb = SmartStrip = Discover = None
    _KASA_AVAILABLE = False

try:
    import miio  # type: ignore

    _MIIO_AVAILABLE = True
except ImportError:
    miio = None
    _MIIO_AVAILABLE = False

try:
    import pyatv  # type: ignore

    _PYATV_AVAILABLE = True
except ImportError:
    pyatv = None
    _PYATV_AVAILABLE = False

try:
    import pychromecast  # type: ignore

    _CHROMECAST_AVAILABLE = True
except ImportError:
    pychromecast = None
    _CHROMECAST_AVAILABLE = False

try:
    from tuya_iot import TuyaOpenAPI as _TuyaOpenAPI, AuthType as _TuyaAuthType  # type: ignore

    _TUYA_AVAILABLE = True
    _TUYA_SDK = "iot"
except ImportError:
    try:
        from tuya_connector import TuyaOpenAPI as _TuyaOpenAPI  # type: ignore

        _TUYA_AVAILABLE = True
        _TUYA_SDK = "connector"
        _TuyaAuthType = None
    except ImportError:
        _TuyaOpenAPI = None  # type: ignore
        _TuyaAuthType = None
        _TUYA_AVAILABLE = False
        _TUYA_SDK = ""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SmartHomeResult:
    success: bool
    device: str
    action: str
    detail: str = ""
    error: str = ""


@dataclass
class SmartHomeConfig:
    # Philips Hue
    hue_bridge_ip: str = field(default_factory=lambda: os.getenv("HUE_BRIDGE_IP", ""))
    hue_username: str = field(default_factory=lambda: os.getenv("HUE_USERNAME", ""))

    # TP-Link Kasa (auto-discover or explicit IP list comma-separated)
    kasa_device_ips: str = field(default_factory=lambda: os.getenv("KASA_DEVICE_IPS", ""))

    # Xiaomi Mi
    miio_device_ip: str = field(default_factory=lambda: os.getenv("MIIO_DEVICE_IP", ""))
    miio_device_token: str = field(default_factory=lambda: os.getenv("MIIO_DEVICE_TOKEN", ""))
    miio_device_type: str = field(default_factory=lambda: os.getenv("MIIO_DEVICE_TYPE", "light"))

    # Apple TV
    atv_identifier: str = field(default_factory=lambda: os.getenv("ATV_IDENTIFIER", ""))

    # Chromecast (auto-discover or friendly name)
    chromecast_name: str = field(default_factory=lambda: os.getenv("CHROMECAST_NAME", ""))

    # Tuya Cloud API
    tuya_client_id: str = field(default_factory=lambda: os.getenv("TUYA_CLIENT_ID", ""))
    tuya_client_secret: str = field(default_factory=lambda: os.getenv("TUYA_CLIENT_SECRET", ""))
    tuya_device_ids: str = field(default_factory=lambda: os.getenv("TUYA_DEVICE_IDS", ""))
    tuya_region: str = field(default_factory=lambda: os.getenv("TUYA_REGION", "eu"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro) -> Any:
    """Run a coroutine from synchronous code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=15)
        return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)


def _color_name_to_rgb(color: str) -> tuple[int, int, int]:
    table = {
        "red": (255, 0, 0),
        "green": (0, 200, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 220, 0),
        "purple": (150, 0, 200),
        "white": (255, 255, 255),
        "warmwhite": (255, 200, 100),
        "orange": (255, 130, 0),
        "cyan": (0, 220, 220),
        "pink": (255, 100, 150),
    }
    return table.get(str(color).lower().replace(" ", ""), (255, 255, 255))


def _rgb_to_hue_xy(r: int, g: int, b: int) -> tuple[float, float]:
    """Convert RGB (0-255) to CIE xy for Hue API."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    r = pow((r + 0.055) / 1.055, 2.4) if r > 0.04045 else r / 12.92
    g = pow((g + 0.055) / 1.055, 2.4) if g > 0.04045 else g / 12.92
    b = pow((b + 0.055) / 1.055, 2.4) if b > 0.04045 else b / 12.92
    X = r * 0.664511 + g * 0.154324 + b * 0.162028
    Y = r * 0.283881 + g * 0.668433 + b * 0.047685
    Z = r * 0.000088 + g * 0.072310 + b * 0.986039
    denom = X + Y + Z
    if denom == 0:
        return (0.3127, 0.3290)
    return round(X / denom, 4), round(Y / denom, 4)


# ---------------------------------------------------------------------------
# Philips Hue
# ---------------------------------------------------------------------------


class _HueDriver:
    def __init__(self, ip: str, username: str):
        self._ip = ip
        self._username = username
        self._bridge: Any = None
        self._lock = threading.Lock()

    def _connect(self) -> bool:
        if not _HUE_AVAILABLE or not self._ip:
            return False
        with self._lock:
            if self._bridge:
                return True
            try:
                self._bridge = HueBridge(self._ip)
                if self._username:
                    self._bridge.username = self._username
                self._bridge.connect()
                logger.info("Hue bridge connected at %s", self._ip)
                return True
            except Exception as exc:
                logger.warning("Hue connect failed: %s", exc)
                self._bridge = None
                return False

    def set_all_lights(self, on: bool, brightness: float = 1.0, color: str = "") -> SmartHomeResult:
        if not self._connect():
            return SmartHomeResult(False, "hue", "set_lights", error="Not connected")
        try:
            bri = max(1, min(254, int(brightness * 254)))
            state: dict[str, Any] = {"on": on, "bri": bri, "transitiontime": 10}
            if color and on:
                rgb = _color_name_to_rgb(color)
                x, y = _rgb_to_hue_xy(*rgb)
                state["xy"] = [x, y]
            lights = self._bridge.lights
            for light in lights:
                self._bridge.set_light(light.light_id, state)
            action = "on" if on else "off"
            logger.info("Hue: all lights %s (bri=%.0f%%)", action, brightness * 100)
            return SmartHomeResult(True, "hue", "set_lights", detail=f"All lights {action}")
        except Exception as exc:
            logger.warning("Hue set_lights failed: %s", exc)
            return SmartHomeResult(False, "hue", "set_lights", error=str(exc))

    def set_scene(self, scene_name: str) -> SmartHomeResult:
        if not self._connect():
            return SmartHomeResult(False, "hue", "set_scene", error="Not connected")
        try:
            groups = self._bridge.groups
            if groups:
                self._bridge.set_group(groups[0].group_id, "scene", scene_name)
            return SmartHomeResult(True, "hue", "set_scene", detail=scene_name)
        except Exception as exc:
            return SmartHomeResult(False, "hue", "set_scene", error=str(exc))

    def bedtime_scene(self) -> SmartHomeResult:
        """Warm dim lighting for sleep prep."""
        if not self._connect():
            return SmartHomeResult(False, "hue", "bedtime", error="Not connected")
        try:
            lights = self._bridge.lights
            for light in lights:
                self._bridge.set_light(
                    light.light_id,
                    {
                        "on": True,
                        "bri": 30,
                        "ct": 500,
                        "transitiontime": 30,
                    },
                )
            return SmartHomeResult(True, "hue", "bedtime", detail="Warm dim bedtime lighting")
        except Exception as exc:
            return SmartHomeResult(False, "hue", "bedtime", error=str(exc))

    def sunrise_alarm(self) -> SmartHomeResult:
        """Gradually brighten from dim red to full daylight over 30 min."""
        if not self._connect():
            return SmartHomeResult(False, "hue", "sunrise", error="Not connected")
        try:
            lights = self._bridge.lights
            for light in lights:
                self._bridge.set_light(
                    light.light_id,
                    {
                        "on": True,
                        "bri": 254,
                        "ct": 153,
                        "transitiontime": 18000,
                    },
                )
            return SmartHomeResult(
                True, "hue", "sunrise", detail="Sunrise alarm started (30 min ramp)"
            )
        except Exception as exc:
            return SmartHomeResult(False, "hue", "sunrise", error=str(exc))

    def turn_off(self) -> SmartHomeResult:
        return self.set_all_lights(False)


# ---------------------------------------------------------------------------
# TP-Link Kasa
# ---------------------------------------------------------------------------


class _KasaDriver:
    def __init__(self, device_ips: str):
        self._ips = [ip.strip() for ip in device_ips.split(",") if ip.strip()]
        self._discovered: list[Any] = []

    async def _get_devices(self) -> list[Any]:
        if not _KASA_AVAILABLE:
            return []
        if self._discovered:
            return self._discovered
        try:
            if self._ips:
                devices = []
                for ip in self._ips:
                    try:
                        dev = SmartBulb(ip)
                        await dev.update()
                        devices.append(dev)
                    except Exception:
                        try:
                            dev = SmartStrip(ip)
                            await dev.update()
                            devices.append(dev)
                        except Exception:
                            pass
            else:
                found = await Discover.discover()
                devices = list(found.values())
                for d in devices:
                    await d.update()
            self._discovered = devices
            logger.info("Kasa: %d device(s) found", len(devices))
            return devices
        except Exception as exc:
            logger.warning("Kasa discover failed: %s", exc)
            return []

    def set_all(self, on: bool, brightness: float = 1.0) -> SmartHomeResult:
        if not _KASA_AVAILABLE:
            return SmartHomeResult(False, "kasa", "set_all", error="python-kasa not installed")

        async def _run():
            devices = await self._get_devices()
            if not devices:
                return SmartHomeResult(False, "kasa", "set_all", error="No devices found")
            bri = max(1, min(100, int(brightness * 100)))
            for dev in devices:
                try:
                    if on:
                        await dev.turn_on()
                        if hasattr(dev, "set_brightness"):
                            await dev.set_brightness(bri)
                    else:
                        await dev.turn_off()
                except Exception as exc:
                    logger.warning("Kasa device error: %s", exc)
            action = "on" if on else "off"
            return SmartHomeResult(
                True, "kasa", "set_all", detail=f"{len(devices)} device(s) {action}"
            )

        try:
            return _run_async(_run())
        except Exception as exc:
            return SmartHomeResult(False, "kasa", "set_all", error=str(exc))

    def bedtime(self) -> SmartHomeResult:
        return self.set_all(True, brightness=0.10)

    def turn_off(self) -> SmartHomeResult:
        return self.set_all(False)

    def cut_power(self) -> SmartHomeResult:
        """Cut power to TV/entertainment outlets at bedtime."""
        if not _KASA_AVAILABLE:
            return SmartHomeResult(False, "kasa", "cut_power", error="python-kasa not installed")

        async def _run():
            devices = await self._get_devices()
            strips = [d for d in devices if isinstance(d, SmartStrip)]
            if not strips:
                return self.turn_off()
            for strip in strips:
                try:
                    await strip.turn_off()
                except Exception as exc:
                    logger.warning("Kasa strip off failed: %s", exc)
            return SmartHomeResult(True, "kasa", "cut_power", detail="Smart strips powered off")

        try:
            return _run_async(_run())
        except Exception as exc:
            return SmartHomeResult(False, "kasa", "cut_power", error=str(exc))


# ---------------------------------------------------------------------------
# Xiaomi Mi (miio)
# ---------------------------------------------------------------------------


class _MiioDriver:
    def __init__(self, ip: str, token: str, device_type: str = "light"):
        self._ip = ip
        self._token = token
        self._type = device_type
        self._device: Any = None

    def _connect(self) -> bool:
        if not _MIIO_AVAILABLE or not self._ip or not self._token:
            return False
        if self._device:
            return True
        try:
            if self._type == "fan":
                self._device = miio.AirHumidifier(self._ip, self._token)
            elif self._type == "purifier":
                self._device = miio.AirPurifier(self._ip, self._token)
            else:
                self._device = miio.Yeelight(self._ip, self._token)
            logger.info("Miio %s connected at %s", self._type, self._ip)
            return True
        except Exception as exc:
            logger.warning("Miio connect failed: %s", exc)
            return False

    def set_brightness(self, brightness: float) -> SmartHomeResult:
        if not self._connect():
            return SmartHomeResult(False, "miio", "set_brightness", error="Not connected")
        try:
            bri = max(1, min(100, int(brightness * 100)))
            self._device.set_brightness(bri)
            return SmartHomeResult(True, "miio", "set_brightness", detail=f"Brightness {bri}%")
        except Exception as exc:
            return SmartHomeResult(False, "miio", "set_brightness", error=str(exc))

    def set_color_temp(self, kelvin: int) -> SmartHomeResult:
        if not self._connect():
            return SmartHomeResult(False, "miio", "set_color_temp", error="Not connected")
        try:
            self._device.set_color_temp(max(1700, min(6500, kelvin)))
            return SmartHomeResult(True, "miio", "set_color_temp", detail=f"{kelvin}K")
        except Exception as exc:
            return SmartHomeResult(False, "miio", "set_color_temp", error=str(exc))

    def turn_off(self) -> SmartHomeResult:
        if not self._connect():
            return SmartHomeResult(False, "miio", "turn_off", error="Not connected")
        try:
            self._device.off()
            return SmartHomeResult(True, "miio", "turn_off")
        except Exception as exc:
            return SmartHomeResult(False, "miio", "turn_off", error=str(exc))


# ---------------------------------------------------------------------------
# Apple TV
# ---------------------------------------------------------------------------


class _AppleTVDriver:
    def __init__(self, identifier: str):
        self._identifier = identifier

    async def _get_atv(self):
        if not _PYATV_AVAILABLE or not self._identifier:
            return None
        try:
            devices = await pyatv.scan(None, identifier=self._identifier, timeout=5)
            if not devices:
                return None
            return await pyatv.connect(devices[0], None)
        except Exception as exc:
            logger.warning("AppleTV scan failed: %s", exc)
            return None

    def pause(self) -> SmartHomeResult:
        if not _PYATV_AVAILABLE:
            return SmartHomeResult(False, "appletv", "pause", error="pyatv not installed")

        async def _run():
            atv = await self._get_atv()
            if not atv:
                return SmartHomeResult(False, "appletv", "pause", error="Device not found")
            try:
                await atv.remote_control.pause()
                atv.close()
                return SmartHomeResult(True, "appletv", "pause", detail="Media paused")
            except Exception as exc:
                atv.close()
                return SmartHomeResult(False, "appletv", "pause", error=str(exc))

        try:
            return _run_async(_run())
        except Exception as exc:
            return SmartHomeResult(False, "appletv", "pause", error=str(exc))

    def sleep_now(self) -> SmartHomeResult:
        if not _PYATV_AVAILABLE:
            return SmartHomeResult(False, "appletv", "sleep", error="pyatv not installed")

        async def _run():
            atv = await self._get_atv()
            if not atv:
                return SmartHomeResult(False, "appletv", "sleep", error="Device not found")
            try:
                await atv.power.turn_off()
                atv.close()
                return SmartHomeResult(True, "appletv", "sleep", detail="Apple TV sleeping")
            except Exception as exc:
                atv.close()
                return SmartHomeResult(False, "appletv", "sleep", error=str(exc))

        try:
            return _run_async(_run())
        except Exception as exc:
            return SmartHomeResult(False, "appletv", "sleep", error=str(exc))


# ---------------------------------------------------------------------------
# Chromecast
# ---------------------------------------------------------------------------


class _ChromecastDriver:
    def __init__(self, device_name: str):
        self._name = device_name
        self._cast: Any = None

    def _connect(self) -> bool:
        if not _CHROMECAST_AVAILABLE:
            return False
        try:
            chromecasts, browser = pychromecast.get_listed_chromecasts(
                friendly_names=[self._name] if self._name else None
            )
            if not chromecasts:
                chromecasts, browser = pychromecast.get_chromecasts()
            if not chromecasts:
                return False
            self._cast = chromecasts[0]
            self._cast.wait()
            logger.info("Chromecast connected: %s", self._cast.name)
            return True
        except Exception as exc:
            logger.warning("Chromecast connect failed: %s", exc)
            return False

    def pause(self) -> SmartHomeResult:
        if not _CHROMECAST_AVAILABLE:
            return SmartHomeResult(False, "chromecast", "pause", error="pychromecast not installed")
        if not self._connect():
            return SmartHomeResult(False, "chromecast", "pause", error="No Chromecast found")
        try:
            mc = self._cast.media_controller
            mc.pause()
            return SmartHomeResult(True, "chromecast", "pause", detail="Media paused")
        except Exception as exc:
            return SmartHomeResult(False, "chromecast", "pause", error=str(exc))

    def stop(self) -> SmartHomeResult:
        if not _CHROMECAST_AVAILABLE:
            return SmartHomeResult(False, "chromecast", "stop", error="pychromecast not installed")
        if not self._connect():
            return SmartHomeResult(False, "chromecast", "stop", error="No Chromecast found")
        try:
            self._cast.quit_app()
            return SmartHomeResult(True, "chromecast", "stop", detail="Chromecast stopped")
        except Exception as exc:
            return SmartHomeResult(False, "chromecast", "stop", error=str(exc))


# ---------------------------------------------------------------------------
# Tuya Cloud API
# ---------------------------------------------------------------------------

_TUYA_REGION_ENDPOINTS: dict[str, str] = {
    "us": "https://openapi.tuyaus.com",
    "eu": "https://openapi.tuyaeu.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}


def _rgb_to_tuya_hsv(r: int, g: int, b: int) -> dict:
    """Convert RGB (0-255) to Tuya HSV format (h: 0-360, s: 0-1000, v: 0-1000)."""
    r_, g_, b_ = r / 255.0, g / 255.0, b / 255.0
    cmax = max(r_, g_, b_)
    cmin = min(r_, g_, b_)
    delta = cmax - cmin

    if delta == 0:
        h = 0.0
    elif cmax == r_:
        h = 60.0 * (((g_ - b_) / delta) % 6)
    elif cmax == g_:
        h = 60.0 * (((b_ - r_) / delta) + 2)
    else:
        h = 60.0 * (((r_ - g_) / delta) + 4)

    s = 0.0 if cmax == 0 else (delta / cmax)
    return {
        "h": round(h),
        "s": round(s * 1000),
        "v": round(cmax * 1000),
    }


class _TuyaDriver:
    """Tuya Cloud API driver — supports tuya-iot-py-sdk and tuya-connector-python."""

    def __init__(self, client_id: str, client_secret: str, device_ids: str, region: str = "eu"):
        self._client_id = client_id
        self._client_secret = client_secret
        self._device_ids = [d.strip() for d in device_ids.split(",") if d.strip()]
        self._endpoint = _TUYA_REGION_ENDPOINTS.get(region.lower(), _TUYA_REGION_ENDPOINTS["eu"])
        self._api: Any = None
        self._lock = threading.Lock()

    def _connect(self) -> bool:
        if (
            not _TUYA_AVAILABLE
            or not self._client_id
            or not self._client_secret
            or not self._device_ids
        ):
            return False
        with self._lock:
            if self._api is not None:
                return True
            try:
                if _TUYA_SDK == "iot" and _TuyaAuthType is not None:
                    api = _TuyaOpenAPI(
                        self._endpoint, self._client_id, self._client_secret, _TuyaAuthType.APIKEY
                    )
                else:
                    api = _TuyaOpenAPI(self._endpoint, self._client_id, self._client_secret)
                resp = api.connect()
                if resp.get("success") is False:
                    logger.warning("Tuya connect failed: %s", resp)
                    return False
                self._api = api
                logger.info(
                    "Tuya Cloud API connected (%s, %d device(s))",
                    self._endpoint,
                    len(self._device_ids),
                )
                return True
            except Exception as exc:
                logger.warning("Tuya connect error: %s", exc)
                self._api = None
                return False

    def _send_commands(self, device_id: str, commands: list[dict]) -> bool:
        if not self._api:
            return False
        try:
            resp = self._api.post(
                f"/v1.0/iot-03/devices/{device_id}/commands",
                {"commands": commands},
            )
            if resp.get("success") is False:
                logger.warning("Tuya command failed for %s: %s", device_id, resp)
                return False
            return True
        except Exception as exc:
            logger.warning("Tuya send_commands error: %s", exc)
            return False

    def _send_all(self, commands: list[dict]) -> SmartHomeResult:
        if not self._connect():
            return SmartHomeResult(False, "tuya", "command", error="Not connected")
        ok_count = 0
        for device_id in self._device_ids:
            if self._send_commands(device_id, commands):
                ok_count += 1
        success = ok_count > 0
        return SmartHomeResult(
            success,
            "tuya",
            "command",
            detail=f"{ok_count}/{len(self._device_ids)} device(s) OK",
            error="" if success else "All devices failed",
        )

    def set_all(self, on: bool, brightness: float = 1.0, color: str = "") -> SmartHomeResult:
        commands: list[dict] = [{"code": "switch_led", "value": on}]
        if on:
            bri = max(10, min(1000, int(brightness * 1000)))
            if color and color not in ("white", "warmwhite"):
                rgb = _color_name_to_rgb(color)
                hsv = _rgb_to_tuya_hsv(*rgb)
                hsv["v"] = bri
                commands += [
                    {"code": "work_mode", "value": "colour"},
                    {"code": "colour_data_v2", "value": hsv},
                ]
            else:
                temp = 200 if color == "warmwhite" else 500
                commands += [
                    {"code": "work_mode", "value": "white"},
                    {"code": "bright_value_v2", "value": bri},
                    {"code": "temp_value_v2", "value": temp},
                ]
        return self._send_all(commands)

    def bedtime(self) -> SmartHomeResult:
        """Warm dim amber at 10% brightness."""
        commands = [
            {"code": "switch_led", "value": True},
            {"code": "work_mode", "value": "white"},
            {"code": "bright_value_v2", "value": 100},
            {"code": "temp_value_v2", "value": 100},
        ]
        return self._send_all(commands)

    def turn_off(self) -> SmartHomeResult:
        return self._send_all([{"code": "switch_led", "value": False}])

    def sunrise_alarm(self) -> SmartHomeResult:
        """Start at dim warm white; device-side timers handle the ramp if supported."""
        commands = [
            {"code": "switch_led", "value": True},
            {"code": "work_mode", "value": "white"},
            {"code": "bright_value_v2", "value": 300},
            {"code": "temp_value_v2", "value": 300},
        ]
        return self._send_all(commands)


# ---------------------------------------------------------------------------
# Unified SmartHomeController
# ---------------------------------------------------------------------------


class SmartHomeController:
    """Single entry point for all smart home device actions.

    Instantiate once at startup. All methods return SmartHomeResult so callers
    can decide whether to surface errors to the user.
    """

    def __init__(self, config: SmartHomeConfig | None = None):
        cfg = config or SmartHomeConfig()
        self.hue = _HueDriver(cfg.hue_bridge_ip, cfg.hue_username)
        self.kasa = _KasaDriver(cfg.kasa_device_ips)
        self.miio = _MiioDriver(cfg.miio_device_ip, cfg.miio_device_token, cfg.miio_device_type)
        self.tuya = _TuyaDriver(
            cfg.tuya_client_id, cfg.tuya_client_secret, cfg.tuya_device_ids, cfg.tuya_region
        )
        self.appletv = _AppleTVDriver(cfg.atv_identifier)
        self.chromecast = _ChromecastDriver(cfg.chromecast_name)

    # ------------------------------------------------------------------
    # High-level sleep automation actions
    # ------------------------------------------------------------------

    def bedtime_mode(self, brightness: float = 0.12) -> list[SmartHomeResult]:
        """Full bedroom bedtime prep — dim all lights, pause media."""
        results = [
            self.hue.bedtime_scene(),
            self.kasa.bedtime(),
            self.miio.set_brightness(brightness),
            self.miio.set_color_temp(2700),
            self.tuya.bedtime(),
            self.appletv.pause(),
            self.chromecast.pause(),
        ]
        _log_results("bedtime_mode", results)
        return results

    def lights_out(self) -> list[SmartHomeResult]:
        """Turn off all lights and stop media."""
        results = [
            self.hue.turn_off(),
            self.kasa.turn_off(),
            self.miio.turn_off(),
            self.tuya.turn_off(),
            self.appletv.sleep_now(),
            self.chromecast.stop(),
        ]
        _log_results("lights_out", results)
        return results

    def sunrise_alarm(self) -> list[SmartHomeResult]:
        """Gradual wake-up lighting on all devices."""
        results = [
            self.hue.sunrise_alarm(),
            self.kasa.set_all(True, brightness=0.30),
            self.miio.set_brightness(0.30),
            self.miio.set_color_temp(3000),
            self.tuya.sunrise_alarm(),
        ]
        _log_results("sunrise_alarm", results)
        return results

    def set_lights(
        self, color: str = "", brightness: float = 0.8, on: bool = True
    ) -> list[SmartHomeResult]:
        """Set all lights to a color and brightness."""
        results = [
            self.hue.set_all_lights(on, brightness, color),
            self.kasa.set_all(on, brightness),
            self.miio.set_brightness(brightness),
            self.tuya.set_all(on, brightness, color),
        ]
        if color:
            if color in ("warmwhite", "orange", "warm"):
                results.append(self.miio.set_color_temp(2700))
            elif color in ("white", "cool", "cyan"):
                results.append(self.miio.set_color_temp(5500))
        _log_results("set_lights", results)
        return results

    def cut_entertainment_power(self) -> list[SmartHomeResult]:
        """Cut power to TV/entertainment smart plugs at bedtime."""
        results = [
            self.kasa.cut_power(),
            self.appletv.sleep_now(),
            self.chromecast.stop(),
        ]
        _log_results("cut_entertainment_power", results)
        return results

    def available_drivers(self) -> dict[str, bool]:
        return {
            "hue": _HUE_AVAILABLE,
            "kasa": _KASA_AVAILABLE,
            "miio": _MIIO_AVAILABLE,
            "tuya": _TUYA_AVAILABLE,
            "appletv": _PYATV_AVAILABLE,
            "chromecast": _CHROMECAST_AVAILABLE,
        }


def _log_results(action: str, results: list[SmartHomeResult]) -> None:
    ok = sum(1 for r in results if r.success)
    total = len(results)
    logger.info("SmartHome %s: %d/%d succeeded", action, ok, total)
    for r in results:
        if not r.success and r.error:
            logger.debug("  %s/%s failed: %s", r.device, r.action, r.error)


# ---------------------------------------------------------------------------
# Module-level singleton (lazy init from env vars)
# ---------------------------------------------------------------------------

_controller: SmartHomeController | None = None
_controller_lock = threading.Lock()


def get_controller() -> SmartHomeController:
    """Return the module-level SmartHomeController singleton."""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = SmartHomeController()
    return _controller
