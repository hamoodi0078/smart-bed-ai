from __future__ import annotations

from islamic_mode.hadith_daily import HadithService
from islamic_mode.ramadan_mode import RamadanMode
from islamic_mode.sunnah_tips import SunnahSleepTips


class DanaIslamicVoice:
    def __init__(
        self,
        user_name: str = "Hamoud",
        hadith_service: HadithService | None = None,
        sunnah_tips: SunnahSleepTips | None = None,
        ramadan_mode: RamadanMode | None = None,
    ):
        self.user_name = user_name
        self.hadith_service = hadith_service or HadithService()
        self.sunnah_tips = sunnah_tips or SunnahSleepTips()
        self.ramadan_mode = ramadan_mode or RamadanMode()

    def get_prayer_approaching_message(self, prayer_name: str, minutes_until: int) -> str:
        return (
            f"{self.user_name}, {prayer_name} prayer is approaching in {minutes_until} minutes. "
            "The Prophet ﷺ said: 'The prayer is a light.' Take a moment to prepare."
        )

    def get_morning_message(self) -> str:
        hadith = self.hadith_service.get_daily_hadith()
        hadith_text = str(hadith.get("hadith", "")).strip()
        source = str(hadith.get("source", "Sahih Bukhari")).strip()
        return (
            f"Assalamu Alaikum {self.user_name}. Good morning. "
            f"Today's hadith from {source}: {hadith_text}"
        )

    def get_sleep_message(self) -> str:
        dua = self.hadith_service.get_sleep_dua()
        tip = self.sunnah_tips.get_tip_of_night()
        return (
            f"Before sleep, recite: {dua.get('arabic', '')} "
            f"({dua.get('english', '')}). Tonight's Sunnah tip: {tip}"
        )

    def get_ramadan_message(self) -> str:
        greeting = self.ramadan_mode.get_ramadan_greeting()
        tarawih = self.ramadan_mode.get_tarawih_reminder()
        return (
            f"{greeting} May Allah accept your fasting and prayers. {tarawih}"
        )

    def get_achievement_message(self, achievement: str) -> str:
        return (
            f"MashaAllah {self.user_name}! {achievement}. "
            "As the Prophet ﷺ said: 'Allah loves those who are consistent.'"
        )
