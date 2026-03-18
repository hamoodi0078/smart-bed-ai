from __future__ import annotations

import datetime
import json
import os

import requests


class PrayerTimesService:
    PRAYER_ORDER = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
    CITY_API_URL = "http://api.aladhan.com/v1/timingsByCity"
    COORDS_API_URL = "http://api.aladhan.com/v1/timings"

    def __init__(
        self,
        city: str = "Kuwait City",
        country: str = "Kuwait",
        method: int = 8,
        latitude: float | None = None,
        longitude: float | None = None,
        date: str = "",
    ):
        self.city = city
        self.country = country
        self.method = method
        self.latitude = latitude
        self.longitude = longitude
        self.date = str(date or "").strip()
        self.timeout_seconds = int(os.getenv("ISLAMIC_MODE_PRAYER_TIMEOUT", "12"))
        self.cache_path = os.getenv("ISLAMIC_MODE_PRAYER_CACHE", "").strip()

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

    def _request_payload(self) -> dict:
        params = {"method": self.method}
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
            response = requests.get(url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
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
