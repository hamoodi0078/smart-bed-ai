"""Catalog of Quran reciters with audio sources."""

from __future__ import annotations


class ReciterCatalog:
    """
    Catalog of available Quran reciters.
    
    Uses everyayah.com as the primary source for Quran recitations.
    """
    
    RECITERS = {
        "mishary": {
            "id": "mishary",
            "name": "Mishary Rashid Alafasy",
            "arabic_name": "مشاري بن راشد العفاسي",
            "language": "Arabic",
            "style": "Warsh",
            "audio_quality": "128kbps",
            "country": "Kuwait",
            "base_url": "https://everyayah.com/data/Alafasy_128kbps/",
            "format": "mp3",
            "popular": True,
            "description": "One of the most popular reciters, known for his beautiful melodious voice."
        },
        "sudais": {
            "id": "sudais",
            "name": "Abdurrahman As-Sudais",
            "arabic_name": "عبد الرحمن السديس",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "128kbps",
            "country": "Saudi Arabia",
            "base_url": "https://everyayah.com/data/Abdul_Basit_Murattal_192kbps/",  
            "format": "mp3",
            "popular": True,
            "description": "Imam of Masjid al-Haram in Makkah, known for his emotional recitation."
        },
        "husary": {
            "id": "husary",
            "name": "Mahmoud Khalil Al-Husary",
            "arabic_name": "محمود خليل الحصري",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "128kbps",
            "country": "Egypt",
            "base_url": "https://everyayah.com/data/Husary_128kbps/",
            "format": "mp3",
            "popular": True,
            "description": "Classic Egyptian reciter, excellent for learning proper pronunciation."
        },
        "minshawi": {
            "id": "minshawi",
            "name": "Mohamed Siddiq Al-Minshawi",
            "arabic_name": "محمد صديق المنشاوي",
            "language": "Arabic",
            "style": "Mujawwad",
            "audio_quality": "128kbps",
            "country": "Egypt",
            "base_url": "https://everyayah.com/data/Minshawy_Mujawwad_192kbps/",
            "format": "mp3",
            "popular": True,
            "description": "Renowned for his melodious mujawwad (melodic) style."
        },
        "ghamadi": {
            "id": "ghamadi",
            "name": "Saad Al-Ghamadi",
            "arabic_name": "سعد الغامدي",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "128kbps",
            "country": "Saudi Arabia",
            "base_url": "https://everyayah.com/data/Ghamadi_40kbps/",
            "format": "mp3",
            "popular": True,
            "description": "Popular Saudi reciter with a clear and beautiful voice."
        },
        "ajmi": {
            "id": "ajmi",
            "name": "Ahmed ibn Ali Al-Ajmi",
            "arabic_name": "أحمد بن علي العجمي",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "128kbps",
            "country": "Saudi Arabia",
            "base_url": "https://everyayah.com/data/Ahmed_ibn_Ali_al-Ajamy_128kbps_ketaballah.net/",
            "format": "mp3",
            "popular": False,
            "description": "Known for his emotional and heartfelt recitation."
        },
        "shuraim": {
            "id": "shuraim",
            "name": "Saud Ash-Shuraim",
            "arabic_name": "سعود الشريم",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "64kbps",
            "country": "Saudi Arabia",
            "base_url": "https://everyayah.com/data/Salaah_AbdulRahman_Bukhatir_128kbps/",
            "format": "mp3",
            "popular": True,
            "description": "Imam of Masjid al-Haram, distinctive powerful voice."
        },
        "basfar": {
            "id": "basfar",
            "name": "Abdullah Basfar",
            "arabic_name": "عبدالله بصفر",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "32kbps",
            "country": "Saudi Arabia",
            "base_url": "https://everyayah.com/data/Abdullah_Basfar_192kbps/",
            "format": "mp3",
            "popular": False,
            "description": "Clear and precise recitation, good for memorization."
        },
        "jibreen": {
            "id": "jibreen",
            "name": "Ibrahim Al-Jibreen",
            "arabic_name": "إبراهيم الجبرين",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "128kbps",
            "country": "Saudi Arabia",
            "base_url": "https://everyayah.com/data/Ibrahim_Akhdar_32kbps/",
            "format": "mp3",
            "popular": False,
            "description": "Young reciter with a melodious voice."
        },
        "rifai": {
            "id": "rifai",
            "name": "Hani Ar-Rifai",
            "arabic_name": "هاني الرفاعي",
            "language": "Arabic",
            "style": "Hafs",
            "audio_quality": "192kbps",
            "country": "Saudi Arabia",
            "base_url": "https://everyayah.com/data/Hani_Rifai_192kbps/",
            "format": "mp3",
            "popular": False,
            "description": "Powerful and emotional recitation style."
        }
    }
    
    @classmethod
    def get_all_reciters(cls) -> list[dict]:
        """Get list of all available reciters."""
        return list(cls.RECITERS.values())
    
    @classmethod
    def get_popular_reciters(cls) -> list[dict]:
        """Get list of popular reciters."""
        return [r for r in cls.RECITERS.values() if r.get("popular", False)]
    
    @classmethod
    def get_reciter(cls, reciter_id: str) -> dict | None:
        """Get a specific reciter by ID."""
        return cls.RECITERS.get(reciter_id)
    
    @classmethod
    def get_reciter_by_name(cls, name: str) -> dict | None:
        """Get a reciter by name (case-insensitive search)."""
        name_lower = name.lower()
        for reciter in cls.RECITERS.values():
            if (name_lower in reciter["name"].lower() or
                name_lower in reciter.get("arabic_name", "").lower() or
                name_lower == reciter["id"]):
                return reciter
        return None
    
    @classmethod
    def get_audio_url(cls, reciter_id: str, surah: int, ayah: int) -> str | None:
        """
        Get audio URL for a specific ayah.
        
        Args:
            reciter_id: Reciter identifier
            surah: Surah number (1-114)
            ayah: Ayah number within surah
        
        Returns:
            Full URL to the MP3 file, or None if invalid
        """
        reciter = cls.get_reciter(reciter_id)
        if not reciter:
            return None
        
        if not (1 <= surah <= 114):
            return None
        
        # Format: {base_url}{surah:03d}{ayah:03d}.mp3
        # Example: https://everyayah.com/data/Alafasy_128kbps/001001.mp3
        filename = f"{surah:03d}{ayah:03d}.{reciter['format']}"
        return f"{reciter['base_url']}{filename}"
    
    @classmethod
    def get_surah_audio_urls(cls, reciter_id: str, surah: int, total_ayahs: int) -> list[str]:
        """
        Get audio URLs for all ayahs in a surah.
        
        Args:
            reciter_id: Reciter identifier
            surah: Surah number (1-114)
            total_ayahs: Total number of ayahs in the surah
        
        Returns:
            List of URLs for all ayahs
        """
        urls = []
        for ayah in range(1, total_ayahs + 1):
            url = cls.get_audio_url(reciter_id, surah, ayah)
            if url:
                urls.append(url)
        return urls
