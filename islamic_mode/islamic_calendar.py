from __future__ import annotations

import datetime

import requests


class IslamicCalendarService:
    API_URL = "http://api.aladhan.com/v1/gToH"

    def get_hijri_date(self) -> dict:
        today = datetime.date.today()
        params = {"date": today.strftime("%d-%m-%Y")}
        try:
            response = requests.get(self.API_URL, params=params, timeout=12)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {
                "hijri_date": "Unknown",
                "hijri_month": "",
                "hijri_year": 0,
            }

        hijri = payload.get("data", {}).get("hijri", {}) if isinstance(payload, dict) else {}
        day = str(hijri.get("day", "")).strip()
        month = str(hijri.get("month", {}).get("en", "")).strip()
        year_raw = str(hijri.get("year", "0")).strip()
        try:
            year = int(year_raw)
        except ValueError:
            year = 0

        if not day or not month or not year:
            return {
                "hijri_date": "Unknown",
                "hijri_month": month,
                "hijri_year": year,
            }

        return {
            "hijri_date": f"{int(day)} {month} {year}",
            "hijri_month": month,
            "hijri_year": year,
        }

    def is_ramadan(self) -> bool:
        hijri = self.get_hijri_date()
        month = str(hijri.get("hijri_month", "")).strip().lower()
        return month in {"ramadan", "ramadhan"}

    def get_islamic_events(self) -> dict:
        return {
            "Ramadan Start": "1 Ramadan 1447",
            "Laylatul Qadr (27th Ramadan)": "27 Ramadan 1447",
            "Eid al-Fitr": "1 Shawwal 1447",
            "Dhul Hijjah Start": "1 Dhul Hijjah 1447",
            "Eid al-Adha": "10 Dhul Hijjah 1447",
            "Islamic New Year": "1 Muharram 1447",
            "Prophet's Birthday": "12 Rabi al-Awwal 1447",
        }

    @staticmethod
    def _normalize_hijri_text(value: str) -> str:
        parts = str(value or "").strip().lower().split()
        if len(parts) < 3:
            return str(value or "").strip().lower()
        try:
            day = str(int(parts[0]))
        except ValueError:
            day = parts[0]
        return f"{day} {parts[1]} {parts[2]}"

    def get_todays_islamic_event(self) -> str | None:
        hijri = self.get_hijri_date()
        today_hijri = self._normalize_hijri_text(str(hijri.get("hijri_date", "")))
        if not today_hijri or today_hijri == "unknown":
            return None

        events = self.get_islamic_events()
        for event_name, event_date in events.items():
            if self._normalize_hijri_text(event_date) == today_hijri:
                return event_name
        return None
