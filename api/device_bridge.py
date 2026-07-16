"""Device command bridge — the app→cloud→bed seam (Plan 6).

Backend logic for device auth and (later tasks) sync + result reporting.
Lazy-imports web_server inside functions so contract-test patching of
web_server module attributes keeps working, and so importing this module
stays cheap.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import timedelta
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from auth.jwt_handler import create_access_token
from time_utils import to_iso, utcnow

DEVICE_TOKEN_TTL_MINUTES = 60
REDELIVER_SECONDS = 30
LIVE_WINDOW_SECONDS = 15


class DeviceAuthRequest(BaseModel):
    device_id: str
    firmware_version: str = "1.0.0"
    factory_secret: str = ""


class DeviceTokenRefreshRequest(BaseModel):
    device_id: str
    refresh_token: str


def _canonical_device_id(device_id: str) -> str:
    """Canonical device id — same rule as web_server._extract_device_id_from_qr_payload.

    Pairing stores link rows with this form; the JWT sub, device_sessions keys
    and link lookups must all agree on it or the bed never finds its user.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "", str(device_id or "").strip()).upper()[:80]


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

    device_id = _canonical_device_id(payload.device_id)
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

    device_id = _canonical_device_id(payload.device_id)
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


# ── Sync: commands + desired state down to the bed ───────────────────────────


def _find_user_key_for_device(ws, profile: dict[str, Any], device_id: str) -> str:
    wanted = _canonical_device_id(device_id)
    if not wanted:
        return ""
    links = ws._get_scoped_profile_section(profile, "mobile_bed_links")
    for key, row in links.items():
        if isinstance(row, dict) and _canonical_device_id(row.get("device_id", "")) == wanted:
            return str(key)
    return ""


