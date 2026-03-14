from __future__ import annotations

import datetime

from fastapi import APIRouter

from guest_mode.guest_manager import GuestModeManager
from guest_mode.guest_privacy import GuestPrivacyManager
from guest_mode.guest_settings import GuestSettings


router = APIRouter(prefix="/v1/guest", tags=["guest"])

guest_manager = GuestModeManager()
guest_settings = GuestSettings()
guest_privacy = GuestPrivacyManager()


def _seconds_until(auto_reset_at: str) -> int:
    try:
        target = datetime.datetime.fromisoformat(str(auto_reset_at or "").strip())
    except ValueError:
        return 0
    remaining = int((target - datetime.datetime.now()).total_seconds())
    return max(0, remaining)


@router.post("/activate")
def activate_guest_mode(activated_by: str = "user") -> dict:
    status = guest_manager.activate(activated_by=activated_by)
    guest_privacy.log_guest_action("activate_guest_mode")
    return {
        "status": status,
        "welcome_message": guest_settings.get_guest_welcome_message(),
        "blocked_features": guest_settings.get_blocked_features(),
    }


@router.post("/deactivate")
def deactivate_guest_mode() -> dict:
    status = guest_manager.deactivate()
    guest_privacy.log_guest_action("deactivate_guest_mode")
    clear_result = guest_privacy.clear_session_data()
    return {
        "status": status,
        "message": guest_settings.get_reset_message(),
        "session_data_cleared": bool(clear_result.get("cleared", False)),
    }


@router.get("/status")
def guest_mode_status() -> dict:
    status = guest_manager.get_status()
    active = guest_manager.is_active()
    remaining_seconds = _seconds_until(status.get("auto_reset_at", "")) if active else 0
    return {
        "active": active,
        "status": status,
        "time_remaining_seconds": remaining_seconds,
    }


@router.get("/settings")
def guest_mode_settings() -> dict:
    return {
        "allowed_features": guest_settings.get_allowed_features(),
        "blocked_features": guest_settings.get_blocked_features(),
        "guest_led_settings": guest_settings.get_guest_led_settings(),
    }


@router.get("/privacy")
def guest_mode_privacy() -> dict:
    return guest_privacy.get_privacy_summary()


@router.post("/auto-reset")
def guest_mode_auto_reset() -> dict:
    reset_happened = guest_manager.auto_reset()
    if reset_happened:
        guest_privacy.clear_session_data()
    return {
        "reset_happened": reset_happened,
        "status": guest_manager.get_status(),
    }
