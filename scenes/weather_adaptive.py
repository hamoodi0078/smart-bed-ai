"""Weather-responsive lighting adaptation for Smart Bed AI.

Adjusts LED brightness and color based on outdoor weather conditions
using OpenWeatherMap via pyowm (primary) with a raw-requests fallback
and a free open-meteo fallback when no API key is configured.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

import requests

try:
    import pyowm
    _PYOWM_AVAILABLE = True
except ImportError:
    pyowm = None  # type: ignore[assignment]
    _PYOWM_AVAILABLE = False

logger = logging.getLogger("scenes.weather_adaptive")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WeatherAdaptive:
    """Adapts LED scenes based on current weather conditions."""

    API_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(
        self,
        *,
        api_key: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
        city: str = "Kuwait City",
        country_code: str = "KW",
        cache_minutes: int = 30,
        timeout_seconds: int = 10,
    ):
        self._api_key = str(api_key or os.getenv("OPENWEATHERMAP_API_KEY", "")).strip()
        self._lat = float(latitude)
        self._lon = float(longitude)
        self._city = str(city).strip()
        self._country = str(country_code).strip()
        self._cache_minutes = max(5, int(cache_minutes))
        self._timeout = max(3, int(timeout_seconds))
        self._cached_weather: dict[str, Any] | None = None
        self._cache_time: datetime | None = None
        self._lock = threading.Lock()

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("weather_adaptive", {})
        wa = profile["weather_adaptive"]
        wa.setdefault("enabled", True)
        wa.setdefault("brightness_boost_cloudy", 0.20)
        wa.setdefault("brightness_boost_rainy", 0.25)
        wa.setdefault("last_condition", "")

    # ------------------------------------------------------------------
    # Weather fetching
    # ------------------------------------------------------------------

    _OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
    _WMO_CONDITION: dict[int, str] = {
        0: "clear", 1: "clouds", 2: "clouds", 3: "clouds",
        45: "fog", 48: "fog",
        51: "drizzle", 53: "drizzle", 55: "drizzle",
        61: "rain", 63: "rain", 65: "rain",
        71: "snow", 73: "snow", 75: "snow",
        80: "rain", 81: "rain", 82: "rain",
        95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
    }

    def _fetch_open_meteo(self) -> dict[str, Any]:
        """Free weather fallback via open-meteo.com — no API key required."""
        if not (self._lat and self._lon):
            return {"available": False, "reason": "No coordinates configured."}
        with self._lock:
            if self._cached_weather and self._cache_time:
                elapsed = (_utcnow() - self._cache_time).total_seconds() / 60.0
                if elapsed < self._cache_minutes:
                    return self._cached_weather
        try:
            params = {
                "latitude": self._lat,
                "longitude": self._lon,
                "current_weather": "true",
                "hourly": "relativehumidity_2m,cloudcover",
                "forecast_days": 1,
            }
            resp = requests.get(self._OPEN_METEO_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Open-Meteo fetch failed: %s", exc)
            return self._cached_weather or {"available": False, "reason": str(exc)}

        cw = data.get("current_weather", {})
        wmo = int(cw.get("weathercode", 0))
        condition = self._WMO_CONDITION.get(wmo, "clear")
        result = {
            "available": True,
            "condition": condition,
            "description": condition,
            "temp_c": float(cw.get("temperature", 25)),
            "wind_speed": float(cw.get("windspeed", 0)),
            "is_day": bool(cw.get("is_day", 1)),
            "clouds_pct": 0,
            "humidity": 0,
            "fetched_at": _utcnow().isoformat(),
        }
        with self._lock:
            self._cached_weather = result
            self._cache_time = _utcnow()
        return result

    def fetch_weather(self) -> dict[str, Any]:
        """Fetch current weather.

        Priority:
          1. pyowm (typed OWM client)  — when api_key + pyowm installed
          2. raw requests to OWM REST  — when api_key set but pyowm absent
          3. open-meteo (free, no key) — fallback when no api_key
        All paths share the same in-memory cache.
        """
        if not self._api_key:
            return self._fetch_open_meteo()

        with self._lock:
            if self._cached_weather and self._cache_time:
                elapsed = (_utcnow() - self._cache_time).total_seconds() / 60.0
                if elapsed < self._cache_minutes:
                    return self._cached_weather

        if _PYOWM_AVAILABLE:
            result = self._fetch_via_pyowm()
            if result.get("available"):
                return result
            logger.warning("pyowm fetch failed, falling back to raw requests")

        return self._fetch_via_requests()

    def _fetch_via_pyowm(self) -> dict[str, Any]:
        """Fetch weather using the pyowm client library."""
        try:
            owm = pyowm.OWM(self._api_key)
            mgr = owm.weather_manager()
            if self._lat and self._lon:
                obs = mgr.weather_at_coords(self._lat, self._lon)
            else:
                obs = mgr.weather_at_place(f"{self._city},{self._country}")

            w = obs.weather
            temp_dict = w.temperature("celsius")
            result = {
                "available": True,
                "condition": str(w.status or "").lower(),
                "description": str(w.detailed_status or ""),
                "temp_c": float(temp_dict.get("temp", 0)),
                "feels_like_c": float(temp_dict.get("feels_like", 0)),
                "humidity": int(w.humidity or 0),
                "clouds_pct": int(w.clouds or 0),
                "wind_speed": float((w.wind() or {}).get("speed", 0)),
                "is_day": self._is_daytime_from_ref_time(int(w.reference_time() or 0)),
                "fetched_at": _utcnow().isoformat(),
            }
        except Exception as exc:
            logger.warning("pyowm fetch error: %s", exc)
            return {"available": False, "reason": str(exc)}

        with self._lock:
            self._cached_weather = result
            self._cache_time = _utcnow()
        return result

    def _fetch_via_requests(self) -> dict[str, Any]:
        """Fetch weather using raw HTTP requests to OWM REST API."""
        params: dict[str, Any] = {"appid": self._api_key, "units": "metric"}
        if self._lat and self._lon:
            params["lat"] = self._lat
            params["lon"] = self._lon
        else:
            params["q"] = f"{self._city},{self._country}"

        try:
            resp = requests.get(self.API_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("OWM requests fetch failed: %s", exc)
            return self._cached_weather or {"available": False, "reason": str(exc)}

        weather_list = data.get("weather", [])
        weather_main = str(weather_list[0].get("main", "")).strip() if weather_list else ""
        weather_desc = str(weather_list[0].get("description", "")).strip() if weather_list else ""
        main_data = data.get("main", {}) if isinstance(data.get("main"), dict) else {}
        result = {
            "available": True,
            "condition": weather_main.lower(),
            "description": weather_desc,
            "temp_c": float(main_data.get("temp", 0)),
            "feels_like_c": float(main_data.get("feels_like", 0)),
            "humidity": int(main_data.get("humidity", 0)),
            "clouds_pct": int(data.get("clouds", {}).get("all", 0)),
            "wind_speed": float(data.get("wind", {}).get("speed", 0)),
            "is_day": self._is_daytime(data),
            "fetched_at": _utcnow().isoformat(),
        }
        with self._lock:
            self._cached_weather = result
            self._cache_time = _utcnow()
        return result

    # ------------------------------------------------------------------
    # Lighting adjustments
    # ------------------------------------------------------------------

    def get_adjustments(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Calculate LED adjustments based on current weather."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        wa = profile.get("weather_adaptive", {})

        if not wa.get("enabled", True):
            return {"adjusted": False, "reason": "Weather adaptation disabled."}

        weather = self.fetch_weather()
        if not weather.get("available", False):
            return {"adjusted": False, "reason": weather.get("reason", "Weather unavailable.")}

        condition = str(weather.get("condition", "")).lower()
        clouds = int(weather.get("clouds_pct", 0))
        temp = float(weather.get("temp_c", 25))
        is_day = weather.get("is_day", True)

        brightness_mod = 0.0
        color_mod = ""
        animation = "solid"
        message = ""

        # Cloudy/overcast adjustments
        if condition in ("clouds", "overcast") or clouds >= 70:
            boost = float(wa.get("brightness_boost_cloudy", 0.20))
            brightness_mod = boost
            color_mod = "#FFF8DC"  # Warmer tone to combat gloom
            message = f"Cloudy day ({clouds}% clouds). Boosting indoor brightness +{int(boost * 100)}%."

        # Rain/drizzle/thunderstorm
        elif condition in ("rain", "drizzle", "thunderstorm"):
            boost = float(wa.get("brightness_boost_rainy", 0.25))
            brightness_mod = boost
            color_mod = "#FFE4B5"  # Warm cozy
            animation = "gentle_pulse"
            message = f"Rainy weather. Cozy mode: brightness +{int(boost * 100)}%, warm tones."

        # Snow
        elif condition == "snow":
            brightness_mod = 0.15
            color_mod = "#F0F8FF"  # Cool blue-white
            message = "Snowy weather. Soft cool lighting."

        # Clear sunny day
        elif condition == "clear" and is_day:
            brightness_mod = -0.10  # Reduce (natural light sufficient)
            message = "Clear sunny day. Reducing indoor brightness."

        # Hot weather
        if temp >= 38:
            color_mod = color_mod or "#ADD8E6"  # Cool blue
            message += " Hot outside. Adding cool blue tones."

        # Cold weather
        elif temp <= 10:
            color_mod = color_mod or "#FF8C00"  # Warm amber
            message += " Cold outside. Warm amber tones."

        # Storm comfort mode
        if condition == "thunderstorm":
            brightness_mod = 0.15
            color_mod = "#FFD9B3"
            animation = "slow_breathing"
            message = "Storm detected. Comfort mode: soft warm glow."

        wa["last_condition"] = condition

        if brightness_mod == 0.0 and not color_mod:
            return {"adjusted": False, "reason": "No weather adjustment needed.", "weather": weather}

        return {
            "adjusted": True,
            "brightness_modifier": round(brightness_mod, 2),
            "color_override": color_mod,
            "animation": animation,
            "weather": weather,
            "message": message.strip(),
            "led_action": {
                "type": "led_scene",
                "action": "weather_adaptive",
                "brightness_modifier": round(brightness_mod, 2),
                "color": color_mod,
                "animation": animation,
            },
        }

    def get_hydration_boost(self) -> dict[str, Any]:
        """Check if hot weather requires increased hydration reminders."""
        weather = self.fetch_weather()
        if not weather.get("available", False):
            return {"boost": False}

        temp = float(weather.get("temp_c", 25))
        humidity = int(weather.get("humidity", 50))

        if temp >= 35 or (temp >= 30 and humidity >= 60):
            return {
                "boost": True,
                "temp_c": temp,
                "humidity": humidity,
                "message": f"Hot weather ({temp:.0f}°C). Drink extra water today.",
                "interval_reduction_pct": 30,
            }
        return {"boost": False, "temp_c": temp}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_daytime(data: dict) -> bool:
        sys_data = data.get("sys", {}) if isinstance(data.get("sys"), dict) else {}
        sunrise = int(sys_data.get("sunrise", 0))
        sunset = int(sys_data.get("sunset", 0))
        dt = int(data.get("dt", 0))
        if sunrise and sunset and dt:
            return sunrise <= dt <= sunset
        hour = datetime.now().hour
        return 6 <= hour <= 18

    @staticmethod
    def _is_daytime_from_ref_time(ref_time: int) -> bool:
        """Estimate daytime from a UTC unix timestamp (pyowm reference_time)."""
        if not ref_time:
            return 6 <= datetime.now().hour <= 18
        hour = datetime.utcfromtimestamp(ref_time).hour
        return 6 <= hour <= 18

    def update_location(self, latitude: float, longitude: float) -> None:
        self._lat = float(latitude)
        self._lon = float(longitude)
        with self._lock:
            self._cached_weather = None
            self._cache_time = None
