from __future__ import annotations

import datetime
import json
import os

import requests


class PrayerTimesService:
    PRAYER_ORDER = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
    API_URL = "http://api.aladhan.com/v1/timingsByCity"

    def __init__(self, city: str = "Kuwait City", country: str = "Kuwait", method: int = 8):
        self.city = city
        self.country = country
        self.method = method
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

    def get_today_prayers(self) -> dict:
        params = {
            "city": self.city,
            "country": self.country,
            "method": self.method,
        }
        payload: dict = {}
        try:
            response = requests.get(self.API_URL, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                self._write_cache(payload)
        except Exception:
            payload = self._read_cache()

        timings = (
            payload.get("data", {}).get("timings", {})
            if isinstance(payload, dict)
            else {}
        )
        if not isinstance(timings, dict):
            timings = {}

        return {
            prayer: self._normalize_time(timings.get(prayer, ""))
            for prayer in self.PRAYER_ORDER
        }

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
