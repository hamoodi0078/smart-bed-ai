from __future__ import annotations

import datetime

from fastapi import APIRouter

from islamic_mode.dana_islamic_voice import DanaIslamicVoice
from islamic_mode.hadith_daily import HadithService
from islamic_mode.islamic_calendar import IslamicCalendarService
from islamic_mode.prayer_times import PrayerTimesService
from islamic_mode.ramadan_mode import RamadanMode
from islamic_mode.sunnah_tips import SunnahSleepTips


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
            {"key": "ibnmajah", "name": "Ibn Majah", "hadiths": "~4,300"}
        ],
        "total_books": 6,
        "total_hadiths": "~33,000+"
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
        "today_source": cached.get("api_source") if cached else None
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
        "total_tips": sunnah_tips_service.get_tips_count()
    }


@router.get("/sunnah-tips/category/{category}")
def get_sunnah_tips_by_category(category: str) -> dict:
    """
    Get sunnah tips by category.
    
    Categories: posture, quran, dua, timing, spiritual, physical, family, special
    """
    tips = sunnah_tips_service.get_tip_by_category(category)
    return {
        "category": category,
        "tips": tips,
        "count": len(tips)
    }


@router.get("/sunnah-tips/all")
def get_all_sunnah_tips() -> dict:
    """Get all sunnah sleep tips."""
    return {
        "tips": sunnah_tips_service.get_all_tips(),
        "total": sunnah_tips_service.get_tips_count()
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
    city: str = None,
    country: str = None,
    latitude: float = None,
    longitude: float = None
) -> dict:
    """Update prayer times location dynamically."""
    prayer_service.update_location(
        city=city,
        country=country,
        latitude=latitude,
        longitude=longitude
    )
    return {
        "success": True,
        "message": "Prayer times location updated",
        "location": prayer_service.get_current_location()
    }


@router.post("/location/refresh")
def refresh_prayer_location() -> dict:
    """Refresh location using auto-detection if enabled."""
    success = prayer_service.refresh_auto_location()
    return {
        "success": success,
        "message": "Location refreshed" if success else "Auto-detection not enabled or failed",
        "location": prayer_service.get_current_location()
    }


@router.get("/prayer-times/detailed")
def get_prayer_times_detailed() -> dict:
    """Get prayer times with full location and metadata."""
    bundle = prayer_service.get_today_prayer_bundle()
    return {
        "prayers": bundle.get("prayers", {}),
        "location": bundle.get("location", {}),
        "next_prayer": prayer_service.get_next_prayer()
    }
