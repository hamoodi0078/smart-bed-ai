"""User profile and settings routes — fully DB-backed via ProfileRepository.

Routes:
  GET  /v1/mobile/profile
  POST /v1/mobile/profile
  GET  /v1/mobile/settings
  POST /v1/mobile/settings
  GET  /v1/mobile/routine
  POST /v1/mobile/routine
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.middleware import get_current_user
from database import ProfileRepository

router = APIRouter(tags=["profile"])


def _profile_repo() -> ProfileRepository:
    # Per-request construction is cheap now that the connection is shared;
    # an import-time global would pin whatever DATABASE_URL was set first.
    return ProfileRepository()


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class UserProfilePrefsRequest(BaseModel):
    display_name: str = Field(default="", max_length=256)
    timezone: str = Field(default="Asia/Kuwait", max_length=64)
    push_enabled: bool = True
    email_enabled: bool = False
    location_mode: Literal["auto", "manual"] = "auto"
    country_code: str = Field(default="", max_length=8)
    city: str = Field(default="", max_length=128)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    theme_mode: Literal["system", "dark", "light"] = "system"


class UserSettingsRequest(BaseModel):
    response_style: str = Field(default="balanced", max_length=64)
    engagement_level: str = Field(default="high", max_length=64)
    wind_down_minutes: int = Field(default=45, ge=0, le=480)
    partner_mode_enabled: bool = False
    bedtime_drift_automation_enabled: bool = True
    quiet_hours_override_limit_minutes: int = Field(default=120, ge=0, le=480)
    weekly_insight_enabled: bool = True


class UserRoutineRequest(BaseModel):
    bedtime: str = Field(default="22:30", pattern=r"^\d{2}:\d{2}$")
    wake: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    weekends_different: bool = False
    weekend_bedtime: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekend_wake: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolved_display_name(prefs: dict[str, Any], user_id: str) -> str:
    name = str(prefs.get("display_name") or "").strip()
    return name if name else user_id


def _location_summary(prefs: dict[str, Any]) -> dict[str, Any]:
    city = str(prefs.get("city") or "").strip()
    country = str(prefs.get("country_code") or "").strip()
    parts = [p for p in [city, country] if p]
    return {
        "label": ", ".join(parts) if parts else "Location pending",
        "city": city,
        "country_code": country,
        "latitude": prefs.get("latitude"),
        "longitude": prefs.get("longitude"),
        "mode": prefs.get("location_mode", "auto"),
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/v1/mobile/profile")
def mobile_profile(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    uid: str = current_user["sub"]
    prefs = _profile_repo().get_profile_prefs(uid)
    return {
        "ok": True,
        "profile": prefs,
        "resolved_display_name": _resolved_display_name(prefs, uid),
        "resolved_location": _location_summary(prefs),
    }


@router.post("/v1/mobile/profile")
def upsert_mobile_profile(
    payload: UserProfilePrefsRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    uid: str = current_user["sub"]
    updated = _profile_repo().upsert_profile_prefs(uid, **payload.model_dump())
    return {
        "ok": True,
        "profile": updated,
        "resolved_display_name": _resolved_display_name(updated, uid),
    }


@router.get("/v1/mobile/settings")
def mobile_settings(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    uid: str = current_user["sub"]
    settings = _profile_repo().get_settings(uid)
    return {"ok": True, "settings": settings}


@router.post("/v1/mobile/settings")
def upsert_mobile_settings(
    payload: UserSettingsRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    uid: str = current_user["sub"]
    updated = _profile_repo().upsert_settings(uid, **payload.model_dump())
    return {"ok": True, "settings": updated}


@router.get("/v1/mobile/routine")
def mobile_routine(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    uid: str = current_user["sub"]
    routine = _profile_repo().get_routine(uid)
    return {"ok": True, "routine": routine}


@router.post("/v1/mobile/routine")
def upsert_mobile_routine(
    payload: UserRoutineRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    uid: str = current_user["sub"]
    updated = _profile_repo().upsert_routine(uid, **payload.model_dump(exclude_none=True))
    return {"ok": True, "routine": updated}
