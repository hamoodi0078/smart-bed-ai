"""Quran text service with caching and translation support."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from config import RUNTIME_DATA_DIR


logger = logging.getLogger(__name__)


class QuranTextService:
    """
    Service for fetching and caching Quran text with translations.
    
    Uses api.alquran.cloud for comprehensive Quran data.
    """
    
    # API endpoints
    API_BASE = "https://api.alquran.cloud/v1"
    
    # Available editions (identifiers for different reciters/translations)
    EDITIONS = {
        "arabic": "quran-simple-enhanced",  # Simple Arabic text with diacritics
        "english": "en.sahih",              # Sahih International translation
        "transliteration": "en.transliteration",
    }
    
    # Surah metadata
    SURAH_INFO = [
        {"number": 1, "name": "Al-Fatihah", "english_name": "The Opening", "verses": 7, "revelation_type": "Meccan"},
        {"number": 2, "name": "Al-Baqarah", "english_name": "The Cow", "verses": 286, "revelation_type": "Medinan"},
        {"number": 3, "name": "Ali 'Imran", "english_name": "Family of Imran", "verses": 200, "revelation_type": "Medinan"},
        {"number": 4, "name": "An-Nisa", "english_name": "The Women", "verses": 176, "revelation_type": "Medinan"},
        {"number": 5, "name": "Al-Ma'idah", "english_name": "The Table Spread", "verses": 120, "revelation_type": "Medinan"},
        {"number": 6, "name": "Al-An'am", "english_name": "The Cattle", "verses": 165, "revelation_type": "Meccan"},
        {"number": 7, "name": "Al-A'raf", "english_name": "The Heights", "verses": 206, "revelation_type": "Meccan"},
        {"number": 8, "name": "Al-Anfal", "english_name": "The Spoils of War", "verses": 75, "revelation_type": "Medinan"},
        {"number": 9, "name": "At-Tawbah", "english_name": "The Repentance", "verses": 129, "revelation_type": "Medinan"},
        {"number": 10, "name": "Yunus", "english_name": "Jonah", "verses": 109, "revelation_type": "Meccan"},
        {"number": 11, "name": "Hud", "english_name": "Hud", "verses": 123, "revelation_type": "Meccan"},
        {"number": 12, "name": "Yusuf", "english_name": "Joseph", "verses": 111, "revelation_type": "Meccan"},
        {"number": 13, "name": "Ar-Ra'd", "english_name": "The Thunder", "verses": 43, "revelation_type": "Medinan"},
        {"number": 14, "name": "Ibrahim", "english_name": "Abraham", "verses": 52, "revelation_type": "Meccan"},
        {"number": 15, "name": "Al-Hijr", "english_name": "The Rocky Tract", "verses": 99, "revelation_type": "Meccan"},
        {"number": 16, "name": "An-Nahl", "english_name": "The Bee", "verses": 128, "revelation_type": "Meccan"},
        {"number": 17, "name": "Al-Isra", "english_name": "The Night Journey", "verses": 111, "revelation_type": "Meccan"},
        {"number": 18, "name": "Al-Kahf", "english_name": "The Cave", "verses": 110, "revelation_type": "Meccan"},
        {"number": 19, "name": "Maryam", "english_name": "Mary", "verses": 98, "revelation_type": "Meccan"},
        {"number": 20, "name": "Ta-Ha", "english_name": "Ta-Ha", "verses": 135, "revelation_type": "Meccan"},
        {"number": 21, "name": "Al-Anbya", "english_name": "The Prophets", "verses": 112, "revelation_type": "Meccan"},
        {"number": 22, "name": "Al-Hajj", "english_name": "The Pilgrimage", "verses": 78, "revelation_type": "Medinan"},
        {"number": 23, "name": "Al-Mu'minun", "english_name": "The Believers", "verses": 118, "revelation_type": "Meccan"},
        {"number": 24, "name": "An-Nur", "english_name": "The Light", "verses": 64, "revelation_type": "Medinan"},
        {"number": 25, "name": "Al-Furqan", "english_name": "The Criterion", "verses": 77, "revelation_type": "Meccan"},
        {"number": 26, "name": "Ash-Shu'ara", "english_name": "The Poets", "verses": 227, "revelation_type": "Meccan"},
        {"number": 27, "name": "An-Naml", "english_name": "The Ant", "verses": 93, "revelation_type": "Meccan"},
        {"number": 28, "name": "Al-Qasas", "english_name": "The Stories", "verses": 88, "revelation_type": "Meccan"},
        {"number": 29, "name": "Al-'Ankabut", "english_name": "The Spider", "verses": 69, "revelation_type": "Meccan"},
        {"number": 30, "name": "Ar-Rum", "english_name": "The Romans", "verses": 60, "revelation_type": "Meccan"},
        {"number": 31, "name": "Luqman", "english_name": "Luqman", "verses": 34, "revelation_type": "Meccan"},
        {"number": 32, "name": "As-Sajdah", "english_name": "The Prostration", "verses": 30, "revelation_type": "Meccan"},
        {"number": 33, "name": "Al-Ahzab", "english_name": "The Combined Forces", "verses": 73, "revelation_type": "Medinan"},
        {"number": 34, "name": "Saba", "english_name": "Sheba", "verses": 54, "revelation_type": "Meccan"},
        {"number": 35, "name": "Fatir", "english_name": "Originator", "verses": 45, "revelation_type": "Meccan"},
        {"number": 36, "name": "Ya-Sin", "english_name": "Ya-Sin", "verses": 83, "revelation_type": "Meccan"},
        {"number": 37, "name": "As-Saffat", "english_name": "Those who set the Ranks", "verses": 182, "revelation_type": "Meccan"},
        {"number": 38, "name": "Sad", "english_name": "The Letter 'Sad'", "verses": 88, "revelation_type": "Meccan"},
        {"number": 39, "name": "Az-Zumar", "english_name": "The Troops", "verses": 75, "revelation_type": "Meccan"},
        {"number": 40, "name": "Ghafir", "english_name": "The Forgiver", "verses": 85, "revelation_type": "Meccan"},
        {"number": 41, "name": "Fussilat", "english_name": "Explained in Detail", "verses": 54, "revelation_type": "Meccan"},
        {"number": 42, "name": "Ash-Shuraa", "english_name": "The Consultation", "verses": 53, "revelation_type": "Meccan"},
        {"number": 43, "name": "Az-Zukhruf", "english_name": "The Ornaments of Gold", "verses": 89, "revelation_type": "Meccan"},
        {"number": 44, "name": "Ad-Dukhan", "english_name": "The Smoke", "verses": 59, "revelation_type": "Meccan"},
        {"number": 45, "name": "Al-Jathiyah", "english_name": "The Crouching", "verses": 37, "revelation_type": "Meccan"},
        {"number": 46, "name": "Al-Ahqaf", "english_name": "The Wind-Curved Sandhills", "verses": 35, "revelation_type": "Meccan"},
        {"number": 47, "name": "Muhammad", "english_name": "Muhammad", "verses": 38, "revelation_type": "Medinan"},
        {"number": 48, "name": "Al-Fath", "english_name": "The Victory", "verses": 29, "revelation_type": "Medinan"},
        {"number": 49, "name": "Al-Hujurat", "english_name": "The Rooms", "verses": 18, "revelation_type": "Medinan"},
        {"number": 50, "name": "Qaf", "english_name": "The Letter 'Qaf'", "verses": 45, "revelation_type": "Meccan"},
        {"number": 51, "name": "Adh-Dhariyat", "english_name": "The Winnowing Winds", "verses": 60, "revelation_type": "Meccan"},
        {"number": 52, "name": "At-Tur", "english_name": "The Mount", "verses": 49, "revelation_type": "Meccan"},
        {"number": 53, "name": "An-Najm", "english_name": "The Star", "verses": 62, "revelation_type": "Meccan"},
        {"number": 54, "name": "Al-Qamar", "english_name": "The Moon", "verses": 55, "revelation_type": "Meccan"},
        {"number": 55, "name": "Ar-Rahman", "english_name": "The Beneficent", "verses": 78, "revelation_type": "Medinan"},
        {"number": 56, "name": "Al-Waqi'ah", "english_name": "The Inevitable", "verses": 96, "revelation_type": "Meccan"},
        {"number": 57, "name": "Al-Hadid", "english_name": "The Iron", "verses": 29, "revelation_type": "Medinan"},
        {"number": 58, "name": "Al-Mujadila", "english_name": "The Pleading Woman", "verses": 22, "revelation_type": "Medinan"},
        {"number": 59, "name": "Al-Hashr", "english_name": "The Exile", "verses": 24, "revelation_type": "Medinan"},
        {"number": 60, "name": "Al-Mumtahanah", "english_name": "She that is to be examined", "verses": 13, "revelation_type": "Medinan"},
        {"number": 61, "name": "As-Saf", "english_name": "The Ranks", "verses": 14, "revelation_type": "Medinan"},
        {"number": 62, "name": "Al-Jumu'ah", "english_name": "Friday", "verses": 11, "revelation_type": "Medinan"},
        {"number": 63, "name": "Al-Munafiqun", "english_name": "The Hypocrites", "verses": 11, "revelation_type": "Medinan"},
        {"number": 64, "name": "At-Taghabun", "english_name": "The Mutual Disillusion", "verses": 18, "revelation_type": "Medinan"},
        {"number": 65, "name": "At-Talaq", "english_name": "The Divorce", "verses": 12, "revelation_type": "Medinan"},
        {"number": 66, "name": "At-Tahrim", "english_name": "The Prohibition", "verses": 12, "revelation_type": "Medinan"},
        {"number": 67, "name": "Al-Mulk", "english_name": "The Sovereignty", "verses": 30, "revelation_type": "Meccan"},
        {"number": 68, "name": "Al-Qalam", "english_name": "The Pen", "verses": 52, "revelation_type": "Meccan"},
        {"number": 69, "name": "Al-Haqqah", "english_name": "The Reality", "verses": 52, "revelation_type": "Meccan"},
        {"number": 70, "name": "Al-Ma'arij", "english_name": "The Ascending Stairways", "verses": 44, "revelation_type": "Meccan"},
        {"number": 71, "name": "Nuh", "english_name": "Noah", "verses": 28, "revelation_type": "Meccan"},
        {"number": 72, "name": "Al-Jinn", "english_name": "The Jinn", "verses": 28, "revelation_type": "Meccan"},
        {"number": 73, "name": "Al-Muzzammil", "english_name": "The Enshrouded One", "verses": 20, "revelation_type": "Meccan"},
        {"number": 74, "name": "Al-Muddaththir", "english_name": "The Cloaked One", "verses": 56, "revelation_type": "Meccan"},
        {"number": 75, "name": "Al-Qiyamah", "english_name": "The Resurrection", "verses": 40, "revelation_type": "Meccan"},
        {"number": 76, "name": "Al-Insan", "english_name": "The Man", "verses": 31, "revelation_type": "Medinan"},
        {"number": 77, "name": "Al-Mursalat", "english_name": "The Emissaries", "verses": 50, "revelation_type": "Meccan"},
        {"number": 78, "name": "An-Naba", "english_name": "The Tidings", "verses": 40, "revelation_type": "Meccan"},
        {"number": 79, "name": "An-Nazi'at", "english_name": "Those who drag forth", "verses": 46, "revelation_type": "Meccan"},
        {"number": 80, "name": "'Abasa", "english_name": "He Frowned", "verses": 42, "revelation_type": "Meccan"},
        {"number": 81, "name": "At-Takwir", "english_name": "The Overthrowing", "verses": 29, "revelation_type": "Meccan"},
        {"number": 82, "name": "Al-Infitar", "english_name": "The Cleaving", "verses": 19, "revelation_type": "Meccan"},
        {"number": 83, "name": "Al-Mutaffifin", "english_name": "The Defrauding", "verses": 36, "revelation_type": "Meccan"},
        {"number": 84, "name": "Al-Inshiqaq", "english_name": "The Sundering", "verses": 25, "revelation_type": "Meccan"},
        {"number": 85, "name": "Al-Buruj", "english_name": "The Mansions of the Stars", "verses": 22, "revelation_type": "Meccan"},
        {"number": 86, "name": "At-Tariq", "english_name": "The Nightcommer", "verses": 17, "revelation_type": "Meccan"},
        {"number": 87, "name": "Al-A'la", "english_name": "The Most High", "verses": 19, "revelation_type": "Meccan"},
        {"number": 88, "name": "Al-Ghashiyah", "english_name": "The Overwhelming", "verses": 26, "revelation_type": "Meccan"},
        {"number": 89, "name": "Al-Fajr", "english_name": "The Dawn", "verses": 30, "revelation_type": "Meccan"},
        {"number": 90, "name": "Al-Balad", "english_name": "The City", "verses": 20, "revelation_type": "Meccan"},
        {"number": 91, "name": "Ash-Shams", "english_name": "The Sun", "verses": 15, "revelation_type": "Meccan"},
        {"number": 92, "name": "Al-Layl", "english_name": "The Night", "verses": 21, "revelation_type": "Meccan"},
        {"number": 93, "name": "Ad-Duhaa", "english_name": "The Morning Hours", "verses": 11, "revelation_type": "Meccan"},
        {"number": 94, "name": "Ash-Sharh", "english_name": "The Relief", "verses": 8, "revelation_type": "Meccan"},
        {"number": 95, "name": "At-Tin", "english_name": "The Fig", "verses": 8, "revelation_type": "Meccan"},
        {"number": 96, "name": "Al-'Alaq", "english_name": "The Clot", "verses": 19, "revelation_type": "Meccan"},
        {"number": 97, "name": "Al-Qadr", "english_name": "The Power", "verses": 5, "revelation_type": "Meccan"},
        {"number": 98, "name": "Al-Bayyinah", "english_name": "The Clear Proof", "verses": 8, "revelation_type": "Medinan"},
        {"number": 99, "name": "Az-Zalzalah", "english_name": "The Earthquake", "verses": 8, "revelation_type": "Medinan"},
        {"number": 100, "name": "Al-'Adiyat", "english_name": "The Courser", "verses": 11, "revelation_type": "Meccan"},
        {"number": 101, "name": "Al-Qari'ah", "english_name": "The Calamity", "verses": 11, "revelation_type": "Meccan"},
        {"number": 102, "name": "At-Takathur", "english_name": "The Rivalry in world increase", "verses": 8, "revelation_type": "Meccan"},
        {"number": 103, "name": "Al-'Asr", "english_name": "The Declining Day", "verses": 3, "revelation_type": "Meccan"},
        {"number": 104, "name": "Al-Humazah", "english_name": "The Traducer", "verses": 9, "revelation_type": "Meccan"},
        {"number": 105, "name": "Al-Fil", "english_name": "The Elephant", "verses": 5, "revelation_type": "Meccan"},
        {"number": 106, "name": "Quraysh", "english_name": "Quraysh", "verses": 4, "revelation_type": "Meccan"},
        {"number": 107, "name": "Al-Ma'un", "english_name": "The Small kindnesses", "verses": 7, "revelation_type": "Meccan"},
        {"number": 108, "name": "Al-Kawthar", "english_name": "The Abundance", "verses": 3, "revelation_type": "Meccan"},
        {"number": 109, "name": "Al-Kafirun", "english_name": "The Disbelievers", "verses": 6, "revelation_type": "Meccan"},
        {"number": 110, "name": "An-Nasr", "english_name": "The Divine Support", "verses": 3, "revelation_type": "Medinan"},
        {"number": 111, "name": "Al-Masad", "english_name": "The Palm Fiber", "verses": 5, "revelation_type": "Meccan"},
        {"number": 112, "name": "Al-Ikhlas", "english_name": "The Sincerity", "verses": 4, "revelation_type": "Meccan"},
        {"number": 113, "name": "Al-Falaq", "english_name": "The Daybreak", "verses": 5, "revelation_type": "Meccan"},
        {"number": 114, "name": "An-Nas", "english_name": "Mankind", "verses": 6, "revelation_type": "Meccan"},
    ]
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or RUNTIME_DATA_DIR / "islamic_content" / "quran" / "text"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = 15
        self.cache_duration = timedelta(days=30)  # Cache for 30 days
    
    def get_surahs_list(self) -> list[dict]:
        """Get list of all 114 surahs with metadata."""
        return self.SURAH_INFO
    
    def get_surah_info(self, surah_number: int) -> Optional[dict]:
        """Get metadata for a specific surah."""
        if 1 <= surah_number <= 114:
            return self.SURAH_INFO[surah_number - 1]
        return None
    
    def _get_cache_path(self, surah_number: int, edition: str) -> Path:
        """Get cache file path for a surah."""
        return self.cache_dir / f"surah_{surah_number}_{edition}.json"
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file exists and is not expired."""
        if not cache_path.exists():
            return False
        
        try:
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            return datetime.now() - mtime < self.cache_duration
        except Exception:
            return False
    
    def _read_cache(self, cache_path: Path) -> Optional[dict]:
        """Read surah from cache."""
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to read cache: {e}")
            return None
    
    def _write_cache(self, cache_path: Path, data: dict) -> None:
        """Write surah to cache."""
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Failed to write cache: {e}")
    
    def get_surah(self, surah_number: int, edition: str = "arabic") -> Optional[dict]:
        """
        Get full surah with verses.
        
        Args:
            surah_number: Surah number (1-114)
            edition: Edition type (arabic, english, transliteration)
        
        Returns:
            Dictionary with surah data including verses
        """
        if not 1 <= surah_number <= 114:
            logger.error(f"Invalid surah number: {surah_number}")
            return None
        
        edition_id = self.EDITIONS.get(edition, self.EDITIONS["arabic"])
        cache_path = self._get_cache_path(surah_number, edition)
        
        # Try cache first
        if self._is_cache_valid(cache_path):
            cached = self._read_cache(cache_path)
            if cached:
                logger.debug(f"Using cached surah {surah_number} ({edition})")
                return cached
        
        # Fetch from API
        try:
            url = f"{self.API_BASE}/surah/{surah_number}/{edition_id}"
            logger.info(f"Fetching surah {surah_number} from {url}")
            
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200 and "data" in data:
                surah_data = data["data"]
                result = {
                    "number": surah_data.get("number"),
                    "name": surah_data.get("name"),
                    "english_name": surah_data.get("englishName"),
                    "english_translation": surah_data.get("englishNameTranslation"),
                    "revelation_type": surah_data.get("revelationType"),
                    "verses_count": surah_data.get("numberOfAyahs"),
                    "verses": [
                        {
                            "number": ayah.get("number"),
                            "number_in_surah": ayah.get("numberInSurah"),
                            "text": ayah.get("text"),
                        }
                        for ayah in surah_data.get("ayahs", [])
                    ],
                    "edition": edition,
                    "fetched_at": datetime.now().isoformat()
                }
                
                self._write_cache(cache_path, result)
                logger.info(f"Fetched and cached surah {surah_number} ({edition})")
                return result
            else:
                logger.error(f"API returned error for surah {surah_number}: {data}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch surah {surah_number}: {e}")
            return None
    
    def get_ayah(self, surah_number: int, ayah_number: int, edition: str = "arabic") -> Optional[dict]:
        """
        Get a specific verse (ayah).
        
        Args:
            surah_number: Surah number (1-114)
            ayah_number: Ayah number within the surah
            edition: Edition type (arabic, english, transliteration)
        
        Returns:
            Dictionary with ayah data
        """
        surah = self.get_surah(surah_number, edition)
        if not surah:
            return None
        
        for verse in surah.get("verses", []):
            if verse.get("number_in_surah") == ayah_number:
                return {
                    "surah_number": surah_number,
                    "surah_name": surah.get("english_name"),
                    **verse
                }
        
        logger.error(f"Ayah {ayah_number} not found in surah {surah_number}")
        return None
    
    def get_multi_edition_ayah(self, surah_number: int, ayah_number: int) -> Optional[dict]:
        """
        Get a specific verse in multiple editions (Arabic, English, Transliteration).
        
        Returns:
            Dictionary with ayah in all available editions
        """
        result = {
            "surah_number": surah_number,
            "ayah_number": ayah_number,
            "surah_name": None,
        }
        
        for edition_name, edition_key in [("arabic", "arabic"), ("english", "english"), ("transliteration", "transliteration")]:
            ayah = self.get_ayah(surah_number, ayah_number, edition_key)
            if ayah:
                result["surah_name"] = ayah.get("surah_name")
                result[edition_name] = ayah.get("text")
        
        if result.get("arabic") or result.get("english"):
            return result
        return None
    
    def search_quran(self, query: str, edition: str = "english", limit: int = 20) -> list[dict]:
        """
        Search Quran text.
        
        Note: This is a basic implementation. For production, consider using
        a dedicated search API or implementing full-text search.
        """
        query_lower = query.lower()
        results = []
        
        for surah_num in range(1, 115):
            if len(results) >= limit:
                break
                
            surah = self.get_surah(surah_num, edition)
            if not surah:
                continue
            
            for verse in surah.get("verses", []):
                if query_lower in verse.get("text", "").lower():
                    results.append({
                        "surah_number": surah_num,
                        "surah_name": surah.get("english_name"),
                        "ayah_number": verse.get("number_in_surah"),
                        "text": verse.get("text"),
                        "edition": edition
                    })
                    
                    if len(results) >= limit:
                        break
        
        return results
