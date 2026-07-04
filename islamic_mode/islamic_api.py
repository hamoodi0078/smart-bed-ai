from __future__ import annotations

import datetime

from fastapi import APIRouter

from islamic_mode.dana_islamic_voice import DanaIslamicVoice
from islamic_mode.hadith_daily import HadithService
from islamic_mode.islamic_calendar import IslamicCalendarService
from islamic_mode.prayer_times import PrayerTimesService
from islamic_mode.ramadan_mode import RamadanMode
from islamic_mode.sunnah_tips import SunnahSleepTips
from islamic_mode.content.quran_text import QuranTextService
from islamic_mode.content.prophet_stories import ProphetStoriesService
from islamic_mode.content.content_manager import ContentManager
from islamic_mode.audio.reciter_catalog import ReciterCatalog
from islamic_mode.audio.quran_recitation import QuranRecitationService


router = APIRouter(prefix="/v1/islamic", tags=["islamic"])

prayer_service = PrayerTimesService()
hadith_service = HadithService()
calendar_service = IslamicCalendarService()
sunnah_tips_service = SunnahSleepTips()
ramadan_mode = RamadanMode(calendar_service=calendar_service, prayer_service=prayer_service)
dana_voice = DanaIslamicVoice(
    hadith_service=hadith_service,
    sunnah_tips=sunnah_tips_service,
    ramadan_mode=ramadan_mode,
)

# New content and audio services
quran_text_service = QuranTextService()
prophet_stories_service = ProphetStoriesService()
content_manager = ContentManager()
quran_audio_service = QuranRecitationService()


