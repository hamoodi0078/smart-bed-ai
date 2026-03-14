from __future__ import annotations

from datetime import datetime, timedelta

from islamic_mode.islamic_calendar import IslamicCalendarService
from islamic_mode.prayer_times import PrayerTimesService


class RamadanMode:
    def __init__(
        self,
        calendar_service: IslamicCalendarService | None = None,
        prayer_service: PrayerTimesService | None = None,
    ):
        self.calendar_service = calendar_service or IslamicCalendarService()
        self.prayer_service = prayer_service or PrayerTimesService()

    def is_active(self) -> bool:
        return self.calendar_service.is_ramadan()

    @staticmethod
    def _shift_time(time_text: str, minutes_delta: int) -> str:
        base = datetime.strptime(str(time_text), "%H:%M")
        shifted = base + timedelta(minutes=minutes_delta)
        return shifted.strftime("%H:%M")

    def get_suhoor_wake_time(self) -> str:
        fajr = self.prayer_service.get_today_prayers().get("Fajr", "")
        if not fajr:
            return ""
        return self._shift_time(fajr, -45)

    def get_iftar_time(self) -> str:
        return str(self.prayer_service.get_today_prayers().get("Maghrib", ""))

    def get_ramadan_greeting(self) -> str:
        return "رمضان كريم - Ramadan Kareem! May this blessed month bring you peace and joy."

    def get_tarawih_reminder(self) -> str:
        isha = self.prayer_service.get_today_prayers().get("Isha", "")
        if not isha:
            return "Tarawih reminder: 30 minutes after Isha is a beautiful time to stand in prayer tonight."
        tarawih_time = self._shift_time(isha, 30)
        return (
            f"Tarawih reminder: Around {tarawih_time}, take a few quiet moments for Tarawih prayer tonight."
        )
