"""LED and WS2812 helper functions for color parsing, brightness, and hardware configuration."""

from __future__ import annotations

import re

from config import settings
from led.led_control import LEDController

ARABIC_COLOR_MAP = {
    "احمر": "red",
    "أحمر": "red",
    "اخضر": "green",
    "أخضر": "green",
    "ازرق": "blue",
    "أزرق": "blue",
    "اصفر": "yellow",
    "أصفر": "yellow",
    "بنفسجي": "purple",
    "ابيض": "white",
    "أبيض": "white",
    "سماوي": "cyan",
    "برتقالي": "orange",
    "وردي": "pink",
}

def _clamp_percent(value, default_value: int = 35) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return max(0, min(100, int(default_value)))

def _safe_int(value, default_value: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default_value)

    if min_value is not None:
        parsed = max(int(min_value), parsed)
    if max_value is not None:
        parsed = min(int(max_value), parsed)
    return parsed

def ensure_music_led_preferences(profile: dict) -> dict:
    prefs = profile.setdefault("preferences", {})
    prefs.setdefault("music_lights_enabled", True)
    prefs.setdefault("music_lights_mode", "pulse")
    prefs.setdefault("music_lights_energy", "calm")
    prefs.setdefault("music_lights_target", "both")
    prefs.setdefault("music_lights_brightness_percent", 35)
    prefs.setdefault("music_lights_night_brightness_percent", 35)

    prefs["music_lights_mode"] = str(prefs.get("music_lights_mode", "pulse")).strip().lower()
    if prefs["music_lights_mode"] not in ("pulse", "wave", "spectrum"):
        prefs["music_lights_mode"] = "pulse"

    prefs["music_lights_energy"] = str(prefs.get("music_lights_energy", "calm")).strip().lower()
    if prefs["music_lights_energy"] not in ("calm", "energetic"):
        prefs["music_lights_energy"] = "calm"

    prefs["music_lights_target"] = str(prefs.get("music_lights_target", "both")).strip().lower()
    if prefs["music_lights_target"] not in ("both", "user_only"):
        prefs["music_lights_target"] = "both"

    prefs["music_lights_brightness_percent"] = _clamp_percent(
        prefs.get("music_lights_brightness_percent", 35), default_value=35
    )
    prefs["music_lights_night_brightness_percent"] = _clamp_percent(
        prefs.get("music_lights_night_brightness_percent", 35), default_value=35
    )
    return prefs

def apply_music_led_preferences(led: LEDController, profile: dict, active: bool | None = None):
    prefs = ensure_music_led_preferences(profile)
    runtime_flags = profile.setdefault("runtime_flags", {})
    if active is not None:
        runtime_flags["music_playback_active"] = bool(active)
    desired_active = bool(runtime_flags.get("music_playback_active", False))

    led.configure_music_reactive(
        enabled=bool(prefs.get("music_lights_enabled", True)),
        active=desired_active,
        mode=str(prefs.get("music_lights_mode", "pulse")),
        energy=str(prefs.get("music_lights_energy", "calm")),
        target=str(prefs.get("music_lights_target", "both")),
        brightness=float(_clamp_percent(prefs.get("music_lights_brightness_percent", 35), 35)) / 100.0,
    )

def ensure_hardware_shape(profile: dict):
    profile.setdefault("hardware", {})
    hardware = profile["hardware"]
    hardware.setdefault("user_strip_pin", int(settings.user_strip_pin))
    hardware.setdefault("state_strip_pin", int(settings.state_strip_pin))
    hardware.setdefault("user_strip_led_count", int(settings.user_strip_led_count))
    hardware.setdefault("state_strip_led_count", int(settings.state_strip_led_count))

def _to_int_or_default(value, default_value: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default_value)

def apply_led_hardware_config(led: LEDController, profile: dict):
    ensure_hardware_shape(profile)
    hardware = profile.get("hardware", {})

    user_pin = max(0, _to_int_or_default(hardware.get("user_strip_pin"), settings.user_strip_pin))
    state_pin = max(0, _to_int_or_default(hardware.get("state_strip_pin"), settings.state_strip_pin))
    user_count = max(
        1,
        _to_int_or_default(hardware.get("user_strip_led_count"), settings.user_strip_led_count),
    )
    state_count = max(
        1,
        _to_int_or_default(hardware.get("state_strip_led_count"), settings.state_strip_led_count),
    )

    hardware["user_strip_pin"] = user_pin
    hardware["state_strip_pin"] = state_pin
    hardware["user_strip_led_count"] = user_count
    hardware["state_strip_led_count"] = state_count

    led.update_hardware_config(
        user_strip_pin=user_pin,
        state_strip_pin=state_pin,
        user_strip_led_count=user_count,
        state_strip_led_count=state_count,
    )

def _extract_color_from_normalized_text(normalized: str) -> str:
    named = tuple(LEDController.NAMED_COLORS.keys())
    for name in named:
        if f" {name} " in f" {normalized} ":
            return name

    for ar_name, en_name in ARABIC_COLOR_MAP.items():
        if f" {ar_name.lower()} " in f" {normalized} ":
            return en_name

    hex_match = re.search(r"#[0-9a-f]{6}", normalized)
    if hex_match:
        return hex_match.group(0)
    return ""

