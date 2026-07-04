from __future__ import annotations

import datetime
import hashlib
import random


class SunnahSleepTips:
    def __init__(self):
        self._tips = [
            # Sleep posture & preparation
            "Sleep on your right side as the Prophet ﷺ recommended.",
            "Perform wudu before sleeping whenever you can.",
            "Dust your bed lightly before lying down, as taught in Sunnah.",
            "Avoid sleeping on your stomach - the Prophet ﷺ discouraged this posture.",
            "Place your right hand under your right cheek when sleeping.",
            # Quranic recitations
            "Recite Ayat al-Kursi before sleep for protection through the night.",
            "Recite Surah Al-Ikhlas, Al-Falaq, and An-Nas, then wipe your body.",
            "Recite the last two verses of Surah Al-Baqarah before sleeping.",
            "Read Surah Al-Mulk before sleep - it intercedes for its reciter.",
            "Recite Surah Al-Kafirun to ward off shirk before sleeping.",
            # Duas & dhikr
            "Say the sleep dua: 'Bismika Allahumma amutu wa ahya' before closing your eyes.",
            "Recite 'SubhanAllah' 33 times, 'Alhamdulillah' 33 times, and 'Allahu Akbar' 34 times.",
            "Say 'Alhamdulillahi alladhi at'amana wa saqana' - thanking Allah for provision.",
            "Keep your final words and thoughts in remembrance of Allah.",
            "Make dua for forgiveness and guidance before sleep.",
            # Sleep timing
            "Sleep early after Isha so you can wake up refreshed for Fajr.",
            "Avoid staying awake unnecessarily after Isha prayer.",
            "Take a short afternoon nap (Qailulah) to follow the Sunnah.",
            "Wake up before Fajr to pray Tahajjud, even if just two rak'ah.",
            # Mental & spiritual preparation
            "Set an intention to wake for Tahajjud, even if brief.",
            "Forgive anyone who wronged you before sleeping with a clear heart.",
            "Review your day and seek forgiveness for any mistakes.",
            "Sleep in a state of purity whenever possible.",
            "Avoid negative thoughts and gossip before bed.",
            # Physical care
            "Close doors and windows at night as the Prophet ﷺ instructed.",
            "Cover food and drink containers before sleeping.",
            "Extinguish lamps and candles before sleeping for safety.",
            "Ensure your sleeping area is clean and comfortable.",
            "Wear clean, modest clothing while sleeping.",
            # Family & relationships
            "Make dua for your family's protection before sleep.",
            "Ensure children are home before Maghrib time.",
            "Read bedtime stories from the Quran or Prophet's life to children.",
            "Sleep peacefully with your spouse, avoiding arguments at night.",
            # Special practices
            "If you wake up at night, make dhikr and pray if possible.",
            "Keep a regular sleep schedule to maintain health - part of caring for Allah's trust.",
            "Avoid heavy meals close to bedtime - the Prophet ﷺ ate moderately.",
            "Sleep with the intention of waking for worship, turning rest into ibadah.",
        ]

    def get_tip_of_night(self) -> str:
        """Get deterministic tip based on date (same day = same tip)."""
        today = datetime.date.today()
        # Use hash for better distribution across the collection
        seed = f"{today.year}-{today.month}-{today.day}"
        hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        index = hash_val % len(self._tips)
        return self._tips[index]

    def get_tip_by_category(self, category: str) -> list[str]:
        """Get tips by category (posture, quran, dua, timing, etc)."""
        categories = {
            "posture": self._tips[0:5],
            "quran": self._tips[5:10],
            "dua": self._tips[10:15],
            "timing": self._tips[15:19],
            "spiritual": self._tips[19:24],
            "physical": self._tips[24:29],
            "family": self._tips[29:33],
            "special": self._tips[33:37],
        }
        return categories.get(category.lower(), [])

    def get_all_tips(self) -> list[str]:
        return list(self._tips)

    def get_random_tip(self) -> str:
        return random.choice(self._tips)

    def get_tips_count(self) -> int:
        """Get total number of tips available."""
        return len(self._tips)
