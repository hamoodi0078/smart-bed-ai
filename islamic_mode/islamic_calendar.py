from __future__ import annotations

import datetime

import requests

try:
    from hijri_converter import convert as _hijri_convert
    _HIJRI_CONVERTER_AVAILABLE = True
except ImportError:
    _hijri_convert = None  # type: ignore[assignment]
    _HIJRI_CONVERTER_AVAILABLE = False

# Hijri month number → English name (hijri-converter spelling)
_MONTH_NAMES: dict[int, str] = {
    1: "Muharram",
    2: "Safar",
    3: "Rabi' al-Awwal",
    4: "Rabi' al-Akhirah",
    5: "Jumada al-Ula",
    6: "Jumada al-Akhirah",
    7: "Rajab",
    8: "Sha'ban",
    9: "Ramadan",
    10: "Shawwal",
    11: "Dhu al-Qi'dah",
    12: "Dhu al-Hijjah",
}

# Canonical Ramadan month number
_RAMADAN_MONTH = 9


class IslamicCalendarService:
    API_URL = "http://api.aladhan.com/v1/gToH"

    def get_hijri_date(self, date: datetime.date | None = None) -> dict:
        """Return Hijri date info for *date* (defaults to today).

        Uses hijri-converter (offline) as primary source; falls back to the
        aladhan.com REST API when the library is unavailable.

        Returned dict keys:
          hijri_date   – e.g. "9 Dhu al-Qi'dah 1447"
          hijri_month  – e.g. "Dhu al-Qi'dah"
          hijri_year   – int, e.g. 1447
          hijri_day    – int, e.g. 9
          hijri_month_number – int 1-12
        """
        target = date or datetime.date.today()
        if _HIJRI_CONVERTER_AVAILABLE:
            return self._get_hijri_local(target)
        return self._get_hijri_api(target)

    def _get_hijri_local(self, date: datetime.date) -> dict:
        """Convert Gregorian → Hijri using hijri-converter (offline)."""
        try:
            h = _hijri_convert.Gregorian(date.year, date.month, date.day).to_hijri()
            month_name = _MONTH_NAMES.get(h.month, str(h.month))
            return {
                "hijri_date": f"{h.day} {month_name} {h.year}",
                "hijri_month": month_name,
                "hijri_year": int(h.year),
                "hijri_day": int(h.day),
                "hijri_month_number": int(h.month),
            }
        except Exception:
            return self._get_hijri_api(date)

    def _get_hijri_api(self, date: datetime.date) -> dict:
        """Convert Gregorian → Hijri via aladhan.com REST API (network fallback)."""
        params = {"date": date.strftime("%d-%m-%Y")}
        try:
            response = requests.get(self.API_URL, params=params, timeout=12)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {
                "hijri_date": "Unknown",
                "hijri_month": "",
                "hijri_year": 0,
                "hijri_day": 0,
                "hijri_month_number": 0,
            }

        hijri = payload.get("data", {}).get("hijri", {}) if isinstance(payload, dict) else {}
        day_str = str(hijri.get("day", "")).strip()
        month_obj = hijri.get("month", {})
        month = str(month_obj.get("en", "") if isinstance(month_obj, dict) else month_obj).strip()
        year_raw = str(hijri.get("year", "0")).strip()
        try:
            year = int(year_raw)
        except ValueError:
            year = 0
        try:
            day = int(day_str)
        except ValueError:
            day = 0

        # Try to resolve month number from name
        month_number = 0
        for num, name in _MONTH_NAMES.items():
            if name.lower() == month.lower():
                month_number = num
                break

        if not day_str or not month or not year:
            return {
                "hijri_date": "Unknown",
                "hijri_month": month,
                "hijri_year": year,
                "hijri_day": day,
                "hijri_month_number": month_number,
            }

        return {
            "hijri_date": f"{day} {month} {year}",
            "hijri_month": month,
            "hijri_year": year,
            "hijri_day": day,
            "hijri_month_number": month_number,
        }

    def is_ramadan(self, date: datetime.date | None = None) -> bool:
        """Return True when *date* (default today) falls in Ramadan.

        Uses hijri_month_number (==9) when available; falls back to name match.
        """
        hijri = self.get_hijri_date(date)
        month_number = int(hijri.get("hijri_month_number", 0))
        if month_number:
            return month_number == _RAMADAN_MONTH
        month = str(hijri.get("hijri_month", "")).strip().lower()
        return month in {"ramadan", "ramadhan"}

    def gregorian_to_hijri(self, date: datetime.date) -> dict:
        """Public conversion helper — Gregorian date → Hijri dict."""
        return self.get_hijri_date(date)

    def hijri_to_gregorian(self, year: int, month: int, day: int) -> datetime.date | None:
        """Convert a Hijri date to a Gregorian date.

        Returns None when hijri-converter is unavailable or the date is invalid.
        """
        if not _HIJRI_CONVERTER_AVAILABLE:
            return None
        try:
            g = _hijri_convert.Hijri(year, month, day).to_gregorian()
            return datetime.date(g.year, g.month, g.day)
        except Exception:
            return None

    def get_islamic_events(self, hijri_year: int | None = None) -> dict:
        """Return key Islamic events for *hijri_year* (defaults to current year).

        When hijri-converter is available, also resolves each event's Gregorian
        date and includes it in the returned dict values.
        """
        if hijri_year is None:
            current = self.get_hijri_date()
            hijri_year = int(current.get("hijri_year", 1447) or 1447)

        raw_events: dict[str, tuple[int, int, int]] = {
            "Ramadan Start":            (hijri_year, 9,  1),
            "Laylatul Qadr (27th)":     (hijri_year, 9,  27),
            "Eid al-Fitr":              (hijri_year, 10, 1),
            "Dhul Hijjah Start":        (hijri_year, 12, 1),
            "Eid al-Adha":              (hijri_year, 12, 10),
            "Islamic New Year":         (hijri_year, 1,  1),
            "Prophet's Birthday":       (hijri_year, 3,  12),
        }

        result: dict[str, str] = {}
        for name, (hy, hm, hd) in raw_events.items():
            month_name = _MONTH_NAMES.get(hm, str(hm))
            hijri_str = f"{hd} {month_name} {hy}"
            greg = self.hijri_to_gregorian(hy, hm, hd)
            if greg:
                result[name] = f"{hijri_str} ({greg.isoformat()})"
            else:
                result[name] = hijri_str

        return result

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
            # Strip optional Gregorian suffix before normalising
            hijri_part = event_date.split("(")[0].strip()
            if self._normalize_hijri_text(hijri_part) == today_hijri:
                return event_name
        return None