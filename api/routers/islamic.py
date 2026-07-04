"""Islamic feature routes — prayer times, hadith, Ramadan, Qibla.

Routes extracted from web_server.py lines 7255-7293.
These call islamic_mode services directly — no web_server helpers needed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1/mobile/islamic", tags=["islamic"])


def _resolve_prayer_service(user: dict[str, Any], profile: dict[str, Any]):
    """Build a PrayerTimesService from the user's saved location preferences."""
    from config.settings import settings
    from islamic_mode.prayer_times import PrayerTimesService

    prefs = (profile.get("users") or {}).get(str(user.get("user_id", "") or ""), {}) or {}
    location = prefs.get("location") or {}
    lat = location.get("latitude")
    lon = location.get("longitude")
    mode = str(location.get("mode", "auto") or "auto").strip().lower()
    fiqh_method = int(prefs.get("prayer_method") or settings.islamic_prayer_method or 8)

    if mode == "auto" and lat is not None and lon is not None:
        return PrayerTimesService(method=fiqh_method, latitude=float(lat), longitude=float(lon))

    city = str(location.get("city") or settings.islamic_prayer_city or "Kuwait City")
    country = str(location.get("country") or settings.islamic_prayer_country or "Kuwait")
    return PrayerTimesService(city=city, country=country, method=fiqh_method)


@router.get("/overview")
def mobile_islamic_overview(request: Request) -> dict[str, Any]:
    # Inline import avoids circular deps with web_server helpers during migration.
    from web_server import _require_premium_plan, _safe_profile, _mobile_islamic_overview_payload

    user = _require_premium_plan(request)
    profile = _safe_profile() or {}
    overview = _mobile_islamic_overview_payload(user, profile)
    return {"ok": True, **overview}


@router.get("/prayer-times")
def mobile_islamic_prayer_times(request: Request) -> dict[str, Any]:
    from web_server import _require_premium_plan, _safe_profile

    user = _require_premium_plan(request)
    profile = _safe_profile() or {}
    service = _resolve_prayer_service(user, profile)
    bundle = service.get_today_prayer_bundle()
    return {
        "ok": True,
        "prayers": bundle.get("prayers", {}) if isinstance(bundle, dict) else {},
        "location": (bundle.get("location") or {}) if isinstance(bundle, dict) else {},
        "fiqh_method": (bundle.get("method") or 8) if isinstance(bundle, dict) else 8,
    }


@router.get("/next-prayer")
def mobile_islamic_next_prayer(request: Request) -> dict[str, Any]:
    from web_server import _require_premium_plan, _safe_profile

    user = _require_premium_plan(request)
    profile = _safe_profile() or {}
    service = _resolve_prayer_service(user, profile)
    next_prayer = service.get_next_prayer()
    return {
        "ok": True,
        "next_prayer": next_prayer,
        "led_color": service.get_prayer_led_color(str(next_prayer.get("name", "") or "")),
    }
