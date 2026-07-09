"""Islamic feature routes — prayer times, hadith, Ramadan, Qibla.

Free-tier routes (audit P2: the premium gate 403'd demo accounts).
Location resolves from the DB profile first — what POST /v1/mobile/profile
writes — with the legacy voice-profile JSON section as a pre-migration
fallback (audit P0-3).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1/mobile/islamic", tags=["islamic"])


def _prayer_location(user: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Resolve prayer location: DB profile first, legacy JSON fallback."""
    from config.settings import settings

    user_id = str(user.get("user_id", "") or "").strip()
    db_prefs: dict[str, Any] | None = None
    if user_id:
        try:
            from database import ProfileRepository

            db_prefs = ProfileRepository().get_profile_prefs_if_exists(user_id)
        except Exception:
            db_prefs = None

    legacy = (profile.get("users") or {}).get(user_id, {}) or {}
    legacy_loc = legacy.get("location") or {}
    method = int(legacy.get("prayer_method") or settings.islamic_prayer_method or 8)

    if db_prefs:
        return {
            "mode": str(db_prefs.get("location_mode", "auto") or "auto").lower(),
            "latitude": db_prefs.get("latitude"),
            "longitude": db_prefs.get("longitude"),
            "city": str(db_prefs.get("city") or settings.islamic_prayer_city or "Kuwait City"),
            "country": str(
                db_prefs.get("country_code") or settings.islamic_prayer_country or "Kuwait"
            ),
            "method": method,
        }
    return {
        "mode": str(legacy_loc.get("mode", "auto") or "auto").lower(),
        "latitude": legacy_loc.get("latitude"),
        "longitude": legacy_loc.get("longitude"),
        "city": str(legacy_loc.get("city") or settings.islamic_prayer_city or "Kuwait City"),
        "country": str(legacy_loc.get("country") or settings.islamic_prayer_country or "Kuwait"),
        "method": method,
    }


def _resolve_prayer_service(user: dict[str, Any], profile: dict[str, Any]):
    from islamic_mode.prayer_times import PrayerTimesService

    loc = _prayer_location(user, profile)
    if loc["mode"] == "auto" and loc["latitude"] is not None and loc["longitude"] is not None:
        return PrayerTimesService(
            method=loc["method"], latitude=float(loc["latitude"]), longitude=float(loc["longitude"])
        )
    return PrayerTimesService(city=loc["city"], country=loc["country"], method=loc["method"])


@router.get("/overview")
def mobile_islamic_overview(request: Request) -> dict[str, Any]:
    # Inline import avoids circular deps with web_server helpers during migration.
    from web_server import _require_user, _safe_profile, _mobile_islamic_overview_payload

    user = _require_user(request)
    profile = _safe_profile() or {}
    overview = _mobile_islamic_overview_payload(user, profile)
    return {"ok": True, **overview}


@router.get("/prayer-times")
def mobile_islamic_prayer_times(request: Request) -> dict[str, Any]:
    from web_server import _require_user, _safe_profile

    user = _require_user(request)
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
    from web_server import _require_user, _safe_profile

    user = _require_user(request)
    profile = _safe_profile() or {}
    service = _resolve_prayer_service(user, profile)
    next_prayer = service.get_next_prayer()
    return {
        "ok": True,
        "next_prayer": next_prayer,
        "led_color": service.get_prayer_led_color(str(next_prayer.get("name", "") or "")),
    }
