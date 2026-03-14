from __future__ import annotations

from datetime import datetime

import requests


class HadithService:
    DAILY_HADITH_API = "https://random-hadith-generator.vercel.app/bukhari/"

    def get_daily_hadith(self) -> dict:
        fallback = {
            "hadith": "The most beloved deeds to Allah are those done consistently, even if small.",
            "source": "Sahih Bukhari",
            "chapter": "Good deeds done regularly",
        }
        try:
            response = requests.get(self.DAILY_HADITH_API, timeout=12)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return fallback

        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = {}

        hadith_text = (
            data.get("hadith_english")
            or data.get("hadith")
            or payload.get("hadith")
            if isinstance(payload, dict)
            else ""
        )
        chapter = (
            data.get("header")
            or data.get("chapter")
            or payload.get("chapter")
            if isinstance(payload, dict)
            else ""
        )

        return {
            "hadith": str(hadith_text or fallback["hadith"]).strip(),
            "source": "Sahih Bukhari",
            "chapter": str(chapter or fallback["chapter"]).strip(),
        }

    def get_sleep_hadith(self) -> dict:
        hadiths = [
            {
                "hadith": "When you go to bed, perform ablution as you do for prayer, then lie on your right side.",
                "source": "Sahih al-Bukhari & Sahih Muslim",
            },
            {
                "hadith": "Whoever recites Ayat al-Kursi at night will have a protector from Allah until morning.",
                "source": "Sahih al-Bukhari",
            },
            {
                "hadith": "When the Prophet ﷺ went to bed, he gathered his palms, recited Al-Ikhlas, Al-Falaq, and An-Nas, then wiped his body.",
                "source": "Sahih al-Bukhari",
            },
            {
                "hadith": "The Prophet ﷺ disliked sleeping before the night prayer and talking after it.",
                "source": "Sahih al-Bukhari",
            },
            {
                "hadith": "He would say at bedtime: 'Bismika Allahumma amutu wa ahya' (In Your name, O Allah, I die and I live).",
                "source": "Sahih al-Bukhari",
            },
            {
                "hadith": "The Prophet ﷺ forbade lying on the stomach and called it a posture Allah dislikes.",
                "source": "Sunan Abi Dawud",
            },
            {
                "hadith": "If one of you gets up from sleep and performs prayer at night, that is among the blessed acts of worship.",
                "source": "Sahih Muslim",
            },
        ]
        index = datetime.today().weekday() % len(hadiths)
        return hadiths[index]

    def get_morning_dua(self) -> dict:
        return {
            "arabic": "أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ.",
            "english": "We have entered a new morning and with it all dominion belongs to Allah. All praise is for Allah. None has the right to be worshipped except Allah alone, without partner.",
        }

    def get_sleep_dua(self) -> dict:
        return {
            "arabic": "بِاسْمِكَ اللَّهُمَّ أَمُوتُ وَأَحْيَا",
            "english": "In Your name, O Allah, I die and I live.",
        }
