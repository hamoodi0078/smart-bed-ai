"""Circadian rhythm automation for Smart Bed AI.

Dynamically adjusts LED color temperature throughout the day to match
natural light patterns. Uses astral for precise location-aware sunrise/sunset
times. Falls back to hardcoded defaults if astral is unavailable.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone, date
from typing import Any

logger = logging.getLogger("scenes.circadian_engine")

# ---------------------------------------------------------------------------
# astral — real sunrise/sunset (optional, falls back to defaults)
# ---------------------------------------------------------------------------

try:
    from astral import LocationInfo  # type: ignore
    from astral.sun import sun as astral_sun

    _ASTRAL_AVAILABLE = True
except ImportError:
    _ASTRAL_AVAILABLE = False
    logger.debug("astral not installed — using hardcoded sunrise/sunset hours")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Color temperature presets (Kelvin -> hex approximation)
COLOR_TEMP_MAP = {
    6500: {"hex": "#F5F5FF", "name": "cool_daylight"},
    5000: {"hex": "#FFF5F0", "name": "neutral_white"},
    4500: {"hex": "#FFFAF0", "name": "bright_warm"},
    3500: {"hex": "#FFE4C4", "name": "warm_white"},
    3000: {"hex": "#FFD9B3", "name": "soft_warm"},
    2700: {"hex": "#FFC87C", "name": "amber"},
    2200: {"hex": "#FF9933", "name": "deep_amber"},
    1800: {"hex": "#FF6600", "name": "candlelight"},
}


class CircadianEngine:
    """Manages automatic color temperature transitions throughout the day."""

    def __init__(
        self,
        *,
        sunrise_hour: int = 6,
        sunset_hour: int = 18,
        transition_duration_minutes: int = 30,
        blue_light_reduction_hours_before_bed: float = 2.0,
        latitude: float = 0.0,
        longitude: float = 0.0,
        timezone_name: str = "UTC",
        city_name: str = "Kuwait City",
    ):
        self._sunrise = max(4, min(10, int(sunrise_hour)))
        self._sunset = max(16, min(22, int(sunset_hour)))
        self._transition_min = max(10, int(transition_duration_minutes))
        self._blue_reduction_hours = max(1.0, float(blue_light_reduction_hours_before_bed))
        self._latitude = float(latitude)
        self._longitude = float(longitude)
        self._timezone_name = str(timezone_name or "UTC")
        self._city_name = str(city_name or "Kuwait City")
        self._sun_cache: dict[str, dict] = {}  # date_iso -> {"sunrise": hour, "sunset": hour}

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("circadian", {})
        c = profile["circadian"]
        c.setdefault("enabled", True)
        c.setdefault("sunrise_hour", self._sunrise)
        c.setdefault("sunset_hour", self._sunset)
        c.setdefault("intensity_multiplier", 1.0)
        c.setdefault("last_applied_phase", "")

    # ------------------------------------------------------------------
    # Phase schedule
    # ------------------------------------------------------------------

    PHASES = [
        {"name": "pre_dawn", "start_hour": 4, "end_hour": 6, "kelvin": 2200, "brightness": 0.05},
        {"name": "sunrise", "start_hour": 6, "end_hour": 8, "kelvin": 4500, "brightness": 0.50},
        {"name": "morning", "start_hour": 8, "end_hour": 12, "kelvin": 6500, "brightness": 0.70},
        {"name": "afternoon", "start_hour": 12, "end_hour": 17, "kelvin": 5000, "brightness": 0.60},
        {
            "name": "evening_transition",
            "start_hour": 17,
            "end_hour": 19,
            "kelvin": 3500,
            "brightness": 0.45,
        },
        {"name": "evening", "start_hour": 19, "end_hour": 21, "kelvin": 3000, "brightness": 0.35},
        {"name": "wind_down", "start_hour": 21, "end_hour": 23, "kelvin": 2700, "brightness": 0.20},
        {
            "name": "sleep_prep",
            "start_hour": 23,
            "end_hour": 24,
            "kelvin": 2200,
            "brightness": 0.10,
        },
        {"name": "night", "start_hour": 0, "end_hour": 4, "kelvin": 1800, "brightness": 0.02},
    ]

    def _build_dynamic_phases(self, sun: dict[str, int]) -> list[dict[str, Any]]:
        """Rebuild the phase schedule using real sunrise/sunset hours."""
        sr = sun["sunrise"]  # e.g. 5 in summer
        ss = sun["sunset"]  # e.g. 19 in summer
        dawn = sun["dawn"]  # sr - 1
        dusk = sun["dusk"]  # ss + 1
        return [
            {
                "name": "pre_dawn",
                "start_hour": dawn - 1,
                "end_hour": dawn,
                "kelvin": 2200,
                "brightness": 0.05,
            },
            {
                "name": "sunrise",
                "start_hour": dawn,
                "end_hour": sr + 1,
                "kelvin": 4500,
                "brightness": 0.50,
            },
            {
                "name": "morning",
                "start_hour": sr + 1,
                "end_hour": 12,
                "kelvin": 6500,
                "brightness": 0.70,
            },
            {
                "name": "afternoon",
                "start_hour": 12,
                "end_hour": ss - 2,
                "kelvin": 5000,
                "brightness": 0.60,
            },
            {
                "name": "evening_transition",
                "start_hour": ss - 2,
                "end_hour": ss,
                "kelvin": 3500,
                "brightness": 0.45,
            },
            {
                "name": "evening",
                "start_hour": ss,
                "end_hour": dusk + 1,
                "kelvin": 3000,
                "brightness": 0.35,
            },
            {
                "name": "wind_down",
                "start_hour": dusk + 1,
                "end_hour": dusk + 3,
                "kelvin": 2700,
                "brightness": 0.20,
            },
            {
                "name": "sleep_prep",
                "start_hour": dusk + 3,
                "end_hour": 24,
                "kelvin": 2200,
                "brightness": 0.10,
            },
            {
                "name": "night",
                "start_hour": 0,
                "end_hour": dawn - 1,
                "kelvin": 1800,
                "brightness": 0.02,
            },
        ]

    def get_current_phase(self, now: datetime | None = None) -> dict[str, Any]:
        """Determine the current circadian phase using real astral sunrise/sunset."""
        now = now or datetime.now()
        sun = self._get_sun_times(now.date())
        phases = self._build_dynamic_phases(sun)

        hour = now.hour
        minute = now.minute
        current_minutes = hour * 60 + minute

        for phase in phases:
            start = phase["start_hour"] * 60
            end = phase["end_hour"] * 60
            if start <= end:
                if start <= current_minutes < end:
                    return dict(phase)
            else:
                if current_minutes >= start or current_minutes < end:
                    return dict(phase)

        return dict(phases[-1])

    def get_interpolated_settings(self, now: datetime | None = None) -> dict[str, Any]:
        """Get smoothly interpolated color temperature and brightness using real sun times."""
        now = now or datetime.now()
        sun = self._get_sun_times(now.date())
        phases = self._build_dynamic_phases(sun)

        hour = now.hour
        minute = now.minute
        current_minutes = hour * 60 + minute

        current_phase = self.get_current_phase(now)
        current_start = current_phase["start_hour"] * 60
        current_end = current_phase["end_hour"] * 60

        if current_end <= current_start:
            current_end += 24 * 60
        if current_minutes < current_start:
            current_minutes += 24 * 60

        phase_duration = max(1, current_end - current_start)
        progress = min(1.0, (current_minutes - current_start) / phase_duration)

        next_phase = self._get_next_phase_from(phases, current_phase["name"])
        kelvin = int(
            current_phase["kelvin"] + (next_phase["kelvin"] - current_phase["kelvin"]) * progress
        )
        brightness = (
            current_phase["brightness"]
            + (next_phase["brightness"] - current_phase["brightness"]) * progress
        )

        color_info = self._kelvin_to_color(kelvin)

        return {
            "phase": current_phase["name"],
            "kelvin": kelvin,
            "brightness": round(max(0.01, min(1.0, brightness)), 3),
            "color_hex": color_info["hex"],
            "color_name": color_info["name"],
            "progress_in_phase": round(progress, 2),
            "next_phase": next_phase["name"],
            "transition_minutes_remaining": int((1.0 - progress) * phase_duration),
            "sunrise_hour": sun["sunrise"],
            "sunset_hour": sun["sunset"],
            "astral_active": _ASTRAL_AVAILABLE and bool(self._latitude),
        }

    # ------------------------------------------------------------------
    # astral-powered sunrise/sunset
    # ------------------------------------------------------------------

    def _get_sun_times(self, for_date: date | None = None) -> dict[str, int]:
        """Return real sunrise/sunset hours from astral, or defaults."""
        target = for_date or datetime.now().date()
        key = target.isoformat()

        if key in self._sun_cache:
            return self._sun_cache[key]

        if _ASTRAL_AVAILABLE and self._latitude and self._longitude:
            try:
                location = LocationInfo(
                    name=self._city_name,
                    region="",
                    timezone=self._timezone_name,
                    latitude=self._latitude,
                    longitude=self._longitude,
                )
                s = astral_sun(location.observer, date=target, tzinfo=self._timezone_name)
                result = {
                    "sunrise": s["sunrise"].hour,
                    "sunset": s["sunset"].hour,
                    "dawn": s["dawn"].hour,
                    "dusk": s["dusk"].hour,
                }
                self._sun_cache[key] = result
                # Keep cache small
                if len(self._sun_cache) > 14:
                    oldest = next(iter(self._sun_cache))
                    del self._sun_cache[oldest]
                logger.debug(
                    "Astral sun times for %s: sunrise=%02d:00 sunset=%02d:00",
                    key,
                    result["sunrise"],
                    result["sunset"],
                )
                return result
            except Exception as exc:
                logger.warning("Astral sun calculation failed: %s", exc)

        return {
            "sunrise": self._sunrise,
            "sunset": self._sunset,
            "dawn": max(4, self._sunrise - 1),
            "dusk": min(22, self._sunset + 1),
        }

    def set_location(self, latitude: float, longitude: float, timezone_name: str = "UTC") -> None:
        """Update location for astral calculations. Clears the sun cache."""
        self._latitude = float(latitude)
        self._longitude = float(longitude)
        self._timezone_name = str(timezone_name or "UTC")
        self._sun_cache.clear()
        logger.info(
            "CircadianEngine location updated: lat=%.4f lon=%.4f tz=%s",
            self._latitude,
            self._longitude,
            self._timezone_name,
        )

    def update_sunrise_sunset(self, sunrise_hour: int, sunset_hour: int) -> None:
        """Override sunrise/sunset hours (e.g. from weather API). Clears astral cache."""
        self._sunrise = max(4, min(10, int(sunrise_hour)))
        self._sunset = max(16, min(22, int(sunset_hour)))
        self._sun_cache.clear()

    # ------------------------------------------------------------------
    # Automation evaluation
    # ------------------------------------------------------------------

    def evaluate(self, profile: dict, now: datetime | None = None) -> dict[str, Any] | None:
        """Check if circadian lighting should be updated. Returns LED action or None."""
        now = now or datetime.now()
        self.ensure_shape(profile)

        if not profile.get("circadian", {}).get("enabled", True):
            return None

        settings = self.get_interpolated_settings(now)
        last_phase = profile.get("circadian", {}).get("last_applied_phase", "")

        if settings["phase"] == last_phase:
            return None

        profile["circadian"]["last_applied_phase"] = settings["phase"]
        multiplier = float(profile.get("circadian", {}).get("intensity_multiplier", 1.0) or 1.0)

        return {
            "type": "led_scene",
            "action": "circadian_update",
            "color": settings["color_hex"],
            "brightness": round(settings["brightness"] * multiplier, 3),
            "animation": "solid",
            "kelvin": settings["kelvin"],
            "phase": settings["phase"],
        }

    # ------------------------------------------------------------------
    # Blue light schedule
    # ------------------------------------------------------------------

    def get_blue_light_status(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Check if blue light should be reduced based on bedtime proximity."""
        now = now or datetime.now()
        self.ensure_shape(profile)

        bedtime_hour = 23
        bed_hist = profile.get("sleep", {}).get("bedtime_history", [])
        if bed_hist:
            try:
                dt = datetime.fromisoformat(str(bed_hist[-1]))
                bedtime_hour = dt.hour
            except Exception:
                pass

        cutoff_hour = bedtime_hour - self._blue_reduction_hours
        if cutoff_hour < 0:
            cutoff_hour += 24

        current_hour = now.hour + now.minute / 60.0
        should_reduce = current_hour >= cutoff_hour or current_hour < 4

        return {
            "reduce_blue_light": should_reduce,
            "bedtime_hour": bedtime_hour,
            "cutoff_hour": round(cutoff_hour, 1),
            "current_hour": round(current_hour, 1),
            "recommended_kelvin": 2200
            if should_reduce
            else self.get_current_phase(now).get("kelvin", 5000),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_next_phase(self, current_name: str) -> dict[str, Any]:
        return self._get_next_phase_from(self.PHASES, current_name)

    def _get_next_phase_from(self, phases: list[dict], current_name: str) -> dict[str, Any]:
        for i, phase in enumerate(phases):
            if phase["name"] == current_name:
                return dict(phases[(i + 1) % len(phases)])
        return dict(phases[0])

    @staticmethod
    def _kelvin_to_color(kelvin: int) -> dict[str, str]:
        closest = min(COLOR_TEMP_MAP.keys(), key=lambda k: abs(k - kelvin))
        return COLOR_TEMP_MAP[closest]

    def get_full_schedule(self) -> list[dict[str, Any]]:
        """Return the full daily phase schedule."""
        schedule = []
        for phase in self.PHASES:
            color = self._kelvin_to_color(phase["kelvin"])
            schedule.append(
                {
                    "phase": phase["name"],
                    "start_hour": phase["start_hour"],
                    "end_hour": phase["end_hour"],
                    "kelvin": phase["kelvin"],
                    "brightness": phase["brightness"],
                    "color_hex": color["hex"],
                    "color_name": color["name"],
                }
            )
        return schedule
