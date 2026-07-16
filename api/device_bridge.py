"""Device command bridge — the app→cloud→bed seam (Plan 6).

Backend logic for device auth and (later tasks) sync + result reporting.
Lazy-imports web_server inside functions so contract-test patching of
web_server module attributes keeps working, and so importing this module
stays cheap.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from auth.jwt_handler import create_access_token
from time_utils import to_iso, utcnow

DEVICE_TOKEN_TTL_MINUTES = 60


class DeviceAuthRequest(BaseModel):
    device_id: str
    firmware_version: str = "1.0.0"
    factory_secret: str = ""


class DeviceTokenRefreshRequest(BaseModel):
    device_id: str
    refresh_token: str


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _default_entitlement() -> dict[str, Any]:
    return {"tier": "free", "status": "active", "cloud_enabled": False, "features": {}}


def _issue_device_bundle(
    ws, profile: dict[str, Any], device_id: str, firmware_version: str
) -> dict[str, Any]:
    expires_at = utcnow() + timedelta(minutes=DEVICE_TOKEN_TTL_MINUTES)
    access_token = create_access_token(
        user_id=device_id,
        jti=secrets.token_hex(16),
        exp=expires_at,
        client_name="bed-device",
        role="device",
    )
    refresh_token = secrets.token_urlsafe(32)
    sessions = ws._get_scoped_profile_section(profile, "device_sessions")
    row = sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
    row.update(
        {
            "refresh_token_hash": _hash_refresh_token(refresh_token),
            "firmware_version": str(firmware_version or "1.0.0"),
            "last_seen": to_iso(utcnow()),
            "created_at": str(row.get("created_at", "") or "") or to_iso(utcnow()),
        }
    )
    sessions[device_id] = row
    profile["device_sessions"] = sessions
    ws._save_profile(profile)
    return {
        "device_access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": to_iso(expires_at),
        "entitlement": _default_entitlement(),
    }


def device_auth(payload: DeviceAuthRequest) -> dict[str, Any]:
    import web_server as ws

    device_id = str(payload.device_id or "").strip()
    if not device_id:
        raise HTTPException(status_code=422, detail="device_id is required")

    required_secret = os.getenv("DEVICE_FACTORY_SECRET", "").strip()
    if required_secret and not hmac.compare_digest(
        str(payload.factory_secret or ""), required_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid factory secret")

    from qr_code.pair_device import get_device_status

    status_payload = get_device_status(device_id)
    if not bool(status_payload.get("success", False)):
        raise HTTPException(status_code=404, detail="Device is not provisioned")

    profile = ws._safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    return _issue_device_bundle(ws, profile, device_id, payload.firmware_version)


def device_token_refresh(payload: DeviceTokenRefreshRequest) -> dict[str, Any]:
    import web_server as ws

    device_id = str(payload.device_id or "").strip()
    presented = str(payload.refresh_token or "").strip()
    if not device_id or not presented:
        raise HTTPException(status_code=422, detail="device_id and refresh_token are required")

    profile = ws._safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    sessions = ws._get_scoped_profile_section(profile, "device_sessions")
    row = sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
    stored_hash = str(row.get("refresh_token_hash", "") or "")
    if not stored_hash or not hmac.compare_digest(stored_hash, _hash_refresh_token(presented)):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _issue_device_bundle(ws, profile, device_id, str(row.get("firmware_version", "") or ""))
