from __future__ import annotations

import datetime
import json
import os
from typing import Optional

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from islamic_mode.geolocation import GeolocationService
from loguru import logger
from Storage.io import async_read_json_simple, async_write_json_simple


class PrayerTimesService:
    PRAYER_ORDER = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
    CITY_API_URL = "http://api.aladhan.com/v1/timingsByCity"
    COORDS_API_URL = "http://api.aladhan.com/v1/timings"

    # Aladhan API calculation method IDs mapped to human-readable names
    CALCULATION_METHODS: dict[int, str] = {
        1:  "University of Islamic Sciences, Karachi (Hanafi)",
        2:  "Islamic Society of North America (ISNA)",
        3:  "Muslim World League (MWL)",
        4:  "Umm Al-Qura University, Makkah",
        5:  "Egyptian General Authority of Survey",
        7:  "Institute of Geophysics, Tehran",
        8:  "Gulf Region",
        9:  "Kuwait",
        10: "Qatar",
        11: "Majlis Ugama Islam Singapura (MUIS)",
        12: "Union Organization Islamique de France (UOIF)",
        13: "Diyanet İşleri Başkanlığı, Turkey",
        14: "Spiritual Administration of Muslims of Russia",
        15: "Moonsighting Committee Worldwide (Shafi'i/Hanbali)",
    }

    # Fiqh school shortcuts → (calculation_method_id, asr_method)
    # asr_method: 0 = Standard (Shafi'i/Maliki/Hanbali, shadow=1×), 1 = Hanafi (shadow=2×)
    FIQH_SCHOOL_PRESETS: dict[str, tuple[int, int]] = {
        "hanafi":   (1, 1),   # Karachi method + Hanafi Asr
        "shafii":   (3, 0),   # MWL method + Standard Asr
        "maliki":   (3, 0),   # Same as Shafi'i for Asr
        "hanbali":  (3, 0),   # Same as Shafi'i for Asr
        "mwl":      (3, 0),   # Muslim World League
        "isna":     (2, 0),   # North America
        "egypt":    (5, 0),   # Egyptian method
        "makkah":   (4, 0),   # Umm Al-Qura
        "kuwait":   (9, 0),   # Kuwait
        "qatar":    (10, 0),  # Qatar
        "turkey":   (13, 0),  # Turkey
        "france":   (12, 0),  # France
        "russia":   (14, 0),  # Russia
        "gulf":     (8, 0),   # Gulf Region
    }

    def __init__(
        self,
        city: Optional[str] = None,
        country: Optional[str] = None,
        method: Optional[int] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        date: str = "",
        auto_detect_location: Optional[bool] = None,
        fiqh_school: Optional[str] = None,
        asr_method: Optional[int] = None,
    ):
        """
        Initialize PrayerTimesService with location settings.
        
        If auto_detect_location is True, will attempt to detect location from IP.
        Otherwise uses provided parameters or falls back to config settings.
        """
        # Use config defaults if not provided
        self.auto_detect = auto_detect_location if auto_detect_location is not None else settings.islamic_prayer_auto_location
        self.date = str(date or "").strip()
        self.timeout_seconds = settings.islamic_prayer_timeout_seconds
        self.cache_path = settings.islamic_prayer_cache_path

        # Fiqh school — resolves method and asr_method together when given
        if fiqh_school:
            preset = self.FIQH_SCHOOL_PRESETS.get(str(fiqh_school).strip().lower())
            if preset:
                preset_method, preset_asr = preset
                self.method = method if method is not None else preset_method
                self.asr_method = asr_method if asr_method is not None else preset_asr
                self.fiqh_school = str(fiqh_school).strip().lower()
            else:
                self.method = method if method is not None else settings.islamic_prayer_method
                self.asr_method = asr_method if asr_method is not None else 0
                self.fiqh_school = "unknown"
        else:
            self.method = method if method is not None else settings.islamic_prayer_method
            self.asr_method = asr_method if asr_method is not None else 0
            self.fiqh_school = None

        # Location setup
        self._setup_location(city, country, latitude, longitude)

    def _setup_location(
        self,
        city: Optional[str],
        country: Optional[str],
        latitude: Optional[float],
        longitude: Optional[float]
    ) -> None:
        """Setup location with auto-detection if enabled."""
        if self.auto_detect:
            logger.info("Auto-detecting location for prayer times...")
            geo_service = GeolocationService(timeout_seconds=self.timeout_seconds)
            
            # Parse config lat/lon if set
            config_lat = None
            config_lon = None
            if settings.islamic_prayer_latitude and settings.islamic_prayer_longitude:
                try:
                    config_lat = float(settings.islamic_prayer_latitude)
                    config_lon = float(settings.islamic_prayer_longitude)
                except ValueError:
                    pass
            
            location = geo_service.get_location_with_fallback(
                default_city=settings.islamic_prayer_city,
                default_country=settings.islamic_prayer_country,
                default_latitude=config_lat,
                default_longitude=config_lon
            )
            
            self.city = location.get("city", settings.islamic_prayer_city)
            self.country = location.get("country", settings.islamic_prayer_country)
            self.latitude = location.get("latitude")
            self.longitude = location.get("longitude")
            
            if location.get("auto_detected"):
                detected_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
                logger.info(
                    "IP geolocation auto-detection fired at=%s city=%s country=%s lat=%s lon=%s",
                    detected_at, self.city, self.country, self.latitude, self.longitude,
                )
                self._location_auto_detected_at = detected_at
            else:
                logger.info("Using default/config location: city=%s country=%s", self.city, self.country)
        else:
            # Use provided params or config defaults
            self.city = city if city is not None else settings.islamic_prayer_city
            self.country = country if country is not None else settings.islamic_prayer_country
            
            # Handle latitude/longitude
            if latitude is not None and longitude is not None:
                self.latitude = latitude
                self.longitude = longitude
            else:
                # Try to parse from config
                try:
                    if settings.islamic_prayer_latitude and settings.islamic_prayer_longitude:
                        self.latitude = float(settings.islamic_prayer_latitude)
                        self.longitude = float(settings.islamic_prayer_longitude)
                    else:
                        self.latitude = None
                        self.longitude = None
                except ValueError:
                    self.latitude = None
                    self.longitude = None

    def update_location(
        self,
        city: Optional[str] = None,
        country: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> None:
        """Update location dynamically."""
        if city is not None:
            self.city = city
        if country is not None:
            self.country = country
        if latitude is not None:
            self.latitude = latitude
        if longitude is not None:
            self.longitude = longitude
        
        logger.info(f"Prayer times location updated: {self.city}, {self.country}")

    def refresh_auto_location(self) -> bool:
        """Re-detect location if auto-detection is enabled. Returns True if successful."""
        if not self.auto_detect:
            return False
        
        geo_service = GeolocationService(timeout_seconds=self.timeout_seconds)
        location = geo_service.get_location_from_ip()
        
        if location:
            self.city = location.get("city", self.city)
            self.country = location.get("country", self.country)
            self.latitude = location.get("latitude")
            self.longitude = location.get("longitude")
            logger.info(f"Location refreshed: {self.city}, {self.country}")
            return True
        
        logger.warning("Failed to refresh location")
        return False

    @staticmethod
    def _normalize_time(value: str) -> str:
        text = str(value or "").strip()
        if "(" in text:
            text = text.split("(", 1)[0].strip()
        if " " in text:
            text = text.split(" ", 1)[0].strip()

        parts = text.split(":")
        if len(parts) >= 2 and parts[0].isdigit():
            minute_digits = "".join(ch for ch in parts[1] if ch.isdigit())
            if minute_digits:
                return f"{int(parts[0]):02d}:{int(minute_digits[:2]):02d}"
        return text[:5]

    def _write_cache(self, payload: dict) -> None:
        if not self.cache_path:
            return
        try:
            with open(self.cache_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except OSError:
            return

    def _read_cache(self) -> dict:
        if not self.cache_path:
            return {}
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                cached = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
        return cached if isinstance(cached, dict) else {}

    async def async_load_cache(self) -> dict:
        """Async version of _read_cache — use from async route handlers."""
        if not self.cache_path:
            return {}
        return await async_read_json_simple(self.cache_path)

    async def async_save_cache(self, payload: dict) -> None:
        """Async version of _write_cache — use from async route handlers."""
        if not self.cache_path:
            return
        await async_write_json_simple(self.cache_path, payload)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
        before_sleep=lambda rs: logger.debug(
            "Prayer times API retry attempt {}/3", rs.attempt_number
        ),
    )
    def _get_with_retry(self, url: str, params: dict) -> requests.Response:
        response = requests.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response

    def set_fiqh_school(self, school: str) -> bool:
        """Update the Fiqh school at runtime.

        Returns True if the school is recognised, False otherwise (no change made).
        """
        preset = self.FIQH_SCHOOL_PRESETS.get(str(school).strip().lower())
        if preset is None:
            logger.warning("Unknown Fiqh school '{}'. Valid options: {}", school, list(self.FIQH_SCHOOL_PRESETS))
            return False
        self.method, self.asr_method = preset
        self.fiqh_school = str(school).strip().lower()
        logger.info("Fiqh school set to '{}': method={}, asr_method={}", self.fiqh_school, self.method, self.asr_method)
        return True

    def get_fiqh_info(self) -> dict:
        """Return the current Fiqh school and calculation method info."""
        method_name = self.CALCULATION_METHODS.get(int(self.method), f"Method {self.method}")
        asr_desc = "Hanafi (shadow = 2× object)" if int(self.asr_method or 0) == 1 else "Standard (shadow = 1× object)"
        return {
            "fiqh_school": self.fiqh_school or "custom",
            "calculation_method_id": self.method,
            "calculation_method_name": method_name,
            "asr_juristic_method": int(self.asr_method or 0),
            "asr_juristic_method_name": asr_desc,
            "available_schools": list(self.FIQH_SCHOOL_PRESETS.keys()),
        }

    def _request_payload(self) -> dict:
        params: dict = {"method": self.method}
        if self.asr_method:
            params["school"] = int(self.asr_method)
        if self.date:
            params["date"] = self.date

        if self.latitude is not None and self.longitude is not None:
            params["latitude"] = self.latitude
            params["longitude"] = self.longitude
            url = self.COORDS_API_URL
        else:
            params["city"] = self.city
            params["country"] = self.country
            url = self.CITY_API_URL

        payload: dict = {}
        try:
            response = self._get_with_retry(url, params)
            payload = response.json()
            if isinstance(payload, dict):
                self._write_cache(payload)
        except Exception:
            payload = self._read_cache()
        return payload if isinstance(payload, dict) else {}

    def get_today_prayer_bundle(self) -> dict:
        payload = self._request_payload()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        timings = data.get("timings", {}) if isinstance(data, dict) else {}
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        resolved_prayers = {
            prayer: self._normalize_time(timings.get(prayer, ""))
            for prayer in self.PRAYER_ORDER
        }
        location = {
            "city": str(self.city or "").strip(),
            "country": str(self.country or "").strip(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": str(meta.get("timezone", "") or "").strip(),
            "method": str(
                ((meta.get("method") or {}) if isinstance(meta, dict) else {}).get("name", "")
                or self.method
            ).strip(),
            "mode": "coordinates"
            if self.latitude is not None and self.longitude is not None
            else "city",
        }
        return {"prayers": resolved_prayers, "location": location, "raw": payload}

    def get_today_prayers(self) -> dict:
        return self.get_today_prayer_bundle().get("prayers", {})

    @staticmethod
    def _minutes_until(target_time: str, now: datetime.datetime) -> int | None:
        try:
            hour, minute = [int(part) for part in target_time.split(":")[:2]]
        except Exception:
            return None
        prayer_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta_minutes = int((prayer_dt - now).total_seconds() // 60)
        return delta_minutes

    def get_next_prayer(self) -> dict:
        prayers = self.get_today_prayers()
        now = datetime.datetime.now()

        for prayer_name in self.PRAYER_ORDER:
            prayer_time = prayers.get(prayer_name, "")
            if not prayer_time:
                continue
            minutes = self._minutes_until(prayer_time, now)
            if minutes is None:
                continue
            if minutes >= 0:
                return {
                    "name": prayer_name,
                    "time": prayer_time,
                    "minutes_until": minutes,
                }

        fajr = prayers.get("Fajr", "")
        if fajr:
            minutes = self._minutes_until(fajr, now)
            if minutes is not None:
                return {
                    "name": "Fajr",
                    "time": fajr,
                    "minutes_until": minutes + 24 * 60,
                }

        return {"name": "", "time": "", "minutes_until": -1}

    def is_prayer_approaching(self, minutes_before: int = 10) -> bool:
        next_prayer = self.get_next_prayer()
        minutes_until = int(next_prayer.get("minutes_until", -1) or -1)
        return 0 <= minutes_until <= int(minutes_before)

    def get_prayer_led_color(self, prayer_name: str) -> str:
        colors = {
            "fajr": "#FFF5E0",
            "dhuhr": "#FFFFFF",
            "asr": "#FFD700",
            "maghrib": "#FF6B35",
            "isha": "#7B68EE",
        }
        return colors.get(str(prayer_name or "").strip().lower(), "#FFFFFF")

    def get_current_location(self) -> dict:
        """Get current location settings."""
        return {
            "city": self.city,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "method": self.method,
            "auto_detect": self.auto_detect,
            "using_coordinates": self.latitude is not None and self.longitude is not None
        }
