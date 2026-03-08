from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
import base64
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

from Storage.io import atomic_write_json, locked_read_json
from Storage.subscription_store import SubscriptionStore
from automations.defaults import build_default_automations
from automations.registry import (
    DEFAULT_QUIET_HOURS_WINDOW,
    AutomationRegistry,
    is_in_quiet_hours,
    is_quiet_hours_override_active,
)
from ai.conversation_engine import ConversationEngine
from ai.emotion_router import detect_emotion_state
from ai.long_term_memory import LongTermMemoryStore
from ai.voice_circuit_breaker import write_voice_circuit_reset_signal
from config import LONG_TERM_MEMORY_PATH, RUNTIME_DATA_DIR, USER_PROFILE_PATH, settings
from core.structured_logging import emit_json_log
from time_utils import from_iso, to_iso, utcnow

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
ASSETS_DIR = WEB_DIR / "assets"
PROFILE_PATH = USER_PROFILE_PATH
WEB_MEMORY_DIR = RUNTIME_DATA_DIR / "web_memory"
AUTOMATION_STATE_PATH = RUNTIME_DATA_DIR / "automations_state.json"
store = SubscriptionStore()
_CHAT_ENGINE_LOCK = threading.RLock()
_CHAT_ENGINES: dict[str, ConversationEngine] = {}

_SENSITIVE_EXACT_KEYS = {"access_token", "refresh_token", "password_hash"}
_MAX_CHAT_ENGINES = 200
_DEVICE_STALE_WINDOW_SECONDS = 180
_TRACE_ID_HEADER = "X-Trace-Id"
SCENE_PREVIEW_SECONDS = 3.0
_METRICS_REQUEST_COUNT = Counter(
    "smart_bed_http_requests_total",
    "Total HTTP requests handled by the Smart Bed API",
    ["method", "path", "status_code"],
)
_METRICS_REQUEST_LATENCY = Histogram(
    "smart_bed_http_request_latency_seconds",
    "HTTP request latency in seconds for the Smart Bed API",
    ["method", "path"],
)
_METRICS_ERROR_COUNT = Counter(
    "smart_bed_http_errors_total",
    "Total HTTP error responses from the Smart Bed API",
    ["method", "path", "status_code"],
)


_cors_origins_raw = str(settings.web_allowed_origins_raw or "http://127.0.0.1:8001,http://localhost:8001")
ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
logger = logging.getLogger("web_runtime")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

TELEMETRY = {
    "auth_user_login_success": 0,
    "auth_user_login_failure": 0,
    "auth_admin_login_success": 0,
    "auth_admin_login_failure": 0,
    "auth_register_success": 0,
    "auth_register_failure": 0,
    "guard_user_denied": 0,
    "guard_admin_denied": 0,
    "chat_requests": 0,
    "chat_denied": 0,
    "same_origin_denied": 0,
}

