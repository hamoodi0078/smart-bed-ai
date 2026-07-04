from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from Storage.io import async_read_json_simple, async_write_json_simple

import logging

import requests

from config import RUNTIME_DATA_DIR


logger = logging.getLogger(__name__)


class HadithService:
    """
    Comprehensive Hadith Service with multiple API sources.
    
    Sources:
    - hadith-api.com: 16,000+ hadiths from multiple books
    - random-hadith-generator: Bukhari collection
    - Fallback: Local hadith collection
    """
    
    # Primary API: hadith-api.com (comprehensive collection)
    HADITH_API_BASE = "https://hadithapi.com/api"
    
    # Fallback API: random-hadith-generator
    RANDOM_HADITH_API = "https://random-hadith-generator.vercel.app/bukhari/"
    
    # Available hadith books
    BOOKS = {
        "bukhari": "sahih-bukhari",
        "muslim": "sahih-muslim",
        "abudawud": "abu-dawood",
        "tirmidhi": "al-tirmidhi",
        "nasai": "al-nasai",
        "ibnmajah": "ibn-e-majah"
    }
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or RUNTIME_DATA_DIR / "hadith_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = 15

    def _get_daily_cache_path(self) -> Path:
        """Get cache file path for today's hadith."""
        today = datetime.today().date()
        return self.cache_dir / f"daily_hadith_{today}.json"
    
    def _read_cache(self, cache_path: Path) -> Optional[dict]:
        """Read hadith from cache file."""
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to read cache: {e}")
            return None
    
    def _write_cache(self, cache_path: Path, data: dict) -> None:
        """Write hadith to cache file."""
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("Failed to write cache: {}", e)

    async def async_read_cache(self, cache_path: Path) -> Optional[dict]:
        """Async version of _read_cache — use from async route handlers."""
        result = await async_read_json_simple(cache_path)
        return result if result else None

    async def async_write_cache(self, cache_path: Path, data: dict) -> None:
        """Async version of _write_cache — use from async route handlers."""
        await async_write_json_simple(cache_path, data)

    def _get_deterministic_book_and_number(self) -> tuple[str, int]:
        """Get deterministic book and hadith number based on today's date."""
        today = datetime.today().date()
        seed = f"{today.year}-{today.month}-{today.day}"
        hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        
        # Rotate through different books
        book_list = list(self.BOOKS.keys())
        book_key = book_list[hash_val % len(book_list)]
        
        # Get hadith number (each book has different ranges)
        # Using conservative ranges to ensure valid hadiths
        ranges = {
            "bukhari": 7563,  # Sahih Bukhari has ~7500 hadiths
            "muslim": 7190,   # Sahih Muslim has ~7000 hadiths
            "abudawud": 5274, # Abu Dawood has ~5200 hadiths
            "tirmidhi": 3956, # Tirmidhi has ~3900 hadiths
            "nasai": 5758,    # Nasai has ~5700 hadiths
            "ibnmajah": 4341  # Ibn Majah has ~4300 hadiths
        }
        
        max_number = ranges.get(book_key, 1000)
        hadith_number = (hash_val % max_number) + 1
        
        return book_key, hadith_number
    
    def _fetch_from_hadith_api(self, book_key: str, number: int) -> Optional[dict]:
        """Fetch hadith from hadithapi.com."""
        try:
            book_slug = self.BOOKS[book_key]
            url = f"{self.HADITH_API_BASE}/{book_slug}/hadiths/{number}"

            logger.debug(f"Fetching hadith from {url}")
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == 200 and "hadith" in data:
                hadith_data = data["hadith"]
                return {
                    "hadith": hadith_data.get("hadithEnglish", ""),
                    "hadith_arabic": hadith_data.get("hadithArabic", ""),
                    "source": hadith_data.get("book", {}).get("bookName", book_key.title()),
                    "chapter": hadith_data.get("chapter", {}).get("chapterEnglish", ""),
                    "number": hadith_data.get("hadithNumber", number),
                    "narrator": hadith_data.get("englishNarrator", ""),
                    "api_source": "hadithapi.com"
                }
        except Exception as e:
            logger.debug(f"hadithapi.com fetch failed: {e}")
        return None
    
    def _fetch_from_random_api(self) -> Optional[dict]:
        """Fetch random hadith from random-hadith-generator."""
        try:
            response = requests.get(self.RANDOM_HADITH_API, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            hadith_text = (
                data.get("hadith_english") or 
                data.get("hadith") or 
                payload.get("hadith", "")
            )
            chapter = (
                data.get("header") or 
                data.get("chapter") or 
                payload.get("chapter", "")
            )
            
            if hadith_text:
                return {
                    "hadith": str(hadith_text).strip(),
                    "source": "Sahih Bukhari",
                    "chapter": str(chapter).strip(),
                    "api_source": "random-hadith-generator"
                }
        except Exception as e:
            logger.debug(f"random-hadith-generator fetch failed: {e}")
        return None
    
    def _get_local_fallback(self) -> dict:
        """Get local fallback hadith collection."""
        fallback_hadiths = [
            {
                "hadith": "The most beloved deeds to Allah are those done consistently, even if small.",
                "source": "Sahih Bukhari & Muslim",
                "chapter": "Good deeds done regularly",
                "narrator": "Aisha (RA)"
            },
            {
                "hadith": "Actions are judged by intentions, so each man will have what he intended.",
                "source": "Sahih Bukhari",
                "chapter": "Revelation",
                "narrator": "Umar ibn al-Khattab (RA)"
            },
            {
                "hadith": "The strong person is not the one who can wrestle, but the one who controls himself in a fit of rage.",
                "source": "Sahih Bukhari & Muslim",
                "chapter": "Good Manners",
                "narrator": "Abu Hurairah (RA)"
            },
            {
                "hadith": "Whoever believes in Allah and the Last Day should speak good or remain silent.",
                "source": "Sahih Bukhari & Muslim",
                "chapter": "Good Manners",
                "narrator": "Abu Hurairah (RA)"
            },
            {
                "hadith": "The believers, in their love, mutual kindness, and close ties, are like one body; when any part complains, the whole body responds with wakefulness and fever.",
                "source": "Sahih Muslim",
                "chapter": "Righteousness and Maintaining Ties of Kinship",
                "narrator": "Nu'man ibn Bashir (RA)"
            }
        ]
        
        # Use date-based selection for consistency
        index = datetime.today().day % len(fallback_hadiths)
        selected = fallback_hadiths[index].copy()
        selected["api_source"] = "local_fallback"
        return selected
    
    def get_daily_hadith(self) -> dict:
        """
        Get hadith of the day with intelligent caching and multi-source fallback.
        
        Strategy:
        1. Check cache for today's hadith
        2. Try hadithapi.com (primary source)
        3. Try random-hadith-generator (fallback)
        4. Use local collection (last resort)
        """
        cache_path = self._get_daily_cache_path()
        
        # Try cache first
        cached = self._read_cache(cache_path)
        if cached:
            logger.debug("Using cached daily hadith")
            return cached
        
        # Try primary API
        book_key, number = self._get_deterministic_book_and_number()
        logger.info("Fetching daily hadith: {} #{}", book_key, number)
        
        hadith = self._fetch_from_hadith_api(book_key, number)
        if hadith:
            logger.info("Fetched from hadithapi.com: {}", hadith['source'])
            hadith = self._enrich_with_grade(hadith)
            self._write_cache(cache_path, hadith)
            return hadith

        # Try fallback API
        hadith = self._fetch_from_random_api()
        if hadith:
            logger.info("Fetched from random-hadith-generator")
            hadith = self._enrich_with_grade(hadith)
            self._write_cache(cache_path, hadith)
            return hadith
        
        # Use local fallback
        logger.warning("All APIs failed, using local fallback hadith")
        hadith = self._get_local_fallback()
        self._write_cache(cache_path, hadith)
        return self._enrich_with_grade(hadith)

    # ── Authenticity rating ───────────────────────────────────────────────────

    _SAHIH_SOURCES = frozenset({
        "sahih al-bukhari", "sahih bukhari", "bukhari", "sahih-bukhari",
        "sahih muslim", "muslim", "sahih-muslim",
        "sahih al-bukhari & sahih muslim", "sahih bukhari & muslim",
        "sahih al-bukhari & muslim",
    })
    _HASAN_SOURCES = frozenset({
        "al-tirmidhi", "tirmidhi", "sunan al-tirmidhi",
        "sunan abi dawud", "sunan abu dawood", "abu dawud", "abudawud",
    })
    _AUTHENTICATED_SOURCES = frozenset({
        "sunan an-nasai", "al-nasai", "nasai",
        "sunan ibn majah", "ibn majah", "ibnmajah",
    })

    @classmethod
    def _grade_hadith(cls, source: str) -> dict:
        """Return an authenticity grade for a hadith based on its source collection.

        This is a collection-level approximation, not a per-hadith chain analysis.
        Bukhari and Muslim are the two most rigorously authenticated collections;
        their hadiths are generally considered Sahih.

        Returns
        -------
        dict with keys:
          grade (str)        — 'Sahih' | 'Hasan' | 'Authenticated' | 'Unknown'
          grade_arabic (str) — Arabic transliteration of the grade
          confidence (str)   — 'high' | 'medium' | 'low'
          note (str)         — human-readable explanation
        """
        src_lower = str(source or "").strip().lower()
        if src_lower in cls._SAHIH_SOURCES:
            return {
                "grade": "Sahih",
                "grade_arabic": "صحيح",
                "confidence": "high",
                "note": "From the most rigorously authenticated hadith collections.",
            }
        if src_lower in cls._HASAN_SOURCES:
            return {
                "grade": "Hasan",
                "grade_arabic": "حسن",
                "confidence": "medium",
                "note": "From a well-regarded collection — generally reliable.",
            }
        if src_lower in cls._AUTHENTICATED_SOURCES:
            return {
                "grade": "Authenticated",
                "grade_arabic": "موثق",
                "confidence": "medium",
                "note": "From an authenticated Sunan collection.",
            }
        return {
            "grade": "Unknown",
            "grade_arabic": "غير محدد",
            "confidence": "low",
            "note": "Source not in the known authentic collections index.",
        }

    def _enrich_with_grade(self, hadith: dict) -> dict:
        """Add authenticity grade metadata to a hadith dict."""
        if "authenticity" not in hadith:
            hadith["authenticity"] = self._grade_hadith(hadith.get("source", ""))
        return hadith

    # ── Context-aware selection ───────────────────────────────────────────────

    _CONTEXT_HADITHS: dict[str, list[dict]] = {
        "sleep": [
            {
                "hadith": "When you go to bed, perform ablution as you do for prayer, then lie on your right side.",
                "source": "Sahih al-Bukhari & Muslim",
                "narrator": "Al-Bara' ibn 'Azib (RA)",
            },
            {
                "hadith": "Whoever recites Ayat al-Kursi at night will have a protector from Allah until morning.",
                "source": "Sahih al-Bukhari",
                "narrator": "Abu Hurairah (RA)",
            },
            {
                "hadith": "When the Prophet ﷺ went to bed, he gathered his palms, recited Al-Ikhlas, Al-Falaq, and An-Nas, then wiped his body.",
                "source": "Sahih al-Bukhari",
                "narrator": "Aisha (RA)",
            },
            {
                "hadith": "He would say at bedtime: 'Bismika Allahumma amutu wa ahya' (In Your name, O Allah, I die and I live).",
                "source": "Sahih al-Bukhari",
                "narrator": "Hudhaifa (RA)",
            },
            {
                "hadith": "The Prophet ﷺ disliked sleeping before the night prayer and talking after it.",
                "source": "Sahih al-Bukhari",
                "narrator": "Ibn Mas'ud (RA)",
            },
            {
                "hadith": "The Prophet ﷺ forbade lying on the stomach and called it a posture Allah dislikes.",
                "source": "Sunan Abi Dawud",
                "narrator": "Takhfa al-Ghifari (RA)",
            },
        ],
        "morning": [
            {
                "hadith": "Whoever prays Fajr in congregation is under the protection of Allah until evening.",
                "source": "Sahih Muslim",
                "narrator": "Jundub (RA)",
            },
            {
                "hadith": "O Allah, bless my nation in its early mornings — the Prophet ﷺ would say this after Fajr.",
                "source": "Sunan Abi Dawud",
                "narrator": "Sakhr al-Ghamidi (RA)",
            },
            {
                "hadith": "Two rak'at of Fajr prayer are better than this world and all it contains.",
                "source": "Sahih Muslim",
                "narrator": "Aisha (RA)",
            },
        ],
        "tahajjud": [
            {
                "hadith": "The best prayer after the obligatory prayers is the night prayer.",
                "source": "Sahih Muslim",
                "narrator": "Abu Hurairah (RA)",
            },
            {
                "hadith": "Our Lord descends each night to the lowest heaven when the last third of the night remains and says: Who calls on Me?",
                "source": "Sahih al-Bukhari & Muslim",
                "narrator": "Abu Hurairah (RA)",
            },
            {
                "hadith": "Stick to night prayers; it was the practice of the righteous before you and it brings you closer to your Lord.",
                "source": "Al-Tirmidhi",
                "narrator": "Bilal (RA)",
            },
        ],
        "gratitude": [
            {
                "hadith": "Whoever does not thank people does not thank Allah.",
                "source": "Sunan Abi Dawud",
                "narrator": "Abu Hurairah (RA)",
            },
            {
                "hadith": "Allah is pleased with a servant who eats and praises Him, or drinks and praises Him.",
                "source": "Sahih Muslim",
                "narrator": "Anas ibn Malik (RA)",
            },
        ],
    }

    def get_context_hadith(self, context: str) -> dict:
        """Return a hadith appropriate for the given life/sleep context.

        Parameters
        ----------
        context:
            One of 'sleep', 'morning', 'tahajjud', 'gratitude', or any string.
            Falls back to daily hadith when context is not recognised.

        Returns
        -------
        Hadith dict enriched with ``authenticity`` grade.
        """
        ctx = str(context or "").strip().lower()
        pool = self._CONTEXT_HADITHS.get(ctx)
        if pool:
            index = datetime.today().day % len(pool)
            hadith = pool[index].copy()
            hadith["context"] = ctx
            return self._enrich_with_grade(hadith)
        # Unknown context — fall back to daily hadith
        hadith = self.get_daily_hadith()
        hadith["context"] = "daily"
        return self._enrich_with_grade(hadith)

    def get_sleep_hadith(self) -> dict:
        """Return a sleep-context hadith with authenticity rating."""
        return self.get_context_hadith("sleep")

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