def _load_alarms(ws, profile: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Alarms in the app dialect (days ISO 1-7).

    Mobile alarms are DB-backed (AlarmRepository, Plan 1); the
    mobile_alarm_schedules profile section is the legacy web path and only
    consulted when the DB has no rows for this user.
    """
    alarms: list[dict[str, Any]] = []
    try:
        from database import AlarmRepository

        for alarm in AlarmRepository().list_alarms(key):
            alarms.append(
                {
                    "alarm_id": str(alarm.id),
                    "time": str(alarm.time),
                    "days": sorted(int(d) + 1 for d in (alarm.days_of_week or [])),
                    "enabled": bool(alarm.enabled),
                    "label": str(alarm.label or ""),
                    "sound": str(alarm.sound or "default"),
                    "vibrate": bool(alarm.vibrate),
                }
            )
    except Exception:
        alarms = []
    if alarms:
        return alarms

    alarms_section = ws._get_scoped_profile_section(profile, "mobile_alarm_schedules")
    raw_alarms = alarms_section.get(key, [])
    raw_alarms = raw_alarms if isinstance(raw_alarms, list) else []
    for row in raw_alarms:
        if not isinstance(row, dict):
            continue
        alarms.append(
            {
                "alarm_id": str(row.get("alarm_id", "") or ""),
                "time": str(row.get("time", "07:00") or "07:00"),
                "days": [int(d) for d in row.get("days", []) if isinstance(d, (int, float))],
                "enabled": bool(row.get("enabled", True)),
                "label": str(row.get("label", "") or ""),
                "sound": str(row.get("sound", "default") or "default"),
                "vibrate": bool(row.get("vibrate", True)),
            }
        )
    return alarms


def _assemble_desired_state(ws, profile: dict[str, Any], key: str) -> dict[str, Any]:
    controls_section = ws._get_scoped_profile_section(profile, "web_device_controls")
    controls = ws._normalize_device_controls(controls_section.get(key, {}))
    lighting = {
        "lights_on": bool(controls.get("lights_on", False)),
        "light_level": int(controls.get("light_level", 65) or 65),
    }

    alarms = _load_alarms(ws, profile, key)

    env = profile.get("environment", {}) if isinstance(profile.get("environment", {}), dict) else {}
    scene_key = str(env.get("saved_tonight_scene_key", "") or "").strip()
    scene = {"scene_key": scene_key} if scene_key else None
    return {"lighting": lighting, "alarms": alarms, "scene": scene}


def _state_version(desired_state: dict[str, Any] | None) -> str:
    if not desired_state:
        return ""
    canonical = json.dumps(desired_state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def device_sync(device: dict[str, Any]) -> dict[str, Any]:
    import web_server as ws

    device_id = str(device.get("device_id", "") or "")
    now = utcnow()
    profile = ws._safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    sessions = ws._get_scoped_profile_section(profile, "device_sessions")
    session_row = (
        sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
    )
    session_row["last_seen"] = to_iso(now)
    sessions[device_id] = session_row
    profile["device_sessions"] = sessions

    key = _find_user_key_for_device(ws, profile, device_id)
    if not key:
        ws._save_profile(profile)
        return {
            "server_time": to_iso(now),
            "commands": [],
            "desired_state": None,
            "state_version": "",
        }

    cmd_section = ws._get_scoped_profile_section(profile, "web_device_commands")
    raw_rows = cmd_section.get(key, [])
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    out_rows: list[dict[str, Any]] = []
    to_dispatch: list[dict[str, Any]] = []
    for row in raw_rows:
        cmd = ws._normalize_command_item(row if isinstance(row, dict) else {})
        status = str(cmd.get("status", "queued") or "queued")
        updated = ws._parse_iso_timestamp(str(cmd.get("updated_at", "") or "")) or now
        stale_dispatch = (
            status == "dispatched" and (now - updated).total_seconds() >= REDELIVER_SECONDS
        )
        if status == "queued" or stale_dispatch:
            cmd["status"] = "dispatched"
            cmd["updated_at"] = to_iso(now)
            to_dispatch.append(
                {
                    "id": str(cmd.get("id", "") or ""),
                    "action": str(cmd.get("action", "") or ""),
                    "params": {},
                    "created_at": str(cmd.get("created_at", "") or ""),
                }
            )
        out_rows.append(cmd)
    cmd_section[key] = out_rows
    profile["web_device_commands"] = cmd_section

    desired_state = _assemble_desired_state(ws, profile, key)
    ws._save_profile(profile)
    return {
        "server_time": to_iso(now),
        "commands": to_dispatch,
        "desired_state": desired_state,
        "state_version": _state_version(desired_state),
    }


# ── Result: the bed reports what really happened ─────────────────────────────


class DeviceCommandResultRequest(BaseModel):
    status: Literal["completed", "failed"]
    detail: str = ""
    actual_state: dict = Field(default_factory=dict)


def device_command_result(
    device: dict[str, Any], command_id: str, payload: DeviceCommandResultRequest
) -> dict[str, Any]:
    import web_server as ws

    device_id = str(device.get("device_id", "") or "")
    profile = ws._safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    key = _find_user_key_for_device(ws, profile, device_id)
    if not key:
        raise HTTPException(status_code=404, detail="Device is not paired")

    cmd_section = ws._get_scoped_profile_section(profile, "web_device_commands")
    raw_rows = cmd_section.get(key, [])
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    target: dict[str, Any] | None = None
    out_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        cmd = ws._normalize_command_item(row if isinstance(row, dict) else {})
        if str(cmd.get("id", "") or "") == str(command_id):
            cmd["status"] = payload.status
            cmd["updated_at"] = ws._now_utc_iso()
            if payload.status == "completed":
                cmd["completed_at"] = ws._now_utc_iso()
            if payload.detail:
                cmd["message"] = str(payload.detail)[:200]
            target = cmd
        out_rows.append(cmd)
    if target is None:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd_section[key] = out_rows
    profile["web_device_commands"] = cmd_section
    ws._store_last_command_result(profile, key, ws._build_last_command_result_from_command(target))
    ws._save_profile(profile)

    links = ws._get_scoped_profile_section(profile, "mobile_bed_links")
    link_row = links.get(key, {}) if isinstance(links.get(key, {}), dict) else {}
    ws._persist_mobile_command_record(
        user_id=str(link_row.get("user_id", "") or key), command=target
    )
    return {"ok": True, "command": target}
