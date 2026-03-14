from __future__ import annotations

import datetime
import random


class SunnahSleepTips:
    def __init__(self):
        self._tips = [
            "Sleep on your right side as the Prophet ﷺ recommended.",
            "Perform wudu before sleeping whenever you can.",
            "Recite Ayat al-Kursi before sleep for protection through the night.",
            "Recite Surah Al-Ikhlas, Al-Falaq, and An-Nas, then wipe your body.",
            "Say the sleep dua before closing your eyes.",
            "Dust your bed lightly before lying down, as taught in Sunnah.",
            "Keep your final words and thoughts in remembrance of Allah.",
            "Avoid sleeping on your stomach.",
            "Sleep early after Isha so you can wake up refreshed for Fajr.",
            "Set an intention to wake for Tahajjud, even if brief.",
        ]

    def get_tip_of_night(self) -> str:
        day = datetime.date.today().day
        index = (day - 1) % len(self._tips)
        return self._tips[index]

    def get_all_tips(self) -> list[str]:
        return list(self._tips)

    def get_random_tip(self) -> str:
        return random.choice(self._tips)