app = FastAPI(title="Dana Abuhalifa Web Runtime", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = f"req_{secrets.token_hex(4)}"
    request.state.trace_id = trace_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = max(0.0, time.perf_counter() - started)
    status_code = int(getattr(response, "status_code", 200) or 200)
    method = str(request.method or "GET")
    path = str(request.url.path or "/")
    status_key = str(status_code)

    _METRICS_REQUEST_COUNT.labels(method=method, path=path, status_code=status_key).inc()
    _METRICS_REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
    if status_code >= 400:
        _METRICS_ERROR_COUNT.labels(method=method, path=path, status_code=status_key).inc()

    response.headers[_TRACE_ID_HEADER] = trace_id
    _event(
        "info",
        "http_request",
        trace_id=trace_id,
        method=method,
        path=path,
        status_code=status_code,
        latency_ms=round(elapsed * 1000.0, 2),
    )
    return response


class ChatRequest(BaseModel):
    message: str


class CommandRequest(BaseModel):
    text: str
    source: str = "web"


class BedStateV2State(BaseModel):
    emotion_state: str
    active_personality: str
    biometric_summary: dict[str, Any]
    device_health_status: dict[str, Any]


class BedStateV2Response(BaseModel):
    schema_version: str
    capabilities: list[str]
    updated_at: str
    stale: bool
    device_online: bool
    source: Literal["raspberry_pi", "cache", "mock", "simulator", "memory"]
    state: BedStateV2State


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class UserSettingsRequest(BaseModel):
    response_style: str = "balanced"
    engagement_level: str = "high"
    wind_down_minutes: int = 45
    partner_mode_enabled: bool = False


class AdminActionRequest(BaseModel):
    action: str


class UserRoutineRequest(BaseModel):
    bedtime: str = "22:30"
    wake: str = "07:00"
    weekends: bool = True


class UserProfilePrefsRequest(BaseModel):
    display_name: str = "User"
    timezone: str = "Asia/Kuwait"
    push_enabled: bool = True
    email_enabled: bool = False


class UserDeviceControlRequest(BaseModel):
    lights_on: bool = False
    audio_on: bool = False
    alarm_on: bool = True
    light_level: int = 65


class UserActionRequest(BaseModel):
    action: str


class UserDeviceCommandRequest(BaseModel):
    action: str


class SceneSelectionRequest(BaseModel):
    scene_key: str


class SpotifyPlaybackRequest(BaseModel):
    action: str
    device_id: str = ""
    playlist_uri: str = ""
    volume_percent: int = 50


def _safe_profile() -> dict[str, Any]:
    try:
        return locked_read_json(PROFILE_PATH)
    except Exception as exc:
        emit_json_log(
            logger,
            level="error",
            event_type="profile_read_failed",
            trace_id="web_runtime",
            metadata={
                "path": str(PROFILE_PATH),
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(status_code=500, detail="Profile storage read failed") from exc


def _latest_emotion_state(profile: dict[str, Any]) -> str:
    runtime = profile.get("personality_runtime", {}) if isinstance(profile, dict) else {}
    history = runtime.get("emotion_history", []) if isinstance(runtime.get("emotion_history", []), list) else []
    if not history:
        return "neutral"
    last = history[-1] if isinstance(history[-1], dict) else {}
    state = str(last.get("state", "neutral") or "neutral").strip().lower()
    return state or "neutral"


def _active_personality(profile: dict[str, Any]) -> str:
    adaptive = profile.get("adaptive_personality", {}) if isinstance(profile, dict) else {}
    selected = str(adaptive.get("last_selected", "") or "").strip().lower()
    if selected:
        return selected
    prefs = profile.get("preferences", {}) if isinstance(profile, dict) else {}
    fallback = str(prefs.get("personality", "guide") or "guide").strip().lower()
    return fallback or "guide"


def _last_memory_context() -> str:
    try:
        return LongTermMemoryStore(path=str(LONG_TERM_MEMORY_PATH)).latest_memory_context()
    except Exception:
        return ""


def _biometric_summary(profile: dict[str, Any]) -> dict[str, Any]:
    sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
    bedtime_history = sleep.get("bedtime_history", []) if isinstance(sleep.get("bedtime_history", []), list) else []
    wake_history = sleep.get("wake_history", []) if isinstance(sleep.get("wake_history", []), list) else []
    partner_mode = sleep.get("partner_mode", {}) if isinstance(sleep.get("partner_mode", {}), dict) else {}

    return {
        "recovery_mode": bool(sleep.get("recovery_mode", False)),
        "challenge_level": int(sleep.get("challenge_level", 1) or 1),
        "night_wake_count": int(sleep.get("night_wake_count", 0) or 0),
        "bedtime_samples": len(bedtime_history),
        "wake_samples": len(wake_history),
        "partner_mode_enabled": bool(partner_mode.get("enabled", False)),
        "last_bedtime_drift_alert_date": str(sleep.get("last_bedtime_drift_alert_date", "") or ""),
    }


def _device_health_status(profile: dict[str, Any]) -> dict[str, Any]:
    hardware = profile.get("hardware", {}) if isinstance(profile, dict) else {}
    environment = profile.get("environment", {}) if isinstance(profile, dict) else {}
    runtime_flags = profile.get("runtime_flags", {}) if isinstance(profile, dict) else {}
    spotify_tokens = profile.get("spotify_tokens", {}) if isinstance(profile, dict) else {}

    return {
        "deepgram_configured": bool(str(settings.deepgram_api_key or "").strip()),
        "spotify_connected_users": len(spotify_tokens) if isinstance(spotify_tokens, dict) else 0,
        "led": {
            "user_strip_pin": int(hardware.get("user_strip_pin", 18) or 18),
            "state_strip_pin": int(hardware.get("state_strip_pin", 13) or 13),
            "user_strip_led_count": int(hardware.get("user_strip_led_count", 120) or 120),
            "state_strip_led_count": int(hardware.get("state_strip_led_count", 60) or 60),
        },
        "last_scene_key": str(environment.get("last_scene_key", "") or ""),
        "last_preload_phase": str(environment.get("last_preload_phase", "") or ""),
        "sensor_pressure_active": bool(runtime_flags.get("sensor_pressure_active", False)),
        "sensor_motion_active": bool(runtime_flags.get("sensor_motion_active", False)),
    }


def _save_profile(payload: dict[str, Any]):
    try:
        atomic_write_json(PROFILE_PATH, payload if isinstance(payload, dict) else {})
    except Exception as exc:
        emit_json_log(
            logger,
            level="error",
            event_type="profile_write_failed",
            trace_id="web_runtime",
            metadata={
                "path": str(PROFILE_PATH),
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(status_code=500, detail="Profile storage write failed") from exc


def _purge_profile_user_data(profile: dict[str, Any], user: dict[str, Any]) -> int:
    key_candidates = {
        str(user.get("user_id", "") or "").strip(),
        str(user.get("email", "") or "").strip().lower(),
    }
    key_candidates = {k for k in key_candidates if k}
    if not key_candidates:
        return 0

    removed = 0
    section_keys = (
        "web_settings",
        "web_routines",
        "web_profile_prefs",
        "web_device_controls",
        "web_timeline",
        "web_device_commands",
        "spotify_tokens",
    )
    for section_key in section_keys:
        section = profile.get(section_key, {})
        if not isinstance(section, dict):
            continue
        for candidate in key_candidates:
            if candidate in section:
                del section[candidate]
                removed += 1
        profile[section_key] = section
    return removed


def _normalize_user_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    response_style = str(data.get("response_style", "balanced")).strip().lower()
    engagement_level = str(data.get("engagement_level", "high")).strip().lower()
    allowed_styles = {"balanced", "coaching", "calm"}
    allowed_engagement = {"high", "medium", "low"}
    if response_style not in allowed_styles:
        response_style = "balanced"
    if engagement_level not in allowed_engagement:
        engagement_level = "high"

    try:
        wind_down = int(data.get("wind_down_minutes", 45) or 45)
    except Exception:
        wind_down = 45
    wind_down = max(15, min(120, wind_down))

    return {
        "response_style": response_style,
        "engagement_level": engagement_level,
        "wind_down_minutes": wind_down,
        "partner_mode_enabled": bool(data.get("partner_mode_enabled", False)),
    }


def _profile_user_settings(profile: dict[str, Any], user: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return defaults
    settings_map = profile.get("web_settings", {})
    if not isinstance(settings_map, dict):
        return defaults

    user_id = str(user.get("user_id", "")).strip()
    email = str(user.get("email", "")).strip().lower()
    raw = {}
    if user_id and isinstance(settings_map.get(user_id), dict):
        raw = settings_map.get(user_id, {})
    elif email and isinstance(settings_map.get(email), dict):
        raw = settings_map.get(email, {})

    merged = {**defaults, **(raw if isinstance(raw, dict) else {})}
    return _normalize_user_settings(merged)


def _user_profile_key(user: dict[str, Any]) -> str:
    user_id = str(user.get("user_id", "")).strip()
    if user_id:
        return user_id
    return str(user.get("email", "")).strip().lower()


def _get_scoped_profile_section(profile: dict[str, Any], section_key: str) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    section = profile.get(section_key, {})
    return section if isinstance(section, dict) else {}


def _normalize_user_routine(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    bedtime = str(data.get("bedtime", "22:30") or "22:30").strip()
    wake = str(data.get("wake", "07:00") or "07:00").strip()
    if len(bedtime) != 5 or bedtime[2] != ":":
        bedtime = "22:30"
    if len(wake) != 5 or wake[2] != ":":
        wake = "07:00"
    return {
        "bedtime": bedtime,
        "wake": wake,
        "weekends": bool(data.get("weekends", True)),
    }


def _normalize_user_profile_prefs(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    display_name = str(data.get("display_name", "User") or "User").strip()
    timezone = str(data.get("timezone", "Asia/Kuwait") or "Asia/Kuwait").strip()
    if not display_name:
        display_name = "User"
    if not timezone:
        timezone = "Asia/Kuwait"
    return {
        "display_name": display_name,
        "timezone": timezone,
        "push_enabled": bool(data.get("push_enabled", True)),
        "email_enabled": bool(data.get("email_enabled", False)),
    }


def _normalize_device_controls(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    try:
        light_level = int(data.get("light_level", 65) or 65)
    except Exception:
        light_level = 65
    light_level = max(10, min(100, light_level))
    return {
        "lights_on": bool(data.get("lights_on", False)),
        "audio_on": bool(data.get("audio_on", False)),
        "alarm_on": bool(data.get("alarm_on", True)),
        "light_level": light_level,
    }


def _sanitize_user_key(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "guest"
    safe = re.sub(r"[^a-z0-9._-]+", "_", raw).strip("._-")
    return (safe or "guest")[:80]


def _memory_store_for_user(user_key: str) -> LongTermMemoryStore:
    safe_key = _sanitize_user_key(user_key)
    return LongTermMemoryStore(path=str(WEB_MEMORY_DIR / f"{safe_key}.json"))


def _chat_engine_for_user(user_key: str) -> ConversationEngine:
    safe_key = _sanitize_user_key(user_key)
    api_key = str(settings.deepgram_api_key or "").strip()
    model = str(settings.deepgram_voice_agent_model or "voice-agent-conversational").strip()
    voice_agent_url = str(settings.deepgram_voice_agent_url or "https://agent.deepgram.com/v1/agent/converse").strip()

    with _CHAT_ENGINE_LOCK:
        existing = _CHAT_ENGINES.get(safe_key)
        if (
            existing is not None
            and existing.api_key == api_key
            and existing.model == model
            and existing.voice_agent_url == voice_agent_url
        ):
            return existing

        engine = ConversationEngine(
            api_key=api_key,
            model=model,
            timeout_seconds=12,
            voice_agent_url=voice_agent_url,
        )
        _CHAT_ENGINES[safe_key] = engine
        while len(_CHAT_ENGINES) > _MAX_CHAT_ENGINES:
            oldest_key = next(iter(_CHAT_ENGINES))
            del _CHAT_ENGINES[oldest_key]
        return engine


def _chat_personality_from_settings(settings_payload: dict[str, Any]) -> str:
    style = str((settings_payload or {}).get("response_style", "balanced") or "balanced").strip().lower()
    if style == "coaching":
        return "coach"
    if style == "calm":
        return "therapist"
    return "guide"


def _chat_cognitive_load_mode(settings_payload: dict[str, Any]) -> str:
    engagement = str((settings_payload or {}).get("engagement_level", "high") or "high").strip().lower()
    if engagement == "low":
        return "exhausted"
    if engagement == "medium":
        return "reduced"
    return "normal"


def _chat_local_fallback(message: str) -> str:
    lower = str(message or "").strip().lower()
    if "wind" in lower and "down" in lower:
        return "I can help start wind-down autopilot. Open Bed controls and trigger the wind-down action."
    if "status" in lower or "health" in lower:
        return "System looks stable right now. If you want, ask me for incidents or sleep optimization actions."
    if "incident" in lower:
        return "Top incident: Spotify token refresh failures on a small subset of devices."
    return (
        "I can assist with bed automation, sleep guidance, device status, "
        "or admin incident summaries."
    )


def _chat_profile_prefs_for_user(profile: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    defaults = _normalize_user_profile_prefs(
        {
            "display_name": str(user.get("name", "") or user.get("email", "") or "User"),
            "timezone": "Asia/Kuwait",
            "push_enabled": True,
            "email_enabled": False,
        }
    )
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_profile_prefs")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    return _normalize_user_profile_prefs({**defaults, **scoped})


def _chat_scoped_routine_for_user(profile: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_routines")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    defaults = _normalize_user_routine({"bedtime": "22:30", "wake": "07:00", "weekends": True})
    return _normalize_user_routine({**defaults, **scoped})


def _chat_scoped_controls_for_user(profile: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_device_controls")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    defaults = _normalize_device_controls({"lights_on": False, "audio_on": False, "alarm_on": True, "light_level": 65})
    return _normalize_device_controls({**defaults, **scoped})


def _chat_user_context(
    *,
    user: dict[str, Any],
    settings_payload: dict[str, Any],
    profile_prefs: dict[str, Any],
    routine: dict[str, Any],
    controls: dict[str, Any],
    memory_line: str,
) -> str:
    lines = [
        f"user_name={str(profile_prefs.get('display_name', '') or user.get('name', '') or user.get('email', '') or 'User').strip()}",
        f"user_timezone={str(profile_prefs.get('timezone', 'Asia/Kuwait') or 'Asia/Kuwait').strip()}",
        f"response_style={str(settings_payload.get('response_style', 'balanced') or 'balanced').strip().lower()}",
        f"engagement_level={str(settings_payload.get('engagement_level', 'high') or 'high').strip().lower()}",
        f"wind_down_minutes={int(settings_payload.get('wind_down_minutes', 45) or 45)}",
        f"partner_mode_enabled={bool(settings_payload.get('partner_mode_enabled', False))}",
        f"routine_bedtime={str(routine.get('bedtime', '22:30') or '22:30').strip()}",
        f"routine_wake={str(routine.get('wake', '07:00') or '07:00').strip()}",
        f"lights_on={bool(controls.get('lights_on', False))}",
        f"audio_on={bool(controls.get('audio_on', False))}",
        f"alarm_on={bool(controls.get('alarm_on', True))}",
    ]
    memory_text = str(memory_line or "").strip()
    if memory_text:
        lines.append(memory_text)
    return "\n".join(lines)


def _default_user_timeline() -> list[dict[str, Any]]:
    return [
        {"time": "22:30", "event": "Bedtime routine scheduled", "status": "ready"},
        {"time": "23:10", "event": "Predictive drift alert", "status": "review"},
        {"time": "07:00", "event": "Adaptive wake plan", "status": "active"},
        {"time": "Anytime", "event": "Floating AI chat control", "status": "available"},
    ]


def _scene_catalog() -> dict[str, dict[str, Any]]:
    return {
        "calm_recovery": {
            "key": "calm_recovery",
            "label": "Calm Recovery",
            "summary": "Soft cyan breathing lights with gentle audio.",
            "brightness": 0.25,
            "audio_profile": "soft_pad",
        },
        "focus_momentum": {
            "key": "focus_momentum",
            "label": "Focus Momentum",
            "summary": "Steady pulse scene for focused evenings.",
            "brightness": 0.45,
            "audio_profile": "focus_loop",
        },
        "discipline_night": {
            "key": "discipline_night",
            "label": "Discipline Night",
            "summary": "Blue wave pattern with low-distraction audio.",
            "brightness": 0.35,
            "audio_profile": "night_drive",
        },
        "balanced_default": {
            "key": "balanced_default",
            "label": "Balanced Default",
            "summary": "Neutral white scene for everyday comfort.",
            "brightness": 0.40,
            "audio_profile": "ambient_neutral",
        },
    }


def _scene_gallery_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in _scene_catalog().values():
        items.append(
            {
                "scene_key": str(row.get("key", "") or ""),
                "label": str(row.get("label", "Scene") or "Scene"),
                "summary": str(row.get("summary", "") or ""),
                "preview_seconds": SCENE_PREVIEW_SECONDS,
            }
        )
    return items


def _resolve_scene_entry(scene_key: str) -> dict[str, Any] | None:
    key = str(scene_key or "").strip().lower()
    if not key:
        return None
    catalog = _scene_catalog()
    row = catalog.get(key)
    return dict(row) if isinstance(row, dict) else None


def _scene_preview_controls(current_controls: dict[str, Any], scene_entry: dict[str, Any]) -> dict[str, Any]:
    try:
        brightness = float(scene_entry.get("brightness", 0.4) or 0.4)
    except Exception:
        brightness = 0.4
    light_level = max(10, min(100, int(round(brightness * 100.0))))
    return _normalize_device_controls(
        {
            **_normalize_device_controls(current_controls),
            "lights_on": True,
            "audio_on": True,
            "light_level": light_level,
        }
    )


def _run_scene_preview(
    *,
    profile: dict[str, Any],
    key: str,
    scene_entry: dict[str, Any],
    preview_seconds: float = SCENE_PREVIEW_SECONDS,
    sleep_fn=None,
    time_fn=None,
) -> dict[str, Any]:
    sleep = sleep_fn if callable(sleep_fn) else time.sleep
    clock = time_fn if callable(time_fn) else time.monotonic
    controls_section = _get_scoped_profile_section(profile, "web_device_controls")
    previous_controls = _normalize_device_controls(controls_section.get(key, {}))
    preview_controls = _scene_preview_controls(previous_controls, scene_entry)
    controls_section[key] = preview_controls
    profile["web_device_controls"] = controls_section

    preview_started_at = _now_utc_iso()
    preview_key = str(scene_entry.get("key", "") or "")
    preview_section = _get_scoped_profile_section(profile, "web_scene_preview")
    preview_section[key] = {
        "scene_key": preview_key,
        "active": True,
        "started_at_utc": preview_started_at,
        "ended_at_utc": "",
        "duration_seconds": float(preview_seconds),
    }
    profile["web_scene_preview"] = preview_section
    _save_profile(profile)

    start_monotonic = float(clock())
    try:
        sleep(float(preview_seconds))
    finally:
        controls_section = _get_scoped_profile_section(profile, "web_device_controls")
        controls_section[key] = previous_controls
        profile["web_device_controls"] = controls_section

        preview_section = _get_scoped_profile_section(profile, "web_scene_preview")
        preview_section[key] = {
            "scene_key": preview_key,
            "active": False,
            "started_at_utc": preview_started_at,
            "ended_at_utc": _now_utc_iso(),
            "duration_seconds": float(preview_seconds),
        }
        profile["web_scene_preview"] = preview_section
        _save_profile(profile)

    elapsed_seconds = max(0.0, float(clock()) - start_monotonic)
    return {
        "scene_key": preview_key,
        "preview_controls": preview_controls,
        "restored_controls": previous_controls,
        "duration_seconds": float(preview_seconds),
        "elapsed_seconds": elapsed_seconds,
    }


def _effective_quiet_window(profile: dict[str, Any]) -> str:
    prefs = profile.get("preferences", {}) if isinstance(profile.get("preferences", {}), dict) else {}
    return str(
        prefs.get("quiet_window", settings.quiet_hours_default_window) or settings.quiet_hours_default_window or DEFAULT_QUIET_HOURS_WINDOW
    ).strip()


def _quiet_override_until_utc(profile: dict[str, Any]) -> str:
    prefs = profile.get("preferences", {}) if isinstance(profile.get("preferences", {}), dict) else {}
    return str(prefs.get("quiet_hours_override_until_utc", "") or "").strip()


def _user_local_now(profile: dict[str, Any], user: dict[str, Any], now_utc: datetime | None = None) -> datetime:
    now = now_utc if isinstance(now_utc, datetime) else utcnow()
    now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    timezone_name = str(_chat_profile_prefs_for_user(profile, user).get("timezone", "UTC") or "UTC").strip() or "UTC"
    try:
        return now.astimezone(ZoneInfo(timezone_name))
    except Exception:
        return now.astimezone(timezone.utc)


def _quiet_window_end_local(now_local: datetime, quiet_window: str) -> datetime:
    raw = str(quiet_window or "").strip()
    if "-" not in raw:
        raw = DEFAULT_QUIET_HOURS_WINDOW
    _, end_part = [part.strip() for part in raw.split("-", 1)]
    try:
        end_h, end_m = end_part.split(":", 1)
        end_hour = max(0, min(23, int(end_h)))
        end_minute = max(0, min(59, int(end_m)))
    except Exception:
        end_hour, end_minute = 7, 0

    end_local = now_local.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if now_local >= end_local:
        end_local = end_local + timedelta(days=1)
    return end_local


def _compute_quiet_hours_override_until_utc(profile: dict[str, Any], user: dict[str, Any], now_utc: datetime | None = None) -> str:
    now = now_utc if isinstance(now_utc, datetime) else utcnow()
    now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    override_limit_minutes = max(30, min(240, int(settings.quiet_hours_override_max_minutes or 120)))
    hard_limit_utc = now + timedelta(minutes=override_limit_minutes)

    quiet_window = _effective_quiet_window(profile)
    now_local = _user_local_now(profile, user, now_utc=now)
    quiet_end_utc = _quiet_window_end_local(now_local, quiet_window).astimezone(timezone.utc)
    override_until = hard_limit_utc if hard_limit_utc <= quiet_end_utc else quiet_end_utc
    return to_iso(override_until)


def _quiet_hours_status_timeline_item(profile: dict[str, Any], user: dict[str, Any], now_utc: datetime | None = None) -> dict[str, Any] | None:
    now = now_utc if isinstance(now_utc, datetime) else utcnow()
    now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    quiet_window = _effective_quiet_window(profile)
    now_local = _user_local_now(profile, user, now_utc=now)
    override_until = _quiet_override_until_utc(profile)
    override_active = is_quiet_hours_override_active(now_utc=now, override_until_utc=override_until)
    quiet_active = is_in_quiet_hours(
        now_local=now_local,
        quiet_window=quiet_window,
        quiet_mode_active=bool(
            (profile.get("preferences", {}) if isinstance(profile.get("preferences", {}), dict) else {}).get(
                "quiet_mode_active", False
            )
        ),
    )

    if override_active:
        try:
            until_dt = from_iso(override_until)
            remaining_minutes = max(0, int((ensure_utc(until_dt) - ensure_utc(now)).total_seconds() / 60.0))
        except Exception:
            remaining_minutes = 0
        return {
            "time": "Now",
            "event": f"Quiet hours override active ({remaining_minutes} min remaining)",
            "status": "override",
        }

    if quiet_active:
        return {
            "time": "Now",
            "event": f"Quiet hours active ({quiet_window}). Non-critical automations are paused.",
            "status": "quiet",
        }

    return None


def _automation_cooldown_timeline_items(now_utc: datetime | None = None) -> list[dict[str, Any]]:
    registry = AutomationRegistry(state_path=AUTOMATION_STATE_PATH)
    for automation in build_default_automations():
        registry.register(automation)

    statuses = registry.cooldown_status(now_utc=now_utc)
    rows: list[dict[str, Any]] = []
    for row in statuses:
        automation_name = str(row.get("name", "automation") or "automation").replace("_", " ")
        remaining = max(0, int(row.get("next_run_in_minutes", 0) or 0))
        if remaining > 0:
            rows.append(
                {
                    "time": f"in {remaining} min",
                    "event": f"{automation_name}: next run available in {remaining} min",
                    "status": "cooldown",
                }
            )
        else:
            rows.append(
                {
                    "time": "Anytime",
                    "event": f"{automation_name}: available now",
                    "status": "ready",
                }
            )
    return rows[:8]


def _normalize_timeline_items(items: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    source = items if isinstance(items, list) else []
    for row in source:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "time": str(row.get("time", "Anytime") or "Anytime"),
                "event": str(row.get("event", "Timeline event") or "Timeline event"),
                "status": str(row.get("status", "active") or "active"),
                "command_id": str(row.get("command_id", "") or ""),
            }
        )
    return out[:20]


def _user_action_catalog() -> dict[str, dict[str, str]]:
    return {
        "winddown": {
            "event": "Wind-down autopilot started",
            "status": "active",
            "message": "Wind-down autopilot is now active.",
        },
        "optimize_room": {
            "event": "Room optimization triggered",
            "status": "ready",
            "message": "Room optimization sequence started.",
        },
        "wake_recovery": {
            "event": "Night wake recovery mode triggered",
            "status": "review",
            "message": "Recovery mode armed for unexpected wake events.",
        },
        "reactive_lights": {
            "event": "Music-reactive lights enabled",
            "status": "active",
            "message": "Reactive lights are enabled and synced.",
        },
        "quiet_hours_override": {
            "event": "Quiet hours override enabled",
            "status": "override",
            "message": "Quiet hours override is active for a short window.",
        },
    }


def _parse_iso_timestamp(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return from_iso(raw)
    except Exception:
        return None


def _now_utc_iso() -> str:
    return to_iso(utcnow())


def _normalize_command_item(row: dict[str, Any] | None) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {}
    return {
        "id": str(data.get("id", "") or ""),
        "action": str(data.get("action", "") or ""),
        "event": str(data.get("event", "Action triggered") or "Action triggered"),
        "message": str(data.get("message", "Action accepted") or "Action accepted"),
        "status": str(data.get("status", "queued") or "queued"),
        "trace_id": str(data.get("trace_id", "") or ""),
        "created_at": str(data.get("created_at", "") or ""),
        "updated_at": str(data.get("updated_at", "") or ""),
        "completed_at": str(data.get("completed_at", "") or ""),
    }


def _safe_command_summary(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return "Command action"
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", value)
    value = re.sub(r"(?i)(token|secret|password)\s*[:=]\s*\S+", r"\1=[redacted]", value)
    value = " ".join(value.split())
    return value[:160] or "Command action"


def _build_last_command_result_from_command(command: dict[str, Any] | None) -> dict[str, Any]:
    cmd = _normalize_command_item(command)
    status = str(cmd.get("status", "queued") or "queued").strip().lower() or "queued"
    action = str(cmd.get("action", "") or "").strip().lower()
    summary = _safe_command_summary(str(cmd.get("event", "") or action.replace("_", " ")))
    timestamp_utc = str(
        cmd.get("completed_at", "")
        or cmd.get("updated_at", "")
        or cmd.get("created_at", "")
        or _now_utc_iso()
    ).strip()
    trace_id = str(cmd.get("trace_id", "") or "").strip()

    diagnostic = "Command completed." if status == "completed" else "Command in progress."
    if status == "failed":
        diagnostic = "Command failed on device."

    return {
        "command_id": str(cmd.get("id", "") or ""),
        "action": action,
        "summary": summary,
        "status": status,
        "success": bool(status == "completed"),
        "timestamp_utc": timestamp_utc,
        "trace_id": trace_id,
        "retry_action": action,
        "diagnostic": diagnostic,
    }


def _normalize_last_command_result(row: dict[str, Any] | None) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {}
    status = str(data.get("status", "queued") or "queued").strip().lower() or "queued"
    action = str(data.get("action", "") or "").strip().lower()
    return {
        "command_id": str(data.get("command_id", "") or ""),
        "action": action,
        "summary": _safe_command_summary(str(data.get("summary", "") or "Command action")),
        "status": status,
        "success": bool(data.get("success", status == "completed")),
        "timestamp_utc": str(data.get("timestamp_utc", "") or _now_utc_iso()),
        "trace_id": str(data.get("trace_id", "") or ""),
        "retry_action": str(data.get("retry_action", action) or action).strip().lower(),
        "diagnostic": _safe_command_summary(str(data.get("diagnostic", "") or "")),
    }


def _last_command_result_from_profile(profile: dict[str, Any], key: str) -> dict[str, Any]:
    section = _get_scoped_profile_section(profile, "web_last_command_result")
    row = section.get(key, {}) if key else {}
    if not key or not isinstance(row, dict) or not row:
        return {}
    return _normalize_last_command_result(row)


def _store_last_command_result(profile: dict[str, Any], key: str, result: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_last_command_result(result)
    section = _get_scoped_profile_section(profile, "web_last_command_result")
    section[key] = normalized
    profile["web_last_command_result"] = section
    return normalized


def _progress_command_state(command: dict[str, Any], now: datetime) -> tuple[dict[str, Any], bool]:
    cmd = _normalize_command_item(command)
    created_at = _parse_iso_timestamp(cmd.get("created_at", "")) or now
    elapsed = (now - created_at).total_seconds()
    previous = cmd.get("status", "queued")

    next_status = previous
    if previous not in {"completed", "failed"}:
        if elapsed >= 5:
            next_status = "completed"
        elif elapsed >= 2:
            next_status = "running"
        else:
            next_status = "queued"

    changed = next_status != previous
    cmd["status"] = next_status
    cmd["updated_at"] = _now_utc_iso()
    if next_status == "completed" and not cmd.get("completed_at"):
        cmd["completed_at"] = _now_utc_iso()
    return cmd, changed


def _progress_user_commands(profile: dict[str, Any], key: str) -> tuple[list[dict[str, Any]], bool]:
    commands_section = _get_scoped_profile_section(profile, "web_device_commands")
    raw_rows = commands_section.get(key, []) if isinstance(commands_section.get(key, []), list) else []
    now = utcnow()
    out: list[dict[str, Any]] = []
    changed_any = False
    for row in raw_rows:
        cmd, changed = _progress_command_state(row if isinstance(row, dict) else {}, now)
        out.append(cmd)
        if changed:
            changed_any = True
    return out[:60], changed_any


def _apply_command_status_to_timeline(items: list[dict[str, Any]], commands: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in items:
        next_row = dict(row)
        command_id = str(next_row.get("command_id", "") or "")
        if command_id and command_id in commands:
            next_row["status"] = str(commands[command_id].get("status", next_row.get("status", "active")))
        out.append(next_row)
    return out


def _spotify_env_config(request: Request | None = None) -> dict[str, str]:
    redirect_uri = str(settings.spotify_redirect_uri or "").strip()
    if not redirect_uri and request is not None:
        base_url = str(request.base_url).rstrip("/")
        redirect_uri = f"{base_url}/v1/mobile/spotify/callback"

    return {
        "client_id": str(settings.spotify_client_id or "").strip(),
        "client_secret": str(settings.spotify_client_secret or "").strip(),
        "redirect_uri": redirect_uri,
        "scope": str(settings.spotify_scopes or "").strip(),
    }


def _spotify_missing_config_fields(config: dict[str, str], require_redirect_uri: bool = True) -> list[str]:
    missing: list[str] = []
    if not str(config.get("client_id", "")).strip():
        missing.append("SPOTIFY_CLIENT_ID")
    if not str(config.get("client_secret", "")).strip():
        missing.append("SPOTIFY_CLIENT_SECRET")
    if require_redirect_uri and not str(config.get("redirect_uri", "")).strip():
        missing.append("SPOTIFY_REDIRECT_URI")
    return missing


def _spotify_is_configured(config: dict[str, str], require_redirect_uri: bool = True) -> bool:
    return not _spotify_missing_config_fields(config, require_redirect_uri=require_redirect_uri)


def _spotify_auth_url(config: dict[str, str], state: str) -> str:
    params = {
        "client_id": config.get("client_id", ""),
        "response_type": "code",
        "redirect_uri": config.get("redirect_uri", ""),
        "scope": config.get("scope", ""),
        "state": state,
        "show_dialog": "true",
    }
    return f"https://accounts.spotify.com/authorize?{urlencode(params)}"


def _spotify_http_post(url: str, form_data: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    encoded = urlencode({k: "" if v is None else str(v) for k, v in form_data.items()}).encode("utf-8")
    request = UrlRequest(url, data=encoded, method="POST")
    for k, v in (headers or {}).items():
        request.add_header(k, v)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise HTTPException(status_code=502, detail=f"Spotify HTTP error: {exc.code} {detail[:180]}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail="Spotify service unreachable") from exc


def _spotify_http_get(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = UrlRequest(url, method="GET")
    for k, v in (headers or {}).items():
        request.add_header(k, v)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise HTTPException(status_code=502, detail=f"Spotify HTTP error: {exc.code} {detail[:180]}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail="Spotify service unreachable") from exc


def _spotify_exchange_code(config: dict[str, str], code: str) -> dict[str, Any]:
    basic = base64.b64encode(f"{config.get('client_id', '')}:{config.get('client_secret', '')}".encode("utf-8")).decode("ascii")
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.get("redirect_uri", ""),
    }
    return _spotify_http_post(
        "https://accounts.spotify.com/api/token",
        payload,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )


def _spotify_refresh_access_token(config: dict[str, str], refresh_token: str) -> dict[str, Any]:
    basic = base64.b64encode(f"{config.get('client_id', '')}:{config.get('client_secret', '')}".encode("utf-8")).decode("ascii")
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    return _spotify_http_post(
        "https://accounts.spotify.com/api/token",
        payload,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )


def _spotify_expires_at(expires_in: Any) -> str:
    try:
        ttl = max(60, int(expires_in or 3600))
    except Exception:
        ttl = 3600
    return to_iso(utcnow() + timedelta(seconds=ttl - 30))


def _spotify_api_request(method: str, url: str, access_token: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=True).encode("utf-8")
    request = UrlRequest(url, data=body, method=method.upper())
    request.add_header("Authorization", f"Bearer {access_token}")
    if body is not None:
        request.add_header("Content-Type", "application/json")

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        if exc.code == 204:
            return {}
        raise HTTPException(status_code=502, detail=f"Spotify API error: {exc.code} {detail[:180]}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail="Spotify API unreachable") from exc


def _spotify_user_token(profile: dict[str, Any], user_key: str, user_email: str = "") -> dict[str, Any]:
    token_map = _get_scoped_profile_section(profile, "spotify_tokens")
    direct = token_map.get(user_key, {}) if isinstance(token_map.get(user_key, {}), dict) else {}
    if direct:
        return direct

    email = str(user_email or "").strip().lower()
    if not email:
        return {}

    matched_key = ""
    matched_token: dict[str, Any] = {}
    for candidate_key, row in token_map.items():
        if not isinstance(row, dict):
            continue
        row_email = str(row.get("spotify_email", "") or "").strip().lower()
        if row_email and row_email == email:
            matched_key = str(candidate_key)
            matched_token = row
            break

    if not matched_token:
        return {}

    if user_key and matched_key and matched_key != user_key:
        token_map[user_key] = matched_token
        profile["spotify_tokens"] = token_map
        _save_profile(profile)
    return matched_token


def _spotify_refresh_user_token_if_needed(profile: dict[str, Any], user_key: str, user_email: str = "") -> dict[str, Any]:
    token = _spotify_user_token(profile, user_key, user_email=user_email)
    if not token:
        return {}

    expires_at = _parse_iso_timestamp(str(token.get("expires_at", "")))
    needs_refresh = bool(expires_at and expires_at <= utcnow())
    refresh_token = str(token.get("refresh_token", "") or "")
    if not needs_refresh or not refresh_token:
        return token

    config = _spotify_env_config()
    if not _spotify_is_configured(config, require_redirect_uri=False):
        return token

    refreshed = _spotify_refresh_access_token(config, refresh_token)
    if not str(refreshed.get("access_token", "") or ""):
        return token

    token["access_token"] = str(refreshed.get("access_token", "") or token.get("access_token", ""))
    if refreshed.get("refresh_token"):
        token["refresh_token"] = str(refreshed.get("refresh_token", "") or token.get("refresh_token", ""))
    token["expires_at"] = _spotify_expires_at(refreshed.get("expires_in", 3600))
    token["scope"] = str(refreshed.get("scope", token.get("scope", "")) or token.get("scope", ""))
    token["token_type"] = str(refreshed.get("token_type", token.get("token_type", "Bearer")) or token.get("token_type", "Bearer"))
    token["updated_at"] = _now_utc_iso()

    token_map = _get_scoped_profile_section(profile, "spotify_tokens")
    token_map[user_key] = token
    profile["spotify_tokens"] = token_map
    _save_profile(profile)
    return token


def _bump(metric: str, inc: int = 1):
    TELEMETRY[metric] = int(TELEMETRY.get(metric, 0)) + int(inc)


def _event(level: str, action: str, **fields: Any):
    raw = dict(fields or {})
    trace_id = str(raw.pop("trace_id", "") or "")
    user_id = str(raw.pop("user_id", "") or "")
    emit_json_log(
        logger,
        level=level,
        event_type=action,
        trace_id=trace_id,
        user_id=user_id,
        metadata=raw,
    )


def _request_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", "")
    if str(trace_id or "").strip():
        return str(trace_id)
    fallback = f"req_{secrets.token_hex(4)}"
    request.state.trace_id = fallback
    return fallback


def _status_error_code(status_code: int) -> str:
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
    }
    return mapping.get(int(status_code), "HTTP_ERROR")


def _error_envelope(*, trace_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": str(code or "INTERNAL_ERROR"),
            "message": str(message or "Request failed"),
            "trace_id": str(trace_id),
        },
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    trace_id = _request_trace_id(request)
    message = str(exc.detail) if isinstance(exc.detail, str) and str(exc.detail).strip() else "Request failed"
    code = _status_error_code(exc.status_code)
    _event(
        "warning",
        "http_exception",
        trace_id=trace_id,
        path=request.url.path,
        status_code=exc.status_code,
        code=code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(trace_id=trace_id, code=code, message=message),
        headers={_TRACE_ID_HEADER: trace_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    trace_id = _request_trace_id(request)
    _event(
        "warning",
        "validation_exception",
        trace_id=trace_id,
        path=request.url.path,
        error_count=len(exc.errors()),
    )
    return JSONResponse(
        status_code=422,
        content=_error_envelope(trace_id=trace_id, code="VALIDATION_ERROR", message="Request validation failed"),
        headers={_TRACE_ID_HEADER: trace_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    trace_id = _request_trace_id(request)
    emit_json_log(
        logger,
        level="error",
        event_type="unhandled_exception",
        trace_id=trace_id,
        metadata={
            "path": request.url.path,
            "error_type": type(exc).__name__,
        },
    )
    return JSONResponse(
        status_code=500,
        content=_error_envelope(trace_id=trace_id, code="INTERNAL_ERROR", message="Internal server error"),
        headers={_TRACE_ID_HEADER: trace_id},
    )


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    if not normalized:
        return False
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    return "oauth" in normalized and "token" in normalized


def _redact_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, raw in value.items():
            safe_key = str(key)
            if _is_sensitive_key(safe_key):
                continue
            out[safe_key] = _redact_sensitive_payload(raw)
        return out
    if isinstance(value, list):
        return [_redact_sensitive_payload(item) for item in value]
    return value


def _stable_state_snapshot(profile: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "emotion_state": _latest_emotion_state(profile),
        "active_personality": _active_personality(profile),
        "biometric_summary": _biometric_summary(profile),
        "device_health_status": _device_health_status(profile),
    }
    return _redact_sensitive_payload(snapshot)


def _bed_capabilities(snapshot: dict[str, Any]) -> list[str]:
    device_health = snapshot.get("device_health_status", {}) if isinstance(snapshot, dict) else {}
    capabilities = ["led", "audio", "alarm", "ai_chat"]
    if bool(device_health.get("deepgram_configured", False)):
        capabilities.append("voice")
    if int(device_health.get("spotify_connected_users", 0) or 0) > 0:
        capabilities.append("spotify_playback")
    if bool(device_health.get("sensor_pressure_active", False)) or bool(device_health.get("sensor_motion_active", False)):
        capabilities.append("presence_sensing")
    return capabilities


def _bed_state_freshness_meta() -> tuple[str, bool, bool, str]:
    now = utcnow()
    devices = store.list_fleet_devices(limit=1000)
    if not isinstance(devices, list) or not devices:
        return _now_utc_iso(), True, False, "memory"

    online_statuses = {"active", "linked", "online"}
    has_online_device = False
    latest_seen: datetime | None = None
    latest_cached: datetime | None = None
    for row in devices:
        if not isinstance(row, dict):
            continue
        status_key = str(row.get("status", "") or "").strip().lower()
        if status_key in online_statuses:
            has_online_device = True

        seen_at = _parse_iso_timestamp(str(row.get("last_seen_at", "") or ""))
        if seen_at is not None and (latest_seen is None or seen_at > latest_seen):
            latest_seen = seen_at

        cached_at = _parse_iso_timestamp(str(row.get("linked_at", "") or "")) or _parse_iso_timestamp(
            str(row.get("created_at", "") or "")
        )
        if cached_at is not None and (latest_cached is None or cached_at > latest_cached):
            latest_cached = cached_at

    if latest_seen is not None:
        age_seconds = (now - latest_seen).total_seconds()
        stale = age_seconds > _DEVICE_STALE_WINDOW_SECONDS
        device_online = has_online_device and not stale
        return to_iso(latest_seen), stale, device_online, "raspberry_pi"

    if latest_cached is not None:
        return to_iso(latest_cached), True, False, "cache"

    return _now_utc_iso(), True, False, "memory"


def _generate_actor_reply(actor: dict[str, Any], message: str) -> tuple[str, bool]:
    actor_key = _user_profile_key(actor)
    if not actor_key:
        actor_key = str(actor.get("user_id", "") or actor.get("admin_id", "") or actor.get("email", "") or "session").strip().lower()

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    settings_defaults = _normalize_user_settings(
        {
            "response_style": "balanced",
            "engagement_level": "high",
            "wind_down_minutes": 45,
            "partner_mode_enabled": False,
        }
    )
    settings_payload = _profile_user_settings(profile, actor, defaults=settings_defaults)
    profile_prefs = _chat_profile_prefs_for_user(profile, actor)
    routine = _chat_scoped_routine_for_user(profile, actor)
    controls = _chat_scoped_controls_for_user(profile, actor)
    personality = _chat_personality_from_settings(settings_payload)
    emotion_state = detect_emotion_state(message)
    cognitive_load_mode = _chat_cognitive_load_mode(settings_payload)
    memory_store = _memory_store_for_user(actor_key)
    memory_line = memory_store.memory_prompt_line(message)
    user_context = _chat_user_context(
        user=actor,
        settings_payload=settings_payload,
        profile_prefs=profile_prefs,
        routine=routine,
        controls=controls,
        memory_line=memory_line,
    )

    used_fallback = False
    try:
        chat_engine = _chat_engine_for_user(actor_key)
        reply = chat_engine.generate_response(
            user_text=message,
            personality=personality,
            realtime_context="",
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
            quick_timeout_seconds=3,
            total_timeout_seconds=8,
            max_response_tokens=160,
        )
        if not str(reply or "").strip() or str(reply).startswith("(Deepgram fallback -"):
            used_fallback = True
            reply = _chat_local_fallback(message)
    except Exception as exc:
        used_fallback = True
        _event("warning", "chat_engine_failure", user_id=str(actor.get("user_id", "")), error=str(exc)[:180])
        reply = _chat_local_fallback(message)

    try:
        memory_store.record_turn(
            user_text=message,
            assistant_text=reply,
            emotion_state=emotion_state,
            personality=personality,
        )
    except Exception:
        pass

    _event(
        "info",
        "chat_reply",
        user_id=str(actor.get("user_id", "") or ""),
        personality=personality,
        emotion_state=emotion_state,
        fallback=used_fallback,
    )
    return str(reply).strip() or _chat_local_fallback(message), used_fallback


def _is_https_request(request: Request) -> bool:
    xf_proto = (request.headers.get("x-forwarded-proto", "") or "").split(",")[0].strip().lower()
    if xf_proto:
        return xf_proto == "https"
    return request.url.scheme == "https"


def _set_session_cookie(response: Response, key: str, value: str, max_age: int, request: Request):
    response.set_cookie(
        key=key,
        value=value,
        httponly=True,
        samesite="lax",
        secure=_is_https_request(request),
        path="/",
        max_age=max_age,
    )


def _clear_session_cookies(response: Response):
    response.delete_cookie("sb_user_token", path="/")
    response.delete_cookie("sb_admin_token", path="/")


def _enforce_same_origin(request: Request):
    origin = (request.headers.get("origin", "") or "").strip()
    if not origin:
        return
    host = (request.headers.get("host", "") or "").strip().lower()
    if not host:
        raise HTTPException(status_code=403, detail="Origin validation failed")
    parsed = urlparse(origin)
    origin_host = (parsed.netloc or "").strip().lower()
    if not origin_host or origin_host != host:
        _bump("same_origin_denied")
        _event("warning", "same_origin_block", path=request.url.path, origin=origin, host=host)
        raise HTTPException(status_code=403, detail="Cross-site request blocked")


def _cookie_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("sb_user_token", "")
    if not token:
        return None
    user = store.validate_user_token(token)
    return user if isinstance(user, dict) else None


def _cookie_admin(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("sb_admin_token", "")
    if not token:
        return None
    admin = store.validate_admin_token(token)
    return admin if isinstance(admin, dict) else None


def _require_user(request: Request) -> dict[str, Any]:
    user = _cookie_user(request)
    if not user:
        _bump("guard_user_denied")
        _event("warning", "user_guard_denied", path=request.url.path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User auth required")
    return user


def _require_admin(request: Request) -> dict[str, Any]:
    admin = _cookie_admin(request)
    if not admin:
        _bump("guard_admin_denied")
        _event("warning", "admin_guard_denied", path=request.url.path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin auth required")
    return admin


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/login")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(
        WEB_DIR / "login.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "service": "web_runtime"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/bed/state")
def bed_state_bridge(request: Request) -> dict[str, Any]:
    if not (_cookie_user(request) or _cookie_admin(request)):
        raise HTTPException(status_code=401, detail="Login required")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    return {
        "ok": True,
        "generated_at": _now_utc_iso(),
        "emotion_state": _latest_emotion_state(profile),
        "active_personality": _active_personality(profile),
        "last_memory_context": _last_memory_context(),
        "biometric_summary": _biometric_summary(profile),
        "device_health_status": _device_health_status(profile),
    }


@app.get("/v1/state")
def v1_state(request: Request) -> dict[str, Any]:
    if not (_cookie_user(request) or _cookie_admin(request)):
        raise HTTPException(status_code=401, detail="Login required")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    return {
        "ok": True,
        "generated_at": _now_utc_iso(),
        "snapshot": _stable_state_snapshot(profile),
    }


@app.get("/v2/bed/state", response_model=BedStateV2Response)
def v2_bed_state(request: Request) -> BedStateV2Response:
    if not (_cookie_user(request) or _cookie_admin(request)):
        raise HTTPException(status_code=401, detail="Login required")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    snapshot = _stable_state_snapshot(profile)
    updated_at, stale, device_online, source = _bed_state_freshness_meta()
    return BedStateV2Response(
        schema_version="2.0",
        capabilities=_bed_capabilities(snapshot),
        updated_at=updated_at,
        stale=bool(stale),
        device_online=bool(device_online),
        source=source,
        state=BedStateV2State(**snapshot),
    )


@app.get("/user-dashboard")
def user_dashboard(request: Request):
    if not _cookie_user(request):
        return RedirectResponse(url="/login?role=user&next=/user-dashboard", status_code=302)
    return FileResponse(
        WEB_DIR / "user-dashboard.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/admin-panel")
def admin_panel(request: Request):
    if not _cookie_admin(request):
        return RedirectResponse(url="/login?role=admin&next=/admin-panel", status_code=302)
    return FileResponse(
        WEB_DIR / "admin-panel.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/assets/{asset_name}")
def asset_file(asset_name: str) -> FileResponse:
    safe_name = Path(asset_name).name
    target = ASSETS_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(
        target,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/v1/auth/register")
def auth_register(payload: RegisterRequest, response: Response, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    name = (payload.name or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    try:
        # Public registration creates a normal app user only.
        # Admin roles (especially "owner") are not granted here and must come
        # from a separate secure provisioning/setup step.
        user = store.create_user(email=email, password=password, name=name)
    except ValueError as exc:
        _bump("auth_register_failure")
        _event("warning", "register_failed", email=email, reason=str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session = store.issue_user_token(user_id=user.get("user_id", ""))
    _set_session_cookie(response, "sb_user_token", session["access_token"], 7 * 24 * 3600, request)
    _bump("auth_register_success")
    _event("info", "register_success", user_id=user.get("user_id", ""), email=email)
    return {
        "ok": True,
        "user": {"user_id": user.get("user_id", ""), "email": user.get("email", ""), "name": user.get("name", "")},
        "expires_at": session.get("expires_at", ""),
    }


@app.post("/v1/auth/login")
def auth_login(payload: LoginRequest, response: Response, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = store.authenticate_user(payload.email, payload.password)
    if not user:
        _bump("auth_user_login_failure")
        _event("warning", "user_login_failed", email=(payload.email or "").strip().lower())
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session = store.issue_user_token(user_id=user.get("user_id", ""))
    _set_session_cookie(response, "sb_user_token", session["access_token"], 7 * 24 * 3600, request)
    _bump("auth_user_login_success")
    _event("info", "user_login_success", user_id=user.get("user_id", ""), email=user.get("email", ""))
    return {
        "ok": True,
        "user": {"user_id": user.get("user_id", ""), "email": user.get("email", ""), "name": user.get("name", "")},
        "expires_at": session.get("expires_at", ""),
    }


@app.post("/v1/admin/auth/login")
def admin_auth_login(payload: LoginRequest, response: Response, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = store.authenticate_user(payload.email, payload.password)
    if not user:
        _bump("auth_admin_login_failure")
        _event("warning", "admin_login_failed", email=(payload.email or "").strip().lower(), reason="invalid_credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Admin bootstrap flow:
    # - Login may create a missing admin record, but it is always "viewer".
    # - "owner" is never auto-created here; it must be assigned manually or
    #   via a dedicated secure setup flow.
    admin_user = store.ensure_admin_for_login(user)
    role = (admin_user.get("role") or "viewer").strip().lower()
    if role == "viewer":
        _bump("auth_admin_login_failure")
        _event("warning", "admin_login_failed", email=user.get("email", ""), reason="viewer_role_blocked")
        raise HTTPException(status_code=403, detail="Viewer admin role cannot access admin panel")

    session = store.issue_admin_token(user_id=user.get("user_id", ""), role=role)
    store.add_admin_audit_log(
        actor_user_id=user.get("user_id", ""),
        actor_role=role,
        action="admin_login",
        resource="auth",
        details={"email": user.get("email", "")},
    )
    _set_session_cookie(response, "sb_admin_token", session["access_token"], 12 * 3600, request)
    _bump("auth_admin_login_success")
    _event("info", "admin_login_success", user_id=user.get("user_id", ""), role=role)
    return {
        "ok": True,
        "admin": {"user_id": user.get("user_id", ""), "email": user.get("email", ""), "role": role},
        "expires_at": session.get("expires_at", ""),
    }


@app.post("/v1/auth/logout")
def auth_logout(response: Response, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user_token = str(request.cookies.get("sb_user_token", "") or "").strip()
    admin_token = str(request.cookies.get("sb_admin_token", "") or "").strip()
    revoked = 0
    for token in {user_token, admin_token}:
        if token and store.revoke_session(token):
            revoked += 1
    _clear_session_cookies(response)
    _event("info", "logout", revoked_sessions=revoked)
    return {"ok": True}


@app.post("/v1/auth/delete-data")
def auth_delete_data(response: Response, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _cookie_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_token = str(request.cookies.get("sb_user_token", "") or "").strip()
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    profile_removed = _purge_profile_user_data(profile, user)
    _save_profile(profile)
    deleted = store.delete_user_data(user_id=str(user.get("user_id", "")))
    if user_token:
        store.revoke_session(user_token)
    _clear_session_cookies(response)
    _event(
        "info",
        "delete_data",
        user_id=str(user.get("user_id", "")),
        db_deleted=int(deleted.get("total", 0)),
        profile_sections_removed=profile_removed,
    )
    return {"ok": True, "deleted": deleted, "profile_sections_removed": profile_removed}


@app.get("/v1/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    user = _cookie_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "ok": True,
        "user": {
            "user_id": user.get("user_id", ""),
            "email": user.get("email", ""),
            "name": user.get("name", ""),
        },
    }


@app.get("/v1/admin/auth/me")
def admin_auth_me(request: Request) -> dict[str, Any]:
    admin = _cookie_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"ok": True, "admin": admin}


@app.get("/v1/admin/observability")
def admin_observability(request: Request) -> dict[str, Any]:
    _require_admin(request)
    return {
        "ok": True,
        "telemetry": dict(TELEMETRY),
        "allowed_origins": ALLOWED_ORIGINS,
    }


@app.get("/v1/mobile/dashboard")
def mobile_dashboard(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    key = _user_profile_key(user)
    prefs = profile.get("preferences", {}) if isinstance(profile, dict) else {}
    sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}

    defaults = _normalize_user_settings(
        {
            "response_style": prefs.get("response_style", "balanced"),
            "engagement_level": prefs.get("engagement_level", "high"),
            "partner_mode_enabled": bool((sleep.get("partner_mode") or {}).get("enabled", False)),
            "wind_down_minutes": int(sleep.get("wind_down_minutes", 45) or 45),
        }
    )
    resolved = _profile_user_settings(profile, user, defaults)

    return {
        "name": profile.get("name", "Guest"),
        "location": "Kuwait",
        "response_style": resolved["response_style"],
        "engagement_level": resolved["engagement_level"],
        "partner_mode_enabled": resolved["partner_mode_enabled"],
        "wind_down_minutes": resolved["wind_down_minutes"],
        "last_command_result": _last_command_result_from_profile(profile, key),
    }


@app.get("/v1/mobile/scenes")
def mobile_scenes(request: Request) -> dict[str, Any]:
    _require_user(request)
    return {
        "ok": True,
        "preview_duration_seconds": SCENE_PREVIEW_SECONDS,
        "items": _scene_gallery_items(),
    }


@app.get("/v1/mobile/settings")
def mobile_settings(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    prefs = profile.get("preferences", {}) if isinstance(profile, dict) else {}
    sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
    defaults = _normalize_user_settings(
        {
            "response_style": prefs.get("response_style", "balanced"),
            "engagement_level": prefs.get("engagement_level", "high"),
            "partner_mode_enabled": bool((sleep.get("partner_mode") or {}).get("enabled", False)),
            "wind_down_minutes": int(sleep.get("wind_down_minutes", 45) or 45),
        }
    )
    resolved = _profile_user_settings(profile, user, defaults)
    return {"ok": True, "settings": resolved}


@app.post("/v1/mobile/settings")
def upsert_mobile_settings(payload: UserSettingsRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    settings_map = profile.get("web_settings", {})
    if not isinstance(settings_map, dict):
        settings_map = {}

    key = str(user.get("user_id", "")).strip() or str(user.get("email", "")).strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user settings key")

    normalized = _normalize_user_settings(payload.model_dump())
    settings_map[key] = normalized
    profile["web_settings"] = settings_map
    _save_profile(profile)
    _event("info", "user_settings_saved", user_id=str(user.get("user_id", "")), key=key)
    return {"ok": True, "settings": normalized}


@app.get("/v1/mobile/routine")
def mobile_routine(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    defaults = _normalize_user_routine({"bedtime": "22:30", "wake": "07:00", "weekends": True})
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_routines")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    return {"ok": True, "routine": _normalize_user_routine({**defaults, **scoped})}


@app.post("/v1/mobile/routine")
def upsert_mobile_routine(payload: UserRoutineRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user routine key")

    section = _get_scoped_profile_section(profile, "web_routines")
    normalized = _normalize_user_routine(payload.model_dump())
    section[key] = normalized
    profile["web_routines"] = section
    _save_profile(profile)
    _event("info", "user_routine_saved", user_id=str(user.get("user_id", "")), key=key)
    return {"ok": True, "routine": normalized}


@app.get("/v1/mobile/profile")
def mobile_profile(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    defaults = _normalize_user_profile_prefs({
        "display_name": str(user.get("name", "") or user.get("email", "") or "User"),
        "timezone": "Asia/Kuwait",
        "push_enabled": True,
        "email_enabled": False,
    })
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_profile_prefs")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    return {"ok": True, "profile": _normalize_user_profile_prefs({**defaults, **scoped})}


@app.post("/v1/mobile/profile")
def upsert_mobile_profile(payload: UserProfilePrefsRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user profile key")

    section = _get_scoped_profile_section(profile, "web_profile_prefs")
    normalized = _normalize_user_profile_prefs(payload.model_dump())
    section[key] = normalized
    profile["web_profile_prefs"] = section
    prefs = profile.get("preferences", {}) if isinstance(profile.get("preferences", {}), dict) else {}
    prefs["timezone"] = str(normalized.get("timezone", "UTC") or "UTC").strip() or "UTC"
    profile["preferences"] = prefs
    _save_profile(profile)
    _event("info", "user_profile_saved", user_id=str(user.get("user_id", "")), key=key)
    return {"ok": True, "profile": normalized}


@app.get("/v1/mobile/device-controls")
def mobile_device_controls(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    defaults = _normalize_device_controls({
        "lights_on": False,
        "audio_on": False,
        "alarm_on": True,
        "light_level": 65,
    })
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_device_controls")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    return {"ok": True, "controls": _normalize_device_controls({**defaults, **scoped})}


@app.get("/v1/mobile/spotify/connect")
def mobile_spotify_connect(request: Request):
    safe_error_redirect = "/user-dashboard?spotify=error"
    try:
        user = _require_user(request)
    except HTTPException:
        return RedirectResponse(url="/login?role=user&next=/user-dashboard", status_code=302)

    config = _spotify_env_config(request)
    if not _spotify_is_configured(config, require_redirect_uri=True):
        missing = ",".join(_spotify_missing_config_fields(config, require_redirect_uri=True))
        return RedirectResponse(url=f"{safe_error_redirect}&reason=oauth_not_configured&missing={missing}", status_code=302)

    key = _user_profile_key(user)
    if not key:
        return RedirectResponse(url=f"{safe_error_redirect}&reason=missing_user_key", status_code=302)

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    states = _get_scoped_profile_section(profile, "spotify_oauth_state")
    state = secrets.token_urlsafe(24)
    states[key] = {
        "state": state,
        "created_at": _now_utc_iso(),
    }
    profile["spotify_oauth_state"] = states
    _save_profile(profile)

    return RedirectResponse(url=_spotify_auth_url(config, state), status_code=302)


@app.get("/v1/mobile/spotify/callback")
def mobile_spotify_callback(request: Request, code: str = "", state: str = ""):
    safe_error_redirect = "/user-dashboard?spotify=error"
    if not code or not state:
        return RedirectResponse(url=f"{safe_error_redirect}&reason=missing_code_or_state", status_code=302)

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    states = _get_scoped_profile_section(profile, "spotify_oauth_state")
    matched_key = ""
    for candidate_key, row in states.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("state", "")).strip() == state.strip():
            matched_key = str(candidate_key)
            break

    if not matched_key:
        return RedirectResponse(url=f"{safe_error_redirect}&reason=invalid_state", status_code=302)

    config = _spotify_env_config(request)
    if not _spotify_is_configured(config, require_redirect_uri=True):
        missing = ",".join(_spotify_missing_config_fields(config, require_redirect_uri=True))
        return RedirectResponse(url=f"{safe_error_redirect}&reason=oauth_not_configured&missing={missing}", status_code=302)

    try:
        token_payload = _spotify_exchange_code(config, code)
        access_token = str(token_payload.get("access_token", "") or "")
        if not access_token:
            return RedirectResponse(url=f"{safe_error_redirect}&reason=token_exchange_failed", status_code=302)

        spotify_profile = _spotify_http_get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except HTTPException as exc:
        detail = str(getattr(exc, "detail", "") or "").strip()
        redirect_qs = urlencode(
            {
                "spotify": "error",
                "reason": "exchange_failed",
                "detail": detail[:180],
            }
        )
        return RedirectResponse(url=f"/user-dashboard?{redirect_qs}", status_code=302)

    token_map = _get_scoped_profile_section(profile, "spotify_tokens")
    token_map[matched_key] = {
        "access_token": access_token,
        "refresh_token": str(token_payload.get("refresh_token", "") or ""),
        "expires_at": _spotify_expires_at(token_payload.get("expires_in", 3600)),
        "scope": str(token_payload.get("scope", "") or ""),
        "token_type": str(token_payload.get("token_type", "Bearer") or "Bearer"),
        "spotify_user_id": str(spotify_profile.get("id", "") or ""),
        "spotify_email": str(spotify_profile.get("email", "") or ""),
        "updated_at": _now_utc_iso(),
    }
    profile["spotify_tokens"] = token_map

    states.pop(matched_key, None)
    profile["spotify_oauth_state"] = states
    _save_profile(profile)
    return RedirectResponse(url="/user-dashboard?spotify=connected", status_code=302)


@app.get("/v1/mobile/spotify/status")
def mobile_spotify_status(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user Spotify key")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    user_email = str(user.get("email", "") or "").strip().lower()
    token = _spotify_refresh_user_token_if_needed(profile, key, user_email=user_email)
    if not token:
        return {"ok": True, "connected": False}

    return {
        "ok": True,
        "connected": True,
        "spotify_user_id": str(token.get("spotify_user_id", "") or ""),
        "spotify_email": str(token.get("spotify_email", "") or ""),
        "expires_at": str(token.get("expires_at", "") or ""),
        "scope": str(token.get("scope", "") or ""),
    }


@app.post("/v1/mobile/spotify/disconnect")
def mobile_spotify_disconnect(request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user Spotify key")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    token_map = _get_scoped_profile_section(profile, "spotify_tokens")
    token_map.pop(key, None)
    profile["spotify_tokens"] = token_map
    _save_profile(profile)
    return {"ok": True}


@app.get("/v1/mobile/spotify/playback-status")
def mobile_spotify_playback_status(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user Spotify key")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    user_email = str(user.get("email", "") or "").strip().lower()
    token = _spotify_refresh_user_token_if_needed(profile, key, user_email=user_email)
    access_token = str(token.get("access_token", "") or "")
    if not access_token:
        return {"ok": True, "connected": False}

    payload = _spotify_api_request("GET", "https://api.spotify.com/v1/me/player", access_token)
    item = payload.get("item", {}) if isinstance(payload, dict) else {}
    device = payload.get("device", {}) if isinstance(payload, dict) else {}
    return {
        "ok": True,
        "connected": True,
        "is_playing": bool(payload.get("is_playing", False)),
        "track_name": str(item.get("name", "") or ""),
        "artist": ", ".join([str(a.get("name", "") or "") for a in (item.get("artists", []) or []) if isinstance(a, dict)]),
        "device_name": str(device.get("name", "") or ""),
    }


@app.post("/v1/mobile/spotify/playback")
def mobile_spotify_playback(payload: SpotifyPlaybackRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user Spotify key")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    user_email = str(user.get("email", "") or "").strip().lower()
    token = _spotify_refresh_user_token_if_needed(profile, key, user_email=user_email)
    access_token = str(token.get("access_token", "") or "")
    if not access_token:
        raise HTTPException(status_code=400, detail="Spotify is not connected")

    action = str(payload.action or "").strip().lower()
    device_id = str(payload.device_id or "").strip() or str(settings.spotify_device_id or "").strip()
    query = f"?device_id={device_id}" if device_id else ""

    try:
        if action in {"play", "resume"}:
            body = None
            playlist_uri = str(payload.playlist_uri or "").strip()
            if playlist_uri:
                body = {"context_uri": playlist_uri}
            _spotify_api_request("PUT", f"https://api.spotify.com/v1/me/player/play{query}", access_token, body)
            return {"ok": True, "message": "Playback started."}

        if action == "pause":
            _spotify_api_request("PUT", f"https://api.spotify.com/v1/me/player/pause{query}", access_token)
            return {"ok": True, "message": "Playback paused."}

        if action == "next":
            _spotify_api_request("POST", f"https://api.spotify.com/v1/me/player/next{query}", access_token)
            return {"ok": True, "message": "Skipped to next track."}

        if action == "previous":
            _spotify_api_request("POST", f"https://api.spotify.com/v1/me/player/previous{query}", access_token)
            return {"ok": True, "message": "Moved to previous track."}

        if action == "set_volume":
            volume = max(0, min(100, int(payload.volume_percent or 50)))
            sep = "&" if query else "?"
            _spotify_api_request(
                "PUT",
                f"https://api.spotify.com/v1/me/player/volume{query}{sep}volume_percent={volume}",
                access_token,
            )
            return {"ok": True, "message": f"Volume set to {volume}%."}
    except HTTPException as exc:
        detail = str(getattr(exc, "detail", "") or "").strip()
        lower = detail.lower()
        if "premium" in lower or " 403" in lower or "error: 403" in lower:
            raise HTTPException(status_code=400, detail="Spotify Premium is required for playback controls on this account.") from exc
        if "no active device" in lower or " 404" in lower or "error: 404" in lower:
            raise HTTPException(status_code=400, detail="No active Spotify device found. Open Spotify on your phone and start any song, then retry.") from exc
        raise

    raise HTTPException(status_code=400, detail="Unsupported Spotify playback action")


@app.post("/v1/mobile/device-controls")
def upsert_mobile_device_controls(payload: UserDeviceControlRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user device control key")

    section = _get_scoped_profile_section(profile, "web_device_controls")
    normalized = _normalize_device_controls(payload.model_dump())
    section[key] = normalized
    profile["web_device_controls"] = section
    _save_profile(profile)
    _event("info", "user_device_controls_saved", user_id=str(user.get("user_id", "")), key=key)
    return {"ok": True, "controls": normalized}


@app.get("/v1/mobile/timeline")
def mobile_timeline(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    key = _user_profile_key(user)
    if not isinstance(profile, dict):
        profile = {}
    section = _get_scoped_profile_section(profile, "web_timeline")
    scoped = section.get(key, []) if key else []
    items = _normalize_timeline_items(scoped if isinstance(scoped, list) else [])

    if key:
        commands, changed = _progress_user_commands(profile, key)
        command_map = {str(c.get("id", "")): c for c in commands if str(c.get("id", ""))}
        items = _apply_command_status_to_timeline(items, command_map)
        if changed and commands:
            _store_last_command_result(profile, key, _build_last_command_result_from_command(commands[0]))
        if changed:
            cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
            cmd_section[key] = commands
            profile["web_device_commands"] = cmd_section
            _save_profile(profile)

    now = utcnow()
    quiet_row = _quiet_hours_status_timeline_item(profile, user, now_utc=now)
    cooldown_rows = _automation_cooldown_timeline_items(now_utc=now)
    if cooldown_rows:
        items = cooldown_rows + items
    if quiet_row:
        items = [quiet_row] + items

    if not items:
        items = _default_user_timeline()
    return {"ok": True, "items": _normalize_timeline_items(items)[:20]}


@app.post("/v1/mobile/user-actions")
def mobile_user_actions(payload: UserActionRequest, request: Request) -> dict[str, Any]:
    return create_mobile_device_command(UserDeviceCommandRequest(action=payload.action), request)


@app.post("/v1/mobile/scenes/preview")
def mobile_scene_preview(payload: SceneSelectionRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user scene key")

    scene_entry = _resolve_scene_entry(payload.scene_key)
    if not scene_entry:
        raise HTTPException(status_code=400, detail="Unsupported scene key")

    trace_id = _request_trace_id(request)
    scene_key = str(scene_entry.get("key", "") or "")
    _event(
        "info",
        "scene_preview_started",
        trace_id=trace_id,
        user_id=str(user.get("user_id", "")),
        scene_key=scene_key,
        preview_seconds=SCENE_PREVIEW_SECONDS,
        premium_quota_charged=False,
    )

    try:
        preview_result = _run_scene_preview(
            profile=profile,
            key=key,
            scene_entry=scene_entry,
            preview_seconds=SCENE_PREVIEW_SECONDS,
        )
    except Exception as exc:
        _event(
            "error",
            "scene_preview_failed",
            trace_id=trace_id,
            user_id=str(user.get("user_id", "")),
            scene_key=scene_key,
            error_type=type(exc).__name__,
        )
        raise

    _event(
        "info",
        "scene_preview_completed",
        trace_id=trace_id,
        user_id=str(user.get("user_id", "")),
        scene_key=scene_key,
        preview_seconds=SCENE_PREVIEW_SECONDS,
        elapsed_ms=int(round(float(preview_result.get("elapsed_seconds", 0.0)) * 1000.0)),
        premium_quota_charged=False,
    )
    return {
        "ok": True,
        "scene_key": scene_key,
        "scene_label": str(scene_entry.get("label", "Scene") or "Scene"),
        "preview_duration_seconds": SCENE_PREVIEW_SECONDS,
        "elapsed_seconds": round(float(preview_result.get("elapsed_seconds", 0.0)), 3),
        "post_preview_prompt": "Like it? Save for Tonight",
        "message": "Preview complete. Like it? Save for Tonight",
        "premium_quota_exempt": True,
        "trace_id": trace_id,
    }


@app.post("/v1/mobile/scenes/save-tonight")
def mobile_scene_save_tonight(payload: SceneSelectionRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user scene key")

    scene_entry = _resolve_scene_entry(payload.scene_key)
    if not scene_entry:
        raise HTTPException(status_code=400, detail="Unsupported scene key")

    scene_key = str(scene_entry.get("key", "") or "")
    scene_label = str(scene_entry.get("label", "Scene") or "Scene")

    controls_section = _get_scoped_profile_section(profile, "web_device_controls")
    current_controls = _normalize_device_controls(controls_section.get(key, {}))
    controls_section[key] = _scene_preview_controls(current_controls, scene_entry)
    profile["web_device_controls"] = controls_section

    env = profile.get("environment", {}) if isinstance(profile.get("environment", {}), dict) else {}
    env["last_scene_key"] = scene_key
    env["last_scene_applied_at"] = _now_utc_iso()
    env["saved_tonight_scene_key"] = scene_key
    profile["environment"] = env

    timeline_section = _get_scoped_profile_section(profile, "web_timeline")
    rows = timeline_section.get(key, []) if isinstance(timeline_section.get(key, []), list) else []
    rows = _normalize_timeline_items(rows)
    rows.insert(
        0,
        {
            "time": "Now",
            "event": f"Scene saved for tonight: {scene_label}",
            "status": "ready",
            "command_id": "",
        },
    )
    timeline_section[key] = rows[:20]
    profile["web_timeline"] = timeline_section

    _save_profile(profile)

    trace_id = _request_trace_id(request)
    _event(
        "info",
        "scene_saved_for_tonight",
        trace_id=trace_id,
        user_id=str(user.get("user_id", "")),
        scene_key=scene_key,
        premium_quota_charged=False,
    )
    return {
        "ok": True,
        "scene_key": scene_key,
        "scene_label": scene_label,
        "saved_for_tonight": True,
        "message": "Scene saved for tonight.",
        "premium_quota_exempt": True,
        "trace_id": trace_id,
    }


@app.post("/v1/mobile/device-commands")
def create_mobile_device_command(payload: UserDeviceCommandRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    action_key = str(payload.action or "").strip().lower()
    catalog = _user_action_catalog()
    entry = catalog.get(action_key)
    if not entry:
        raise HTTPException(status_code=400, detail="Unsupported user action")

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user action key")
    request_trace_id = _request_trace_id(request)

    if action_key == "quiet_hours_override":
        prefs = profile.get("preferences", {}) if isinstance(profile.get("preferences", {}), dict) else {}
        profile["preferences"] = prefs
        now_iso = _now_utc_iso()
        override_until_utc = _compute_quiet_hours_override_until_utc(profile, user, now_utc=utcnow())
        prefs["quiet_hours_override_until_utc"] = override_until_utc

        section = _get_scoped_profile_section(profile, "web_timeline")
        rows = section.get(key, []) if isinstance(section.get(key, []), list) else []
        rows = _normalize_timeline_items(rows)
        rows.insert(
            0,
            {
                "time": "Now",
                "event": "Quiet hours override enabled",
                "status": "override",
                "command_id": "",
            },
        )
        section[key] = rows[:20]
        profile["web_timeline"] = section
        last_command_result = _store_last_command_result(
            profile,
            key,
            _build_last_command_result_from_command(
                {
                    "id": "",
                    "action": action_key,
                    "event": str(entry.get("event", "Action triggered")),
                    "status": "completed",
                    "trace_id": request_trace_id,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "completed_at": now_iso,
                }
            ),
        )
        _save_profile(profile)

        _event(
            "info",
            "quiet_hours_override_enabled",
            trace_id=request_trace_id,
            user_id=str(user.get("user_id", "")),
            override_until_utc=override_until_utc,
        )
        return {
            "ok": True,
            "action": action_key,
            "command_id": "",
            "message": f"Quiet hours override active until {override_until_utc}.",
            "override_until_utc": override_until_utc,
            "last_command_result": last_command_result,
            "timeline": section[key],
        }

    command_id = f"cmd_{int(datetime.now().timestamp() * 1000)}"
    now_iso = _now_utc_iso()
    command = _normalize_command_item(
        {
            "id": command_id,
            "action": action_key,
            "event": str(entry.get("event", "Action triggered")),
            "message": str(entry.get("message", "Action accepted")),
            "status": "queued",
            "trace_id": request_trace_id,
            "created_at": now_iso,
            "updated_at": now_iso,
            "completed_at": "",
        }
    )

    cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
    cmd_rows = cmd_section.get(key, []) if isinstance(cmd_section.get(key, []), list) else []
    normalized_cmd_rows = [_normalize_command_item(r if isinstance(r, dict) else {}) for r in cmd_rows]
    normalized_cmd_rows.insert(0, command)
    cmd_section[key] = normalized_cmd_rows[:60]
    profile["web_device_commands"] = cmd_section

    section = _get_scoped_profile_section(profile, "web_timeline")
    rows = section.get(key, []) if isinstance(section.get(key, []), list) else []
    rows = _normalize_timeline_items(rows)
    rows.insert(
        0,
        {
            "time": datetime.now().strftime("%H:%M"),
            "event": str(entry.get("event", "Action triggered")),
            "status": "queued",
            "command_id": command_id,
        },
    )
    section[key] = rows[:20]
    profile["web_timeline"] = section
    last_command_result = _store_last_command_result(
        profile,
        key,
        _build_last_command_result_from_command(command),
    )
    _save_profile(profile)

    _event(
        "info",
        "user_action",
        trace_id=request_trace_id,
        user_id=str(user.get("user_id", "")),
        command_action=action_key,
        command_id=command_id,
    )
    return {
        "ok": True,
        "action": action_key,
        "command_id": command_id,
        "command": command,
        "last_command_result": last_command_result,
        "message": str(entry.get("message", "Action completed.")),
        "timeline": section[key],
    }


@app.get("/v1/mobile/device-commands/{command_id}")
def mobile_device_command_status(command_id: str, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user action key")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    commands, changed = _progress_user_commands(profile, key)
    last_command_result = _last_command_result_from_profile(profile, key)
    if commands:
        latest_result = _build_last_command_result_from_command(commands[0])
        last_command_result = latest_result
        if changed:
            _store_last_command_result(profile, key, latest_result)
    cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
    cmd_section[key] = commands
    profile["web_device_commands"] = cmd_section

    section = _get_scoped_profile_section(profile, "web_timeline")
    rows = section.get(key, []) if isinstance(section.get(key, []), list) else []
    timeline_rows = _normalize_timeline_items(rows)
    command_map = {str(c.get("id", "")): c for c in commands if str(c.get("id", ""))}
    timeline_rows = _apply_command_status_to_timeline(timeline_rows, command_map)
    section[key] = timeline_rows[:20]
    profile["web_timeline"] = section

    if changed:
        _save_profile(profile)

    target = None
    for cmd in commands:
        if str(cmd.get("id", "")) == str(command_id):
            target = cmd
            break
    if not target:
        raise HTTPException(status_code=404, detail="Command not found")

    return {"ok": True, "command": target, "last_command_result": last_command_result}


@app.get("/v1/mobile/devices")
def mobile_devices(request: Request) -> dict[str, Any]:
    _require_user(request)
    profile = _safe_profile()
    hardware = profile.get("hardware", {}) if isinstance(profile, dict) else {}

    return {
        "firmware_version": "1.0.0",
        "device_status": "online",
        "user_strip_pin": hardware.get("user_strip_pin", 18),
        "state_strip_pin": hardware.get("state_strip_pin", 13),
        "user_strip_led_count": hardware.get("user_strip_led_count", 120),
        "state_strip_led_count": hardware.get("state_strip_led_count", 60),
    }


@app.get("/v1/admin/overview")
def admin_overview(request: Request) -> dict[str, Any]:
    _require_admin(request)
    return {
        "registered_users": 1248,
        "active_beds": 876,
        "open_incidents": 4,
        "ai_quota_health_percent": 97,
    }


@app.get("/v1/admin/incidents")
def admin_incidents(request: Request) -> dict[str, Any]:
    _require_admin(request)
    items = store.list_incidents(limit=20)
    if items:
        normalized = []
        for item in items:
            normalized.append(
                {
                    "id": item.get("incident_id", ""),
                    "type": item.get("title", item.get("type", "incident")),
                    "device": item.get("device_id", "n/a"),
                    "status": item.get("status", "open"),
                }
            )
        return {"items": normalized}

    return {
        "items": [
            {
                "id": "INC-1902",
                "type": "Spotify token refresh fail",
                "device": "bed_kw_022",
                "status": "investigating",
            },
            {
                "id": "INC-1901",
                "type": "TTS timeout burst",
                "device": "bed_kw_017",
                "status": "monitoring",
            },
            {
                "id": "INC-1899",
                "type": "Entitlement mismatch",
                "device": "bed_kw_009",
                "status": "escalated",
            },
        ]
    }


@app.get("/v1/admin/runtime")
def admin_runtime(request: Request) -> dict[str, Any]:
    _require_admin(request)
    payment_events = store.db.get("payment_events", []) if isinstance(store.db, dict) else []
    failed_events = 0
    for row in payment_events:
        typ = str((row or {}).get("event_type", "")).strip().lower()
        if typ in ("payment.failed", "subscription.past_due"):
            failed_events += 1

    total_events = max(1, len(payment_events))
    webhook_success_rate = round(max(88.0, 100.0 - ((failed_events / total_events) * 100.0)), 1)

    return {
        "guard_denied": int(TELEMETRY.get("guard_admin_denied", 0)) + int(TELEMETRY.get("guard_user_denied", 0)),
        "chat_requests": int(TELEMETRY.get("chat_requests", 0)),
        "same_origin_denied": int(TELEMETRY.get("same_origin_denied", 0)),
        "tier_mix": "Free 39% | Standard 44% | Pro 17%",
        "grace_users": 23,
        "webhook_success_rate": webhook_success_rate,
    }


@app.get("/v1/admin/fleet")
def admin_fleet(request: Request) -> dict[str, Any]:
    _require_admin(request)
    devices = store.list_fleet_devices(limit=1000)
    total = len(devices)
    active = 0
    replaced = 0
    stale = 0
    for item in devices:
        state = str(item.get("status", "")).strip().lower()
        if state in ("active", "linked", "online"):
            active += 1
        elif state in ("replaced", "retired"):
            replaced += 1
        else:
            stale += 1

    if total == 0:
        return {
            "items": [
                {"label": "Fleet enrollment", "value": "0 devices", "status": "warn", "note": "No devices synced yet"},
                {"label": "Activation coverage", "value": "0%", "status": "warn", "note": "Awaiting first links"},
                {"label": "Replaced devices", "value": "0", "status": "good", "note": "No swaps recorded"},
                {"label": "Stale devices", "value": "0", "status": "good", "note": "No stale records"},
            ]
        }

    coverage = round((active / max(1, total)) * 100)
    return {
        "items": [
            {
                "label": "Fleet enrollment",
                "value": f"{total} devices",
                "status": "good" if total >= 10 else "warn",
                "note": "Registered in fleet directory",
            },
            {
                "label": "Activation coverage",
                "value": f"{coverage}%",
                "status": "good" if coverage >= 70 else "warn",
                "note": f"{active} active or online devices",
            },
            {
                "label": "Replaced devices",
                "value": str(replaced),
                "status": "warn" if replaced > 0 else "good",
                "note": "Hardware lifecycle swaps",
            },
            {
                "label": "Stale devices",
                "value": str(stale),
                "status": "warn" if stale > 0 else "good",
                "note": "Unknown/offline status records",
            },
        ]
    }


@app.get("/v1/admin/audit")
def admin_audit(request: Request) -> dict[str, Any]:
    _require_admin(request)
    rows = store.list_admin_audit_logs(limit=10)
    if not rows:
        return {
            "items": [
                {
                    "actor": "owner@danahabuhalifa",
                    "action": "admin_login",
                    "resource": "auth",
                    "time": "just now",
                }
            ]
        }

    items = []
    for row in rows:
        actor_id = str(row.get("actor_user_id", "")).strip()
        actor_user = store.get_user(actor_id) if actor_id else None
        actor_email = str((actor_user or {}).get("email", "")).strip().lower()
        actor = actor_email or actor_id or "admin"
        items.append(
            {
                "actor": actor,
                "action": str(row.get("action", "-") or "-"),
                "resource": str(row.get("resource", "-") or "-"),
                "time": str(row.get("created_at", "") or "recent"),
            }
        )
    return {"items": items}


@app.get("/v1/admin/user-dashboard")
def admin_user_dashboard(request: Request) -> dict[str, Any]:
    _require_admin(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    settings_map = profile.get("web_settings", {}) if isinstance(profile.get("web_settings", {}), dict) else {}
    routines_map = profile.get("web_routines", {}) if isinstance(profile.get("web_routines", {}), dict) else {}
    prefs_map = profile.get("web_profile_prefs", {}) if isinstance(profile.get("web_profile_prefs", {}), dict) else {}
    controls_map = profile.get("web_device_controls", {}) if isinstance(profile.get("web_device_controls", {}), dict) else {}
    timeline_map = profile.get("web_timeline", {}) if isinstance(profile.get("web_timeline", {}), dict) else {}
    commands_map = profile.get("web_device_commands", {}) if isinstance(profile.get("web_device_commands", {}), dict) else {}

    command_rows: list[dict[str, Any]] = []
    pending_commands = 0
    running_commands = 0
    completed_commands = 0

    for user_key, rows in commands_map.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            cmd = _normalize_command_item(row if isinstance(row, dict) else {})
            status_value = str(cmd.get("status", "queued")).strip().lower()
            if status_value == "queued":
                pending_commands += 1
            elif status_value == "running":
                running_commands += 1
            elif status_value == "completed":
                completed_commands += 1
            command_rows.append(
                {
                    "user": str(user_key),
                    "command_id": str(cmd.get("id", "") or "-"),
                    "action": str(cmd.get("action", "") or "-"),
                    "status": status_value or "queued",
                    "updated_at": str(cmd.get("updated_at", "") or "recent"),
                }
            )

    command_rows.sort(
        key=lambda x: _parse_iso_timestamp(str(x.get("updated_at", ""))) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    timeline_rows: list[dict[str, Any]] = []
    for user_key, rows in timeline_map.items():
        if not isinstance(rows, list):
            continue
        normalized = _normalize_timeline_items(rows)
        for row in normalized[:5]:
            timeline_rows.append(
                {
                    "user": str(user_key),
                    "time": str(row.get("time", "Anytime") or "Anytime"),
                    "event": str(row.get("event", "Timeline event") or "Timeline event"),
                    "status": str(row.get("status", "active") or "active"),
                }
            )

    return {
        "summary": {
            "users_with_settings": len(settings_map),
            "users_with_routines": len(routines_map),
            "users_with_profile_prefs": len(prefs_map),
            "users_with_device_controls": len(controls_map),
            "pending_commands": pending_commands,
            "running_commands": running_commands,
            "completed_commands": completed_commands,
            "timeline_users": len(timeline_map),
        },
        "commands": command_rows[:12],
        "timeline": timeline_rows[:12],
    }


@app.post("/v1/admin/actions")
def admin_actions(payload: AdminActionRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    admin = _require_admin(request)
    action_key = str(payload.action or "").strip().lower()

    catalog = {
        "publish_firmware": {
            "title": "Firmware release queued",
            "message": "Firmware release draft queued for staged rollout (5%, then 25%, then 100%).",
            "resource": "firmware",
        },
        "device_timeline": {
            "title": "Device timeline prepared",
            "message": "Recent fleet timeline compiled. Open Fleet Devices for per-device history.",
            "resource": "fleet",
        },
        "open_billing": {
            "title": "Billing events opened",
            "message": "Filtered billing feed for failed/past-due events is ready for review.",
            "resource": "billing",
        },
        "export_report": {
            "title": "Monthly report export started",
            "message": "CSV export request accepted. Your monthly operations report is being generated.",
            "resource": "reports",
        },
    }

    config = catalog.get(action_key)
    if not config:
        raise HTTPException(status_code=400, detail="Unsupported admin action")

    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=str(admin.get("role", "viewer")),
        action=action_key,
        resource=str(config.get("resource", "admin")),
        details={"source": "admin_panel"},
    )
    _event("info", "admin_action", action=action_key, actor=str(admin.get("user_id", "")))
    return {
        "ok": True,
        "action": action_key,
        "title": str(config.get("title", "Action completed")),
        "message": str(config.get("message", "Action completed.")),
    }


@app.post("/v1/admin/voice/circuit-breaker/reset")
def admin_voice_circuit_breaker_reset(request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    admin = _require_admin(request)

    source = f"admin_panel:{str(admin.get('user_id', '') or 'unknown')}"
    payload = write_voice_circuit_reset_signal(settings.voice_circuit_reset_signal_path, source=source)

    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=str(admin.get("role", "viewer")),
        action="voice_circuit_breaker_reset",
        resource="voice_pipeline",
        details={"source": "admin_panel"},
    )
    _event("info", "voice_circuit_breaker_reset", actor=str(admin.get("user_id", "")))
    return {
        "ok": True,
        "requested_at": str(payload.get("requested_at", "")),
        "message": "Voice circuit-breaker reset signal queued.",
    }


@app.post("/v1/ai/chat")
def ai_chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _cookie_user(request)
    admin = _cookie_admin(request)
    actor = user or admin
    if not actor:
        _bump("chat_denied")
        _event("warning", "chat_denied_unauthenticated")
        raise HTTPException(status_code=401, detail="Login required")
    _bump("chat_requests")

    message = (payload.message or "").strip()
    if not message:
        return {"reply": "Please type a message so I can help."}

    reply, _ = _generate_actor_reply(actor, message)
    return {"reply": reply}


@app.post("/v1/command")
def v1_command(payload: CommandRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _cookie_user(request)
    admin = _cookie_admin(request)
    actor = user or admin
    if not actor:
        raise HTTPException(status_code=401, detail="Login required")

    text = str(payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    source = str(payload.source or "web").strip().lower() or "web"
    if source not in {"web", "mobile", "api"}:
        source = "web"

    reply_text, used_fallback = _generate_actor_reply(actor, text)
    return {
        "reply_text": reply_text,
        "effects_summary": {
            "source": source,
            "executed_actions": [],
            "assistant_fallback_used": bool(used_fallback),
            "note": "No direct device action executed; assistant generated a guidance reply.",
        },
    }