def _minutes_until_prayer(prayer_name: str) -> int:
    prayers = prayer_service.get_today_prayers()
    normalized = str(prayer_name or "").strip().lower()
    matched_name = next((name for name in prayers.keys() if name.lower() == normalized), "")
    if not matched_name:
        return 0

    prayer_time = prayers.get(matched_name, "")
    try:
        hour, minute = [int(part) for part in str(prayer_time).split(":")[:2]]
    except Exception:
        return 0

    now = datetime.datetime.now()
    prayer_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if prayer_dt < now:
        if matched_name.lower() == "fajr":
            prayer_dt += datetime.timedelta(days=1)
        else:
            return 0

    return max(0, int((prayer_dt - now).total_seconds() // 60))


@router.get("/prayer-times")
def get_prayer_times() -> dict:
    return prayer_service.get_today_prayers()


@router.get("/next-prayer")
def get_next_prayer() -> dict:
    return prayer_service.get_next_prayer()


@router.get("/hadith/daily")
def get_daily_hadith() -> dict:
    return hadith_service.get_daily_hadith()


@router.get("/hadith/sleep")
def get_sleep_hadith() -> dict:
    return hadith_service.get_sleep_hadith()


@router.get("/hadith/books")
def get_available_hadith_books() -> dict:
    """Get list of available hadith books."""
    return {
        "books": [
            {"key": "bukhari", "name": "Sahih Bukhari", "hadiths": "~7,500"},
            {"key": "muslim", "name": "Sahih Muslim", "hadiths": "~7,000"},
            {"key": "abudawud", "name": "Abu Dawood", "hadiths": "~5,200"},
            {"key": "tirmidhi", "name": "Al-Tirmidhi", "hadiths": "~3,900"},
            {"key": "nasai", "name": "Al-Nasai", "hadiths": "~5,700"},
            {"key": "ibnmajah", "name": "Ibn Majah", "hadiths": "~4,300"},
        ],
        "total_books": 6,
        "total_hadiths": "~33,000+",
    }


@router.get("/hadith/info")
def get_hadith_service_info() -> dict:
    """Get information about the hadith service and current status."""
    cache_path = hadith_service._get_daily_cache_path()
    cached = hadith_service._read_cache(cache_path)

    return {
        "primary_source": "hadithapi.com",
        "fallback_sources": ["random-hadith-generator", "local_collection"],
        "available_books": list(hadith_service.BOOKS.keys()),
        "cache_enabled": True,
        "today_cached": cached is not None,
        "today_source": cached.get("api_source") if cached else None,
    }


@router.get("/calendar")
def get_islamic_calendar() -> dict:
    hijri = calendar_service.get_hijri_date()
    event = calendar_service.get_todays_islamic_event()
    return {"hijri": hijri, "event_today": event}


@router.get("/sunnah-tips")
def get_sunnah_tip() -> dict:
    return {
        "tip": sunnah_tips_service.get_tip_of_night(),
        "total_tips": sunnah_tips_service.get_tips_count(),
    }


@router.get("/sunnah-tips/category/{category}")
def get_sunnah_tips_by_category(category: str) -> dict:
    """
    Get sunnah tips by category.

    Categories: posture, quran, dua, timing, spiritual, physical, family, special
    """
    tips = sunnah_tips_service.get_tip_by_category(category)
    return {"category": category, "tips": tips, "count": len(tips)}


@router.get("/sunnah-tips/all")
def get_all_sunnah_tips() -> dict:
    """Get all sunnah sleep tips."""
    return {
        "tips": sunnah_tips_service.get_all_tips(),
        "total": sunnah_tips_service.get_tips_count(),
    }


@router.get("/sunnah-tips/random")
def get_random_sunnah_tip() -> dict:
    """Get a random sunnah tip."""
    return {"tip": sunnah_tips_service.get_random_tip()}


@router.get("/ramadan/status")
def get_ramadan_status() -> dict:
    active = ramadan_mode.is_active()
    if not active:
        return {"active": False}
    return {
        "active": True,
        "suhoor_wake_time": ramadan_mode.get_suhoor_wake_time(),
        "iftar_time": ramadan_mode.get_iftar_time(),
        "greeting": ramadan_mode.get_ramadan_greeting(),
    }


@router.get("/dana-message/prayer/{prayer_name}")
def get_dana_prayer_message(prayer_name: str) -> dict:
    minutes_until = _minutes_until_prayer(prayer_name)
    message = dana_voice.get_prayer_approaching_message(prayer_name.title(), minutes_until)
    return {"message": message}


@router.get("/location")
def get_prayer_location() -> dict:
    """Get current location settings for prayer times."""
    return prayer_service.get_current_location()


@router.post("/location/update")
def update_prayer_location(
    city: str = None, country: str = None, latitude: float = None, longitude: float = None
) -> dict:
    """Update prayer times location dynamically."""
    prayer_service.update_location(
        city=city, country=country, latitude=latitude, longitude=longitude
    )
    return {
        "success": True,
        "message": "Prayer times location updated",
        "location": prayer_service.get_current_location(),
    }


@router.post("/location/refresh")
def refresh_prayer_location() -> dict:
    """Refresh location using auto-detection if enabled."""
    success = prayer_service.refresh_auto_location()
    return {
        "success": success,
        "message": "Location refreshed" if success else "Auto-detection not enabled or failed",
        "location": prayer_service.get_current_location(),
    }


@router.get("/prayer-times/detailed")
def get_prayer_times_detailed() -> dict:
    """Get prayer times with full location and metadata."""
    bundle = prayer_service.get_today_prayer_bundle()
    return {
        "prayers": bundle.get("prayers", {}),
        "location": bundle.get("location", {}),
        "next_prayer": prayer_service.get_next_prayer(),
    }


# ============= QURAN TEXT ENDPOINTS =============


@router.get("/quran/surahs")
def get_quran_surahs() -> dict:
    """Get list of all 114 surahs with metadata."""
    return {"surahs": quran_text_service.get_surahs_list(), "total": 114}


@router.get("/quran/surah/{surah_number}")
def get_quran_surah(surah_number: int, edition: str = "arabic") -> dict:
    """
    Get full surah with verses.

    Args:
        surah_number: Surah number (1-114)
        edition: Edition type (arabic, english, transliteration)
    """
    surah = quran_text_service.get_surah(surah_number, edition)
    if not surah:
        return {"error": "Surah not found", "surah_number": surah_number}
    return surah


@router.get("/quran/surah/{surah_number}/info")
def get_quran_surah_info(surah_number: int) -> dict:
    """Get metadata for a specific surah."""
    info = quran_text_service.get_surah_info(surah_number)
    if not info:
        return {"error": "Surah not found", "surah_number": surah_number}
    return info


@router.get("/quran/ayah/{surah_number}/{ayah_number}")
def get_quran_ayah(surah_number: int, ayah_number: int, edition: str = "arabic") -> dict:
    """
    Get a specific verse (ayah).

    Args:
        surah_number: Surah number (1-114)
        ayah_number: Ayah number within the surah
        edition: Edition type (arabic, english, transliteration)
    """
    ayah = quran_text_service.get_ayah(surah_number, ayah_number, edition)
    if not ayah:
        return {"error": "Ayah not found", "surah_number": surah_number, "ayah_number": ayah_number}
    return ayah


@router.get("/quran/ayah/{surah_number}/{ayah_number}/multi")
def get_quran_ayah_multi_edition(surah_number: int, ayah_number: int) -> dict:
    """Get a specific verse in multiple editions (Arabic, English, Transliteration)."""
    ayah = quran_text_service.get_multi_edition_ayah(surah_number, ayah_number)
    if not ayah:
        return {"error": "Ayah not found", "surah_number": surah_number, "ayah_number": ayah_number}
    return ayah


@router.get("/quran/search")
def search_quran(q: str, edition: str = "english", limit: int = 20) -> dict:
    """
    Search Quran text.

    Args:
        q: Search query
        edition: Edition to search (arabic, english, transliteration)
        limit: Maximum results to return
    """
    results = quran_text_service.search_quran(q, edition, limit)
    return {"query": q, "edition": edition, "results": results, "count": len(results)}


# ============= PROPHET STORIES ENDPOINTS =============


@router.get("/stories/prophets")
def get_prophets_list() -> dict:
    """Get list of all 25 prophets."""
    prophets = prophet_stories_service.get_all_prophets()
    return {
        "prophets": [
            {"name": p["name"], "arabic": p["arabic"], "title": p["title"]} for p in prophets
        ],
        "total": len(prophets),
    }


@router.get("/stories/prophets/{prophet_name}")
def get_prophet_story(prophet_name: str) -> dict:
    """Get a specific prophet's story by name."""
    story = prophet_stories_service.get_prophet_by_name(prophet_name)
    if not story:
        return {"error": "Prophet story not found", "name": prophet_name}
    return story


@router.get("/stories/prophets/age/{age_group}")
def get_prophets_by_age(age_group: str) -> dict:
    """
    Get prophet stories filtered by age appropriateness.

    Args:
        age_group: 'all', 'children', 'teen_adult'
    """
    stories = prophet_stories_service.get_prophets_by_age_group(age_group)
    return {"age_group": age_group, "stories": stories, "count": len(stories)}


@router.get("/stories/search")
def search_prophet_stories(q: str) -> dict:
    """Search prophet stories by keyword."""
    results = prophet_stories_service.search_stories(q)
    return {"query": q, "results": results, "count": len(results)}


# ============= QURAN AUDIO ENDPOINTS =============


@router.get("/quran/reciters")
def get_reciters() -> dict:
    """Get list of available Quran reciters."""
    reciters = ReciterCatalog.get_all_reciters()
    return {"reciters": reciters, "total": len(reciters)}


@router.get("/quran/reciters/popular")
def get_popular_reciters() -> dict:
    """Get list of popular reciters."""
    reciters = ReciterCatalog.get_popular_reciters()
    return {"reciters": reciters, "total": len(reciters)}


@router.get("/quran/reciters/{reciter_id}")
def get_reciter_info(reciter_id: str) -> dict:
    """Get information about a specific reciter."""
    reciter = ReciterCatalog.get_reciter(reciter_id)
    if not reciter:
        return {"error": "Reciter not found", "reciter_id": reciter_id}
    return reciter


@router.get("/quran/audio/{reciter_id}/surah/{surah_number}/ayah/{ayah_number}/url")
def get_audio_url(reciter_id: str, surah_number: int, ayah_number: int) -> dict:
    """Get audio URL for a specific ayah."""
    url = ReciterCatalog.get_audio_url(reciter_id, surah_number, ayah_number)
    if not url:
        return {"error": "Invalid reciter or ayah numbers"}
    return {
        "reciter_id": reciter_id,
        "surah": surah_number,
        "ayah": ayah_number,
        "url": url,
        "format": "mp3",
    }


@router.post("/quran/audio/download/ayah")
def download_ayah_audio(reciter_id: str, surah: int, ayah: int) -> dict:
    """Download and cache a single ayah audio file."""
    success, message = quran_audio_service.download_ayah(reciter_id, surah, ayah)
    return {
        "success": success,
        "message": message,
        "reciter_id": reciter_id,
        "surah": surah,
        "ayah": ayah,
        "cached": quran_audio_service.is_cached(reciter_id, surah, ayah),
    }


@router.post("/quran/audio/download/surah")
def download_surah_audio(reciter_id: str, surah: int, total_ayahs: int) -> dict:
    """Download all ayahs in a surah."""
    results = quran_audio_service.download_surah(reciter_id, surah, total_ayahs)
    return results


@router.get("/quran/audio/cache/stats")
def get_audio_cache_stats(reciter_id: str = None) -> dict:
    """Get statistics about cached audio files."""
    return quran_audio_service.get_cache_stats(reciter_id)


@router.delete("/quran/audio/cache")
def clear_audio_cache(reciter_id: str = None) -> dict:
    """
    Clear cached audio files.

    Args:
        reciter_id: Clear specific reciter (None = clear all)
    """
    results = quran_audio_service.clear_cache(reciter_id)
    return results


@router.get("/quran/audio/player/status")
def get_player_status() -> dict:
    """Get current audio player status."""
    return {
        "ready": quran_audio_service.is_player_ready(),
        "playing": quran_audio_service.is_playing(),
        "current": quran_audio_service.get_current_playback_info(),
    }


@router.post("/quran/audio/play/ayah")
def play_ayah_audio(
    reciter_id: str, surah: int, ayah: int, download_if_missing: bool = True
) -> dict:
    """Play a single ayah audio."""
    success, message = quran_audio_service.play_ayah(reciter_id, surah, ayah, download_if_missing)
    return {
        "success": success,
        "message": message,
        "reciter_id": reciter_id,
        "surah": surah,
        "ayah": ayah,
    }


@router.post("/quran/audio/playlist/surah")
def create_surah_playlist(reciter_id: str, surah: int, total_ayahs: int) -> dict:
    """Create a playlist for a full surah."""
    success, message = quran_audio_service.create_surah_playlist(reciter_id, surah, total_ayahs)
    return {
        "success": success,
        "message": message,
        "reciter_id": reciter_id,
        "surah": surah,
        "total_ayahs": total_ayahs,
    }


@router.post("/quran/audio/control/play-next")
def audio_play_next(download_if_missing: bool = True) -> dict:
    """Play next ayah in playlist."""
    success, message = quran_audio_service.play_next(download_if_missing)
    return {
        "success": success,
        "message": message,
        "current": quran_audio_service.get_current_playback_info(),
    }


@router.post("/quran/audio/control/play-previous")
def audio_play_previous(download_if_missing: bool = True) -> dict:
    """Play previous ayah in playlist."""
    success, message = quran_audio_service.play_previous(download_if_missing)
    return {
        "success": success,
        "message": message,
        "current": quran_audio_service.get_current_playback_info(),
    }


@router.post("/quran/audio/control/pause")
def audio_pause() -> dict:
    """Pause audio playback."""
    success, message = quran_audio_service.pause()
    return {"success": success, "message": message}


@router.post("/quran/audio/control/resume")
def audio_resume() -> dict:
    """Resume audio playback."""
    success, message = quran_audio_service.resume()
    return {"success": success, "message": message}


@router.post("/quran/audio/control/stop")
def audio_stop() -> dict:
    """Stop audio playback."""
    success, message = quran_audio_service.stop()
    return {"success": success, "message": message}


# ============= UNIFIED SEARCH ENDPOINT =============


@router.get("/search")
def search_all_content(q: str, limit: int = 20) -> dict:
    """Search across all Islamic content (Quran, Prophet stories)."""
    return content_manager.search_all(q, limit)
