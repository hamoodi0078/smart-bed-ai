from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
import json
import logging
import math
import os
import binascii
import re
import secrets
import hmac
import hashlib
import threading
import time
import uuid
from http import HTTPStatus
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
import base64
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from core.metrics import REQUEST_COUNT, REQUEST_LATENCY, ERROR_COUNT
from pydantic import BaseModel, Field

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
from ai.long_term_memory import DBLongTermMemoryStore, LongTermMemoryStore
from ai.sleep_intelligence import SleepIntelligenceEngine
from ai.voice_circuit_breaker import write_voice_circuit_reset_signal
from commands.undo_manager import UndoManager
from config import LONG_TERM_MEMORY_PATH, RUNTIME_DATA_DIR, USER_PROFILE_PATH, settings
from core.errors import (
    APIError,
    BedError,
    DEVICE_OFFLINE,
    INVALID_SCENE_CONFIG,
    INTERNAL_ERROR,
    NOTHING_TO_UNDO,
    RATE_LIMITED,
    TRIAL_ALREADY_USED,
    UNAUTHORIZED,
    VALIDATION_ERROR,
    bed_error_to_response,
    error_response,
)
from core.structured_logging import emit_json_log
from scenes import SceneStore
from subscriptions import BillingService, BillingServiceError
from time_utils import ensure_utc, from_iso, to_iso, utcnow

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
ASSETS_DIR = WEB_DIR / "assets"
PROFILE_PATH = USER_PROFILE_PATH
WEB_MEMORY_DIR = RUNTIME_DATA_DIR / "web_memory"
AUTOMATION_STATE_PATH = RUNTIME_DATA_DIR / "automations_state.json"
SLEEP_HISTORY_PATH = RUNTIME_DATA_DIR / "sleep_history.json"
store = SubscriptionStore()
scene_store = SceneStore()
undo_manager = UndoManager()
_CHAT_ENGINE_LOCK = threading.RLock()
_CHAT_ENGINES: dict[str, ConversationEngine] = {}
# Serialises all profile read-modify-write cycles to prevent concurrent-write clobber.
_PROFILE_RW_LOCK = threading.RLock()


@contextmanager
def _profile_rw():
    """Context manager that holds the profile RW lock for a full read-modify-write cycle.

    Usage::
        with _profile_rw():
            profile = _safe_profile()
            profile["section"][key] = value
            _save_profile(profile)
    """
    with _PROFILE_RW_LOCK:
        yield
_DB_CONNECTION: Any | None = None
_DB_CONNECTION_URL = ""
_DB_USER_REPOSITORY: Any | None = None
_SUBSCRIPTION_GATE: Any | None = None
_DB_BETA_PROGRESS_REPOSITORY: Any | None = None
_DB_EVENT_REPOSITORY: Any | None = None
_DB_SLEEP_SESSION_REPOSITORY: Any | None = None
_DB_COMMAND_REPOSITORY: Any | None = None
_DB_MOBILE_AUTH_REPOSITORY: Any | None = None
_BILLING_SERVICE: Any | None = None
_DB_UPDATE_REPOSITORY: Any | None = None
_DB_FEATURE_FLAG_REPOSITORY: Any | None = None
# Protects the lazy database-connection initialisation from concurrent requests
# racing to create duplicate connection pools on startup.
_DB_INIT_LOCK = threading.Lock()
_SLEEP_ENGINE = SleepIntelligenceEngine()

_SENSITIVE_EXACT_KEYS = {
    "access_token", "refresh_token", "password_hash", "password",
    "api_key", "secret", "client_secret", "private_key", "otp_code",
    "authorization", "x-api-key", "token", "id_token", "session_token",
    "stripe_secret", "paypal_secret", "sendgrid_api_key", "deepgram_api_key",
}
_SENSITIVE_PARTIAL_KEYS = ("secret", "password", "token", "api_key", "private_key", "credential")
_MAX_CHAT_ENGINES = 200
_DEVICE_STALE_WINDOW_SECONDS = 180
_TRACE_ID_HEADER = "X-Trace-Id"
SCENE_PREVIEW_SECONDS = 3.0
_cors_origins_raw = str(settings.web_allowed_origins_raw or "http://127.0.0.1:8000,http://localhost:8000")
ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
ALLOWED_ORIGIN_REGEX = str(settings.web_allowed_origin_regex or "").strip() or None
# Authoritative server hostname used by _enforce_same_origin to avoid trusting the client Host header.
# Set SERVER_HOSTNAME in .env for production (e.g. "api.danah.io").
_SERVER_HOSTNAME = str(os.getenv("SERVER_HOSTNAME", "") or "").strip().lower() or None
from core.logger import logger, setup_logging
setup_logging()


def _sentry_scrub_event(event: dict, hint: object) -> dict:
    """Strip sensitive keys from Sentry events before they leave the process."""
    for frame in (
        event.get("exception", {})
        .get("values", [{}])[0]
        .get("stacktrace", {})
        .get("frames", [])
    ):
        frame.get("vars", {}).pop("password", None)
        frame.get("vars", {}).pop("access_token", None)
        frame.get("vars", {}).pop("refresh_token", None)
        frame.get("vars", {}).pop("api_key", None)
        frame.get("vars", {}).pop("secret", None)
    request = event.get("request", {})
    for header in ("Authorization", "X-Api-Key", "Cookie"):
        request.get("headers", {}).pop(header, None)
    return event


# ── Sentry ────────────────────────────────────────────────────────────────
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    import logging as _logging

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            release=settings.sentry_release or None,
            traces_sample_rate=float(settings.sentry_traces_sample_rate),
            profiles_sample_rate=float(settings.sentry_profiles_sample_rate),
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=_logging.WARNING,       # breadcrumbs from WARNING+
                    event_level=_logging.ERROR,   # send events for ERROR+
                ),
            ],
            # Never forward secrets to Sentry
            before_send=_sentry_scrub_event,
        )
        logger.info(
            "Sentry initialised env=%s traces_rate=%s",
            settings.sentry_environment,
            settings.sentry_traces_sample_rate,
        )
    else:
        logger.debug("SENTRY_DSN not set — Sentry disabled")
except ImportError:
    logger.debug("sentry-sdk not installed — Sentry disabled")
# ─────────────────────────────────────────────────────────────────────────

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

@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info(
        "CORS configured allow_origins=%s allow_origin_regex=%s",
        ALLOWED_ORIGINS,
        ALLOWED_ORIGIN_REGEX,
    )
    try:
        from api.service_registry import initialize_services
        initialize_services(app)
    except Exception as exc:
        logger.warning("Automation service init error (non-fatal): %s", exc)
    try:
        from database import AsyncDatabaseConnection
        _async_db = AsyncDatabaseConnection()
        await _async_db.initialize()
        app.state.async_db = _async_db
    except Exception as exc:
        logger.warning("Async DB init skipped (non-fatal): %s", exc)
        app.state.async_db = None
    try:
        from ai.pgvector_memory_index import PgVectorMemoryIndex
        if app.state.async_db is not None:
            app.state.pgvector_index = PgVectorMemoryIndex(app.state.async_db)
        else:
            app.state.pgvector_index = None
    except Exception as exc:
        logger.warning("PgVectorMemoryIndex init skipped (non-fatal): %s", exc)
        app.state.pgvector_index = None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        _arq_settings = RedisSettings.from_dsn(settings.arq_redis_url)
        app.state.arq = await create_pool(_arq_settings)
    except Exception as exc:
        logger.warning("arq pool init skipped (non-fatal): %s", exc)
        app.state.arq = None
    try:
        from notifications.fcm_sender import FcmSender, initialize_firebase
        firebase_ok = initialize_firebase(
            credentials_path=settings.firebase_credentials_path,
            credentials_json=settings.firebase_credentials_json,
        )
        app.state.fcm_sender = FcmSender() if firebase_ok else None
    except Exception as exc:
        logger.warning("Firebase Admin SDK init skipped (non-fatal): %s", exc)
        app.state.fcm_sender = None
    yield
    _async_db_inst = getattr(app.state, "async_db", None)
    if _async_db_inst is not None:
        try:
            await _async_db_inst.close()
        except Exception as exc:
            logger.warning("Async DB shutdown error: %s", exc)
    _arq_pool = getattr(app.state, "arq", None)
    if _arq_pool is not None:
        try:
            await _arq_pool.close()
        except Exception as exc:
            logger.warning("arq pool shutdown error: %s", exc)


app = FastAPI(title="Danah Smart Bed API", version="1.0.0", lifespan=_lifespan)

from api.automation_routes import router as automation_router
app.include_router(automation_router)

from api.middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

_cors_credentials = bool(ALLOWED_ORIGINS) and "*" not in ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=_cors_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Trace-ID", "X-Request-ID"],
)


@app.exception_handler(BedError)
async def bed_error_handler(request: Request, exc: BedError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "")
    logger.warning("[BedError] %s: %s (trace=%s)", type(exc).__name__, exc.message, trace_id)
    return bed_error_to_response(exc, trace_id=trace_id)


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "")
    return error_response(exc.code, exc.message, trace_id=trace_id, retry_after=exc.retry_after)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = _new_trace_id()
    request.state.trace_id = trace_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = max(0.0, time.perf_counter() - started)
    status_code = int(getattr(response, "status_code", 200) or 200)
    method = str(request.method or "GET")
    path = str(request.url.path or "/")
    status_key = str(status_code)
    REQUEST_COUNT.labels(method=method, path=path, status_code=status_key).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
    if status_code >= 400:
        ERROR_COUNT.labels(method=method, path=path, status_code=status_key).inc()

    response.headers[_TRACE_ID_HEADER] = trace_id
    try:
        reason = HTTPStatus(status_code).phrase
    except Exception:
        reason = "UNKNOWN"
    elapsed_ms = int(round(elapsed * 1000.0))
    logger.info("[TRACE: %s] %s %s - %d %s - %dms", trace_id, method, path, status_code, reason, elapsed_ms)
    _event(
        "info",
        "http_request",
        trace_id=trace_id,
        method=method,
        path=path,
        status_code=status_code,
        latency_ms=elapsed_ms,
    )
    return response


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4096)


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    source: str = Field(default="web", max_length=32)


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
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    name: str = Field(default="", max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserSettingsRequest(BaseModel):
    response_style: str = Field(default="balanced", max_length=64)
    engagement_level: str = Field(default="high", max_length=64)
    wind_down_minutes: int = Field(default=45, ge=0, le=480)
    partner_mode_enabled: bool = False
    bedtime_drift_automation_enabled: bool = True
    quiet_hours_override_limit_minutes: int = Field(default=120, ge=0, le=480)
    weekly_insight_enabled: bool = True


class AdminActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)


class BetaCohortEnrollRequest(BaseModel):
    user_id: str = Field(default="", max_length=128)
    email: str = Field(default="", max_length=254)
    cohort_key: str = Field(default="kuwait_beta", max_length=64)
    country_code: str = Field(default="KW", max_length=8)
    status: Literal["candidate", "invited", "active", "paused", "graduated", "inactive"] = "active"
    source: str = Field(default="admin_manual", max_length=64)
    notes: str = Field(default="", max_length=2048)


class UserRoutineRequest(BaseModel):
    bedtime: str = Field(default="22:30", max_length=16)
    wake: str = Field(default="07:00", max_length=16)
    weekends: bool = True


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


class UserDeviceControlRequest(BaseModel):
    lights_on: bool = False
    audio_on: bool = False
    alarm_on: bool = True
    light_level: int = Field(default=65, ge=0, le=100)


class UserActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=128)


class UserDeviceCommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=128)


class SceneSelectionRequest(BaseModel):
    scene_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_\-]+$")


class PublishAppVersionRequest(BaseModel):
    platform: str = Field(default="all", max_length=32)
    version_string: str = Field(min_length=1, max_length=32)
    build_number: int = Field(default=0, ge=0)
    changelog: list[str] = Field(default_factory=list, max_length=100)
    is_required: bool = False
    rollout_percent: int = Field(default=100, ge=0, le=100)
    min_supported_version: str = Field(default="", max_length=32)
    store_url_ios: str = Field(default="", max_length=2048)
    store_url_android: str = Field(default="", max_length=2048)


class PublishFirmwareVersionRequest(BaseModel):
    version_string: str = Field(min_length=1, max_length=32)
    changelog: list[str] = Field(default_factory=list, max_length=100)
    download_url: str = Field(default="", max_length=2048)
    is_required: bool = False
    rollout_percent: int = Field(default=100, ge=0, le=100)
    target_device_ids: list[str] = Field(default_factory=list, max_length=1000)


class RegisterPushTokenRequest(BaseModel):
    expo_token: str = Field(min_length=1, max_length=512)
    platform: str = Field(default="android", max_length=32)


class PatchVersionRequest(BaseModel):
    rollout_percent: int | None = None
    is_required: bool | None = None
    is_active: bool | None = None


class UpsertFeatureFlagRequest(BaseModel):
    flag_key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_\-]+$")
    display_name: str = Field(default="", max_length=256)
    description: str = Field(default="", max_length=2048)
    enabled_globally: bool = False
    enabled_for_plans: list[str] = Field(default_factory=list, max_length=20)
    rollout_percent: int = Field(default=0, ge=0, le=100)


class PatchFeatureFlagRequest(BaseModel):
    enabled_globally: bool | None = None
    enabled_for_plans: list[str] | None = None
    rollout_percent: int | None = Field(default=None, ge=0, le=100)


class SetUserFeatureOverrideRequest(BaseModel):
    flag_key: str = Field(min_length=1, max_length=128)
    override_value: bool
    reason: str = Field(default="", max_length=512)


class PatchAdminUserRequest(BaseModel):
    subscription_status: str | None = Field(default=None, max_length=32)
    trial_end_date: str | None = Field(default=None, max_length=32)


class SceneComposeRequest(BaseModel):
    name: str = Field(default="", max_length=256)
    light: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    premium: bool = False
    category: str = Field(default="", max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=20)


class TrialStartRequest(BaseModel):
    user_id: str = Field(default="", max_length=128)


class UndoActionRequest(BaseModel):
    user_id: str = Field(default="", max_length=128)


class SpotifyPlaybackRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    device_id: str = Field(default="", max_length=128)
    playlist_uri: str = Field(default="", max_length=512)
    volume_percent: int = Field(default=50, ge=0, le=100)


class MobileRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    name: str = Field(default="", max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileOtpRequestRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=32)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileOtpVerifyRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    phone_number: str = Field(min_length=7, max_length=32)
    otp_code: str = Field(min_length=4, max_length=8)
    name: str = Field(default="", max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileSocialLoginRequest(BaseModel):
    provider: Literal["google", "apple", "facebook"]
    provider_user_id: str = Field(default="", max_length=256)
    provider_access_token: str = Field(default="", max_length=4096)
    provider_id_token: str = Field(default="", max_length=4096)
    provider_auth_code: str = Field(default="", max_length=2048)
    email: str = Field(default="", max_length=254)
    name: str = Field(default="", max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class MobileLogoutRequest(BaseModel):
    refresh_token: str = Field(default="", max_length=2048)


class MobileBedPairRequest(BaseModel):
    qr_payload: str = Field(default="", max_length=2048)
    device_id: str = Field(default="", max_length=128)
    claim_token: str = Field(default="", max_length=512)
    bed_location: str = Field(default="Kuwait", max_length=128)


class MobileBedUnpairRequest(BaseModel):
    device_id: str = Field(default="", max_length=128)


class MobileAlarmUpsertRequest(BaseModel):
    alarm_id: str = Field(default="", max_length=128)
    time: str = Field(default="07:00", max_length=16)
    days: list[int] = Field(default_factory=list, max_length=7)
    enabled: bool = True
    label: str = Field(default="", max_length=256)
    sound: str = Field(default="default", max_length=128)
    vibrate: bool = True


class MobileAlarmToggleRequest(BaseModel):
    enabled: bool


class MobileSubscriptionCheckoutRequest(BaseModel):
    tier: Literal["standard", "pro"] = "standard"
    interval: Literal["monthly", "yearly"] = "monthly"
    return_url: str = Field(default="", max_length=2048)
    cancel_url: str = Field(default="", max_length=2048)


class MobileSubscriptionCaptureRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=256)
    payer_id: str = Field(default="", max_length=256)
    provider_order_id: str = Field(default="", max_length=256)
    provider_subscription_id: str = Field(default="", max_length=256)


class MobileSubscriptionCancelRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=256)


class MobileSubscriptionActionRequest(BaseModel):
    reason: str = Field(default="", max_length=512)


class BillingWebhookRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    session_id: str = Field(default="", max_length=256)
    user_id: str = Field(default="", max_length=128)
    tier: str = Field(default="", max_length=32)
    interval: str = Field(default="monthly", max_length=32)
    raw: dict[str, Any] = Field(default_factory=dict)
    resource: dict[str, Any] = Field(default_factory=dict)


class FirstThreeNightsStepRequest(BaseModel):
    step_key: Literal[
        "signup",
        "first_scene_preview",
        "first_automation",
        "first_winddown",
        "timeline_review",
    ]


class NightlySummaryFeedbackRequest(BaseModel):
    vote: Literal["helpful", "not_helpful"]
    summary_generated_at_utc: str = ""


class DeviceCommandFeedbackRequest(BaseModel):
    vote: Literal["helpful", "not_helpful"]
    note: str = Field(default="", max_length=1024)


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


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _sleep_history_sessions() -> list[dict[str, Any]]:
    payload = locked_read_json(SLEEP_HISTORY_PATH)
    if not isinstance(payload, dict):
        return []
    raw_sessions = payload.get("sessions", [])
    if not isinstance(raw_sessions, list):
        return []
    return [row for row in raw_sessions if isinstance(row, dict)]


def _parse_optional_utc_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return from_iso(text)
    except Exception:
        return None


def _sleep_readiness_score(now_utc: datetime) -> int:
    score = 70
    sessions = _sleep_history_sessions()
    last_session = sessions[-1] if sessions else {}
    last_bedtime = _parse_optional_utc_datetime(last_session.get("bedtime", "")) if isinstance(last_session, dict) else None
    bedtime_hour = int(last_bedtime.hour) if isinstance(last_bedtime, datetime) else -1

    if 21 <= bedtime_hour < 23:
        score += 10
    elif bedtime_hour >= 23:
        score -= 10

    if len(sessions) >= 3:
        score += 5
    else:
        score -= 5

    return _clamp_score(score)


def _sleep_readiness_explanation(score: int) -> str:
    if score >= 80:
        return "You have been consistent this week. Great habits!"
    if score >= 60:
        return "You are building good sleep habits. Keep going!"
    return "Let us help you improve your sleep consistency."


def _recommended_scene_for_sleep_overview(now_utc: datetime) -> dict[str, Any]:
    hour = int(now_utc.hour)
    if 20 <= hour < 23:
        scene_name = "Cozy Night"
        reason = "Perfect for winding down"
    elif (hour >= 23) or (hour < 4):
        scene_name = "Deep Sleep"
        reason = "Time to rest deeply"
    elif 4 <= hour < 9:
        scene_name = "Gentle Wake"
        reason = "Start your morning gently"
    else:
        scene_name = "Cozy Night"
        reason = "Best scene for this time of night"

    scene_id: str | None = None
    for scene in scene_store.get_all_templates():
        if str(scene.get("name", "")).strip().lower() == scene_name.lower():
            resolved_id = str(scene.get("id", "")).strip()
            scene_id = resolved_id or None
            break

    return {
        "id": scene_id,
        "name": scene_name,
        "reason": reason,
    }


def _sleep_quick_actions(now_utc: datetime) -> list[dict[str, str]]:
    hour = int(now_utc.hour)
    if 22 <= hour < 24:
        return [
            {"label": "Sleep Now", "action": "sleep_now"},
            {"label": "Read Mode", "action": "read_mode"},
            {"label": "Disable Automations", "action": "automations_disable"},
        ]
    if hour < 6:
        return [
            {"label": "Gentle Wake", "action": "gentle_wake"},
            {"label": "View Last Night", "action": "view_last_night"},
            {"label": "Set Alarm", "action": "alarm_set"},
        ]
    return [
        {"label": "Start Wind-Down", "action": "winddown_start"},
        {"label": "Dim Everything", "action": "dim_all"},
        {"label": "Set Alarm", "action": "alarm_set"},
    ]


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

    try:
        from database.connection import DatabaseConnection
        from database.models import SpotifyToken
        from sqlalchemy import func, select
        with DatabaseConnection().get_session() as _s:
            _spotify_count = _s.scalar(select(func.count()).select_from(SpotifyToken)) or 0
    except Exception:
        _spotify_count = 0

    return {
        "deepgram_configured": bool(str(settings.deepgram_api_key or "").strip()),
        "spotify_connected_users": _spotify_count,
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
    with _PROFILE_RW_LOCK:
        _save_profile_unlocked(payload)


def _save_profile_unlocked(payload: dict[str, Any]):
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
        "web_command_feedback",
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

    try:
        quiet_override_limit = int(
            data.get(
                "quiet_hours_override_limit_minutes",
                settings.quiet_hours_override_max_minutes or 120,
            )
            or (settings.quiet_hours_override_max_minutes or 120)
        )
    except Exception:
        quiet_override_limit = int(settings.quiet_hours_override_max_minutes or 120)
    quiet_override_limit = max(30, min(240, quiet_override_limit))

    return {
        "response_style": response_style,
        "engagement_level": engagement_level,
        "wind_down_minutes": wind_down,
        "partner_mode_enabled": bool(data.get("partner_mode_enabled", False)),
        "bedtime_drift_automation_enabled": bool(
            data.get("bedtime_drift_automation_enabled", True)
        ),
        "quiet_hours_override_limit_minutes": quiet_override_limit,
        "weekly_insight_enabled": bool(data.get("weekly_insight_enabled", True)),
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


def _resolved_user_settings(profile: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    prefs = profile.get("preferences", {}) if isinstance(profile.get("preferences", {}), dict) else {}
    sleep = profile.get("sleep", {}) if isinstance(profile.get("sleep", {}), dict) else {}
    try:
        quiet_override_limit = int(
            prefs.get(
                "quiet_hours_override_limit_minutes",
                settings.quiet_hours_override_max_minutes or 120,
            )
            or (settings.quiet_hours_override_max_minutes or 120)
        )
    except Exception:
        quiet_override_limit = int(settings.quiet_hours_override_max_minutes or 120)
    defaults = _normalize_user_settings(
        {
            "response_style": prefs.get("response_style", "balanced"),
            "engagement_level": prefs.get("engagement_level", "high"),
            "partner_mode_enabled": bool((sleep.get("partner_mode") or {}).get("enabled", False)),
            "wind_down_minutes": int(sleep.get("wind_down_minutes", 45) or 45),
            "bedtime_drift_automation_enabled": bool(
                prefs.get("bedtime_drift_automation_enabled", True)
            ),
            "quiet_hours_override_limit_minutes": quiet_override_limit,
            "weekly_insight_enabled": bool(prefs.get("weekly_insight_enabled", True)),
        }
    )
    return _profile_user_settings(profile, user, defaults)


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
    display_name = str(data.get("display_name", "") or "").strip()
    timezone = str(data.get("timezone", "Asia/Kuwait") or "Asia/Kuwait").strip()
    if not timezone:
        timezone = "Asia/Kuwait"

    location_mode = str(data.get("location_mode", "auto") or "auto").strip().lower()
    if location_mode not in {"auto", "manual"}:
        location_mode = "auto"

    theme_mode = str(data.get("theme_mode", "system") or "system").strip().lower()
    if theme_mode not in {"system", "dark", "light"}:
        theme_mode = "system"

    city = str(data.get("city", "") or "").strip()
    country_code = str(data.get("country_code", "") or "").strip().upper()[:2]

    def _coerce_coordinate(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            coordinate = float(value)
        except Exception:
            return None
        return round(coordinate, 6)

    return {
        "display_name": display_name,
        "timezone": timezone,
        "push_enabled": bool(data.get("push_enabled", True)),
        "email_enabled": bool(data.get("email_enabled", False)),
        "location_mode": location_mode,
        "country_code": country_code,
        "city": city,
        "latitude": _coerce_coordinate(data.get("latitude")),
        "longitude": _coerce_coordinate(data.get("longitude")),
        "theme_mode": theme_mode,
    }


def _email_local_part(value: str) -> str:
    email = str(value or "").strip()
    if "@" in email:
        return email.split("@", 1)[0].strip()
    return email


def _first_name_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.split(r"\s+", text)[0].strip()


def _resolved_user_display_name(
    user: dict[str, Any],
    profile_prefs: dict[str, Any] | None = None,
) -> str:
    prefs = profile_prefs if isinstance(profile_prefs, dict) else {}
    configured = _first_name_token(str(prefs.get("display_name", "") or ""))
    if configured:
        return configured

    account_name = _first_name_token(str(user.get("name", "") or ""))
    if account_name:
        return account_name

    email_name = _first_name_token(_email_local_part(str(user.get("email", "") or "")))
    return email_name or "User"


def _country_name_from_code(code: str) -> str:
    mapping = {
        "KW": "Kuwait",
        "PK": "Pakistan",
        "SA": "Saudi Arabia",
        "AE": "United Arab Emirates",
        "QA": "Qatar",
        "BH": "Bahrain",
        "OM": "Oman",
        "EG": "Egypt",
        "TR": "Turkey",
        "GB": "United Kingdom",
        "US": "United States",
    }
    key = str(code or "").strip().upper()
    if key in mapping:
        return mapping[key]
    if len(key) == 2 and key.isalpha():
        return key
    return ""


def _profile_location_summary(profile_prefs: dict[str, Any]) -> dict[str, Any]:
    prefs = profile_prefs if isinstance(profile_prefs, dict) else {}
    mode = str(prefs.get("location_mode", "auto") or "auto").strip().lower() or "auto"
    city = str(prefs.get("city", "") or "").strip()
    country_code = str(prefs.get("country_code", "") or "").strip().upper()
    country_name = _country_name_from_code(country_code)
    timezone_name = str(prefs.get("timezone", "") or "").strip()
    latitude = prefs.get("latitude")
    longitude = prefs.get("longitude")

    parts = [part for part in (city, country_name or country_code) if part]
    if parts:
        label = ", ".join(parts)
    elif latitude is not None and longitude is not None:
        label = (
            f"{timezone_name or 'Detected location'} · "
            f"{float(latitude):.2f}, {float(longitude):.2f}"
        )
    elif timezone_name:
        label = timezone_name
    else:
        label = "Location pending"

    return {
        "mode": mode,
        "city": city,
        "country_code": country_code,
        "country_name": country_name,
        "timezone": timezone_name,
        "latitude": latitude,
        "longitude": longitude,
        "label": label,
    }


def _fallback_location_from_profile(profile_prefs: dict[str, Any]) -> tuple[str, str]:
    timezone_name = str(profile_prefs.get("timezone", "") or "").strip()
    country_code = str(profile_prefs.get("country_code", "") or "").strip().upper()
    city = str(profile_prefs.get("city", "") or "").strip()
    country_name = _country_name_from_code(country_code)

    if city and country_name:
        return city, country_name
    if city:
        return city, country_name or "Kuwait"
    if country_code == "PK" or timezone_name == "Asia/Karachi":
        return "Karachi", "Pakistan"
    return "Kuwait City", "Kuwait"


def _mobile_prayer_service_for_user(
    user: dict[str, Any],
    profile: dict[str, Any],
):
    from islamic_mode.prayer_times import PrayerTimesService

    profile_prefs = _chat_profile_prefs_for_user(profile, user)
    location = _profile_location_summary(profile_prefs)
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    mode = str(location.get("mode", "auto") or "auto").strip().lower()
    if mode == "auto" and latitude is not None and longitude is not None:
        service = PrayerTimesService(
            method=8,
            latitude=float(latitude),
            longitude=float(longitude),
        )
    else:
        city, country = _fallback_location_from_profile(profile_prefs)
        service = PrayerTimesService(city=city, country=country, method=8)

    prayer_bundle = service.get_today_prayer_bundle()
    resolved_location = _profile_location_summary(
        {
            **profile_prefs,
            "timezone": str(
                ((prayer_bundle.get("location") or {}) if isinstance(prayer_bundle, dict) else {}).get("timezone", "")
                or location.get("timezone", "")
                or "Asia/Kuwait"
            ).strip(),
            "city": str(
                ((prayer_bundle.get("location") or {}) if isinstance(prayer_bundle, dict) else {}).get("city", "")
                or location.get("city", "")
            ).strip(),
            "country_code": str(location.get("country_code", "") or "").strip().upper(),
            "latitude": ((prayer_bundle.get("location") or {}) if isinstance(prayer_bundle, dict) else {}).get(
                "latitude",
                latitude,
            ),
            "longitude": ((prayer_bundle.get("location") or {}) if isinstance(prayer_bundle, dict) else {}).get(
                "longitude",
                longitude,
            ),
            "location_mode": mode,
        }
    )
    return service, prayer_bundle, resolved_location, profile_prefs


def _mobile_islamic_overview_payload(user: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    from islamic_mode.hadith_daily import HadithService
    from islamic_mode.islamic_calendar import IslamicCalendarService
    from islamic_mode.sunnah_tips import SunnahSleepTips

    service, prayer_bundle, location, _ = _mobile_prayer_service_for_user(user, profile)
    calendar_service = IslamicCalendarService()
    hadith_service = HadithService()
    tips_service = SunnahSleepTips()

    prayers = prayer_bundle.get("prayers", {}) if isinstance(prayer_bundle, dict) else {}
    next_prayer = service.get_next_prayer()
    hijri = calendar_service.get_hijri_date()
    event = calendar_service.get_todays_islamic_event()

    return {
        "prayers": prayers,
        "next_prayer": next_prayer,
        "location": location,
        "hadith": hadith_service.get_daily_hadith(),
        "sleep_hadith": hadith_service.get_sleep_hadith(),
        "hijri": hijri,
        "islamic_event": event,
        "ramadan_active": calendar_service.is_ramadan(),
        "sunnah_tip": tips_service.get_tip_of_night(),
        "led_color": service.get_prayer_led_color(str(next_prayer.get("name", "") or "")),
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


_MOBILE_OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", str(10 * 60)))
_MOBILE_OTP_MAX_ATTEMPTS = 5
_MOBILE_ALARM_MAX_ITEMS = 12


def _mobile_otp_debug_enabled() -> bool:
    return str(os.getenv("MOBILE_OTP_DEBUG", "1") or "1").strip() != "0"


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_phone_number(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    return f"+{digits}"


def _mask_phone_number(phone_number: str) -> str:
    raw = str(phone_number or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) <= 4:
        return raw or "unknown"
    return f"+{'*' * (len(digits) - 4)}{digits[-4:]}"


def _otp_hmac_digest(*, phone_number: str, request_id: str, otp_code: str) -> str:
    secret = (
        str(os.getenv("MOBILE_OTP_SECRET", "") or "").strip()
        or str(settings.secret_key or "").strip()
    )
    if not secret or secret in {"change-me-in-production", "secret", "changeme", "development"}:
        logger.warning("MOBILE_OTP_SECRET not set — OTP HMAC uses weak fallback")
        secret = settings.secret_key or "change-me-in-production"
    message = f"{phone_number}|{request_id}|{otp_code}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _mobile_http_json_request(
    *,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query_params: dict[str, Any] | None = None,
    form_data: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: int = 15,
    error_prefix: str = "External auth provider",
) -> dict[str, Any]:
    base_url = str(url or "").strip()
    if not base_url:
        return {}

    final_url = base_url
    if isinstance(query_params, dict) and query_params:
        encoded_query = urlencode({k: "" if v is None else str(v) for k, v in query_params.items()})
        sep = "&" if "?" in base_url else "?"
        final_url = f"{base_url}{sep}{encoded_query}"

    request_body = None
    merged_headers = {str(k): str(v) for k, v in (headers or {}).items() if str(k).strip()}
    if isinstance(form_data, dict):
        request_body = urlencode({k: "" if v is None else str(v) for k, v in form_data.items()}).encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif isinstance(json_body, dict):
        request_body = json.dumps(json_body, ensure_ascii=True).encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json")

    request = UrlRequest(final_url, data=request_body, method=str(method or "GET").upper())
    for key, value in merged_headers.items():
        request.add_header(key, value)

    try:
        with urlopen(request, timeout=max(3, int(timeout_seconds))) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return {}
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
            return payload if isinstance(payload, dict) else {"data": payload}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise HTTPException(status_code=502, detail=f"{error_prefix} HTTP error: {exc.code} {detail[:180]}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"{error_prefix} is unreachable") from exc


def _mobile_otp_delivery_mode() -> str:
    raw = str(os.getenv("MOBILE_OTP_DELIVERY_MODE", "auto") or "auto").strip().lower()
    if raw in {"simulated", "twilio_sms", "webhook", "auto"}:
        return raw
    return "auto"


def _mobile_otp_delivery_timeout_seconds() -> int:
    raw = str(os.getenv("MOBILE_OTP_DELIVERY_TIMEOUT_SECONDS", "15") or "15").strip()
    try:
        value = int(raw)
    except Exception:
        value = 15
    return max(3, min(60, value))


def _mobile_twilio_sms_config() -> dict[str, str]:
    return {
        "account_sid": str(os.getenv("TWILIO_ACCOUNT_SID", "") or "").strip(),
        "auth_token": str(os.getenv("TWILIO_AUTH_TOKEN", "") or "").strip(),
        "from_number": str(os.getenv("TWILIO_SMS_FROM", "") or "").strip(),
    }


def _mobile_twilio_sms_configured(config: dict[str, str]) -> bool:
    return bool(
        str(config.get("account_sid", "")).strip()
        and str(config.get("auth_token", "")).strip()
        and str(config.get("from_number", "")).strip()
    )


def _mobile_otp_sms_message(otp_code: str) -> str:
    ttl_minutes = max(1, int(_MOBILE_OTP_TTL_SECONDS // 60))
    template = str(
        os.getenv(
            "MOBILE_OTP_SMS_TEMPLATE",
            "Danah verification code: {code}. It expires in {minutes} minutes.",
        )
        or ""
    ).strip()
    if not template:
        template = "Danah verification code: {code}. It expires in {minutes} minutes."
    try:
        rendered = template.format(code=otp_code, minutes=ttl_minutes)
    except Exception:
        rendered = f"Danah verification code: {otp_code}. It expires in {ttl_minutes} minutes."
    return " ".join(str(rendered).split())


def _mobile_send_otp_via_twilio(phone_number: str, otp_code: str) -> dict[str, Any]:
    config = _mobile_twilio_sms_config()
    if not _mobile_twilio_sms_configured(config):
        raise HTTPException(status_code=500, detail="Twilio SMS delivery is not configured")

    account_sid = config.get("account_sid", "")
    auth_token = config.get("auth_token", "")
    auth_bytes = f"{account_sid}:{auth_token}".encode("utf-8")
    basic = base64.b64encode(auth_bytes).decode("ascii")
    payload = _mobile_http_json_request(
        url=f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        method="POST",
        headers={"Authorization": f"Basic {basic}"},
        form_data={
            "To": phone_number,
            "From": str(config.get("from_number", "")).strip(),
            "Body": _mobile_otp_sms_message(otp_code),
        },
        timeout_seconds=_mobile_otp_delivery_timeout_seconds(),
        error_prefix="Twilio SMS",
    )
    return {
        "provider": "twilio_sms",
        "message_id": str(payload.get("sid", "") or ""),
        "status": str(payload.get("status", "queued") or "queued"),
    }


def _mobile_send_otp_via_webhook(phone_number: str, otp_code: str, request_id: str) -> dict[str, Any]:
    webhook_url = str(os.getenv("MOBILE_OTP_WEBHOOK_URL", "") or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=500, detail="OTP webhook delivery is not configured")

    headers: dict[str, str] = {}
    webhook_bearer = str(os.getenv("MOBILE_OTP_WEBHOOK_BEARER", "") or "").strip()
    if webhook_bearer:
        headers["Authorization"] = f"Bearer {webhook_bearer}"

    payload = _mobile_http_json_request(
        url=webhook_url,
        method="POST",
        headers=headers,
        json_body={
            "phone_number": phone_number,
            "otp_code": otp_code,
            "request_id": request_id,
            "ttl_seconds": _MOBILE_OTP_TTL_SECONDS,
            "message": _mobile_otp_sms_message(otp_code),
        },
        timeout_seconds=_mobile_otp_delivery_timeout_seconds(),
        error_prefix="OTP webhook",
    )
    accepted = payload.get("ok", payload.get("accepted", True))
    if not bool(accepted):
        raise HTTPException(status_code=502, detail="OTP webhook rejected delivery")
    return {
        "provider": "webhook",
        "message_id": str(payload.get("message_id", "") or payload.get("id", "") or ""),
        "status": str(payload.get("status", "accepted") or "accepted"),
    }


def _mobile_send_otp_code(phone_number: str, otp_code: str, request_id: str) -> dict[str, Any]:
    mode = _mobile_otp_delivery_mode()
    if mode == "auto":
        if _mobile_twilio_sms_configured(_mobile_twilio_sms_config()):
            mode = "twilio_sms"
        elif str(os.getenv("MOBILE_OTP_WEBHOOK_URL", "") or "").strip():
            mode = "webhook"
        else:
            mode = "simulated"

    if mode == "simulated":
        return {"provider": "simulated", "message_id": "", "status": "accepted"}
    if mode == "twilio_sms":
        return _mobile_send_otp_via_twilio(phone_number, otp_code)
    if mode == "webhook":
        return _mobile_send_otp_via_webhook(phone_number, otp_code, request_id)
    return {"provider": "simulated", "message_id": "", "status": "accepted"}


def _sanitize_identity_value(value: Any, *, max_len: int = 64) -> str:
    raw = str(value or "").strip().lower()
    safe = re.sub(r"[^a-z0-9._-]+", "_", raw).strip("._-")
    if not safe:
        safe = "user"
    return safe[:max_len]


def _phone_shadow_email(phone_number: str) -> str:
    digits = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
    tail = digits[-12:] if digits else secrets.token_hex(4)
    return f"phone_{tail}@phone.local"


def _social_shadow_email(provider: str, provider_user_id: str) -> str:
    safe_provider = _sanitize_identity_value(provider, max_len=16)
    safe_identity = _sanitize_identity_value(provider_user_id, max_len=48)
    return f"{safe_provider}_{safe_identity}@social.local"


def _mobile_social_allow_unverified() -> bool:
    return _env_truthy("MOBILE_SOCIAL_ALLOW_UNVERIFIED", default=False)


def _mobile_social_timeout_seconds() -> int:
    raw = str(os.getenv("MOBILE_SOCIAL_TIMEOUT_SECONDS", "15") or "15").strip()
    try:
        seconds = int(raw)
    except Exception:
        seconds = 15
    return max(3, min(60, seconds))


def _social_claim_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _safe_epoch_seconds(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


from auth.jwt_handler import decode_unverified as _decode_jwt_payload_unverified  # noqa: E402


def _verify_google_social_identity(*, access_token: str = "", id_token: str = "") -> dict[str, Any]:
    token = str(access_token or "").strip()
    identity_token = str(id_token or "").strip()
    if not token and not identity_token:
        raise HTTPException(status_code=422, detail="Google login requires provider_access_token or provider_id_token")

    google_client_id = str(os.getenv("MOBILE_SOCIAL_GOOGLE_CLIENT_ID", "") or "").strip()
    provider_payload: dict[str, Any] = {}

    if identity_token:
        provider_payload = _mobile_http_json_request(
            url="https://oauth2.googleapis.com/tokeninfo",
            method="GET",
            query_params={"id_token": identity_token},
            timeout_seconds=_mobile_social_timeout_seconds(),
            error_prefix="Google token verification",
        )
        provider_user_id = str(provider_payload.get("sub", "") or "").strip()
        if not provider_user_id:
            raise HTTPException(status_code=401, detail="Google identity token is invalid")
        aud = str(provider_payload.get("aud", "") or "").strip()
        if google_client_id and aud and aud != google_client_id:
            raise HTTPException(status_code=401, detail="Google token audience mismatch")
        exp_at = _safe_epoch_seconds(provider_payload.get("exp"))
        now_ts = int(ensure_utc(utcnow()).timestamp())
        if exp_at and exp_at < now_ts - 30:
            raise HTTPException(status_code=401, detail="Google identity token is expired")
        return {
            "provider_user_id": provider_user_id,
            "email": str(provider_payload.get("email", "") or "").strip().lower(),
            "name": str(provider_payload.get("name", "") or "").strip(),
            "email_verified": _social_claim_bool(provider_payload.get("email_verified")),
            "verification_method": "google_id_token",
        }

    provider_payload = _mobile_http_json_request(
        url="https://openidconnect.googleapis.com/v1/userinfo",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
        timeout_seconds=_mobile_social_timeout_seconds(),
        error_prefix="Google access token",
    )
    provider_user_id = str(provider_payload.get("sub", "") or provider_payload.get("id", "") or "").strip()
    if not provider_user_id:
        raise HTTPException(status_code=401, detail="Google access token is invalid")
    return {
        "provider_user_id": provider_user_id,
        "email": str(provider_payload.get("email", "") or "").strip().lower(),
        "name": str(provider_payload.get("name", "") or "").strip(),
        "email_verified": _social_claim_bool(provider_payload.get("email_verified")),
        "verification_method": "google_access_token",
    }


def _verify_facebook_social_identity(*, access_token: str = "") -> dict[str, Any]:
    token = str(access_token or "").strip()
    if not token:
        raise HTTPException(status_code=422, detail="Facebook login requires provider_access_token")

    app_secret = str(os.getenv("MOBILE_SOCIAL_FACEBOOK_APP_SECRET", "") or "").strip()
    app_id = str(os.getenv("MOBILE_SOCIAL_FACEBOOK_APP_ID", "") or "").strip()
    appsecret_proof = ""
    if app_secret:
        appsecret_proof = hmac.new(app_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()

    params = {
        "fields": "id,name,email",
        "access_token": token,
    }
    if appsecret_proof:
        params["appsecret_proof"] = appsecret_proof
    provider_payload = _mobile_http_json_request(
        url="https://graph.facebook.com/me",
        method="GET",
        query_params=params,
        timeout_seconds=_mobile_social_timeout_seconds(),
        error_prefix="Facebook token verification",
    )
    provider_user_id = str(provider_payload.get("id", "") or "").strip()
    if not provider_user_id:
        raise HTTPException(status_code=401, detail="Facebook access token is invalid")

    if app_id and app_secret:
        debug_payload = _mobile_http_json_request(
            url="https://graph.facebook.com/debug_token",
            method="GET",
            query_params={
                "input_token": token,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout_seconds=_mobile_social_timeout_seconds(),
            error_prefix="Facebook debug token",
        )
        debug_data = debug_payload.get("data", {}) if isinstance(debug_payload.get("data", {}), dict) else {}
        if not bool(debug_data.get("is_valid", False)):
            raise HTTPException(status_code=401, detail="Facebook access token is invalid")
        token_app_id = str(debug_data.get("app_id", "") or "").strip()
        if token_app_id and token_app_id != app_id:
            raise HTTPException(status_code=401, detail="Facebook token audience mismatch")

    return {
        "provider_user_id": provider_user_id,
        "email": str(provider_payload.get("email", "") or "").strip().lower(),
        "name": str(provider_payload.get("name", "") or "").strip(),
        "email_verified": bool(str(provider_payload.get("email", "") or "").strip()),
        "verification_method": "facebook_access_token",
    }


def _apple_social_config() -> dict[str, str]:
    return {
        "client_id": str(os.getenv("MOBILE_SOCIAL_APPLE_CLIENT_ID", "") or "").strip(),
        "client_secret": str(os.getenv("MOBILE_SOCIAL_APPLE_CLIENT_SECRET", "") or "").strip(),
    }


def _exchange_apple_social_auth_code(auth_code: str) -> dict[str, Any]:
    config = _apple_social_config()
    client_id = str(config.get("client_id", "")).strip()
    client_secret = str(config.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Apple social auth code verification is not configured",
        )

    payload = _mobile_http_json_request(
        url="https://appleid.apple.com/auth/token",
        method="POST",
        form_data={
            "grant_type": "authorization_code",
            "code": str(auth_code or "").strip(),
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout_seconds=_mobile_social_timeout_seconds(),
        error_prefix="Apple auth code exchange",
    )
    error_code = str(payload.get("error", "") or "").strip()
    if error_code:
        raise HTTPException(status_code=401, detail=f"Apple auth code is invalid: {error_code}")
    return payload


def _verify_apple_social_identity(*, id_token: str = "", auth_code: str = "") -> dict[str, Any]:
    verified_id_token = str(id_token or "").strip()
    if auth_code:
        exchange_payload = _exchange_apple_social_auth_code(auth_code)
        exchanged_id_token = str(exchange_payload.get("id_token", "") or "").strip()
        if exchanged_id_token:
            verified_id_token = exchanged_id_token

    if not verified_id_token:
        raise HTTPException(
            status_code=422,
            detail="Apple login requires provider_auth_code or provider_id_token",
        )

    claims = _decode_jwt_payload_unverified(verified_id_token)
    provider_user_id = str(claims.get("sub", "") or "").strip()
    if not provider_user_id:
        raise HTTPException(status_code=401, detail="Apple identity token is invalid")

    issuer = str(claims.get("iss", "") or "").strip()
    if issuer and issuer not in {"https://appleid.apple.com", "appleid.apple.com"}:
        raise HTTPException(status_code=401, detail="Apple token issuer is invalid")

    configured_client_id = str(_apple_social_config().get("client_id", "") or "").strip()
    audience = str(claims.get("aud", "") or "").strip()
    if configured_client_id and audience and audience != configured_client_id:
        raise HTTPException(status_code=401, detail="Apple token audience mismatch")

    exp_at = _safe_epoch_seconds(claims.get("exp"))
    now_ts = int(ensure_utc(utcnow()).timestamp())
    if exp_at and exp_at < now_ts - 30:
        raise HTTPException(status_code=401, detail="Apple identity token is expired")

    return {
        "provider_user_id": provider_user_id,
        "email": str(claims.get("email", "") or "").strip().lower(),
        "name": "",
        "email_verified": _social_claim_bool(claims.get("email_verified")),
        "verification_method": "apple_auth_code" if auth_code else "apple_id_token",
    }


def _verify_mobile_social_identity(payload: MobileSocialLoginRequest) -> dict[str, Any]:
    provider = str(payload.provider or "").strip().lower()
    access_token = str(payload.provider_access_token or "").strip()
    id_token = str(payload.provider_id_token or "").strip()
    auth_code = str(payload.provider_auth_code or "").strip()
    legacy_raw = str(payload.provider_user_id or "").strip()
    legacy_user_id = _sanitize_identity_value(legacy_raw, max_len=72) if legacy_raw else ""

    if (not access_token) and (not id_token) and (not auth_code):
        if legacy_user_id and _mobile_social_allow_unverified():
            return {
                "provider_user_id": legacy_user_id,
                "email": str(payload.email or "").strip().lower(),
                "name": str(payload.name or "").strip(),
                "email_verified": False,
                "verification_method": "legacy_unverified",
            }

    try:
        if provider == "google":
            verified = _verify_google_social_identity(access_token=access_token, id_token=id_token)
        elif provider == "facebook":
            verified = _verify_facebook_social_identity(access_token=access_token)
        elif provider == "apple":
            verified = _verify_apple_social_identity(id_token=id_token, auth_code=auth_code)
        else:
            raise HTTPException(status_code=422, detail="Unsupported social provider")
    except HTTPException as exc:
        detail = str(exc.detail or "")
        if exc.status_code == 502 and ("HTTP error: 400" in detail or "HTTP error: 401" in detail):
            raise HTTPException(status_code=401, detail="Social token is invalid or expired") from exc
        raise

    verified_user_id_raw = str(verified.get("provider_user_id", "") or "").strip()
    provider_user_id = _sanitize_identity_value(verified_user_id_raw, max_len=72) if verified_user_id_raw else ""
    if not provider_user_id:
        if legacy_user_id and _mobile_social_allow_unverified():
            provider_user_id = legacy_user_id
            verified["verification_method"] = "legacy_unverified"
            verified["email_verified"] = False
        else:
            raise HTTPException(status_code=401, detail="Social provider identity could not be verified")

    verified["provider_user_id"] = provider_user_id
    verified["email"] = str(verified.get("email", "") or "").strip().lower()
    verified["name"] = str(verified.get("name", "") or "").strip()
    verified["email_verified"] = bool(verified.get("email_verified", False))
    return verified


def _mobile_user_payload_by_id(user_id: str, *, client_name: str = "") -> dict[str, Any] | None:
    key = str(user_id or "").strip()
    if not key:
        return None
    db_user = _db_user_repository().get_user_by_id(key)
    if db_user is None:
        return None
    payload = _db_user_to_mobile_user_payload(db_user, client_name=client_name)
    _ensure_legacy_store_user_shadow(
        payload,
        password_hash=str(getattr(db_user, "password_hash", "") or "mobile_shadow_managed"),
    )
    return payload


def _ensure_external_identity_user(*, email: str, name: str, password_hash: str = "mobile_shadow_managed") -> dict[str, Any]:
    normalized_email = str(email or "").strip().lower()
    if "@" not in normalized_email:
        normalized_email = f"{_sanitize_identity_value(normalized_email or 'user', max_len=40)}@shadow.local"
    normalized_name = str(name or "").strip()

    repo = _db_user_repository()
    db_user = repo.get_user_by_email(normalized_email)
    if db_user is None:
        created = repo.create_user(
            email=normalized_email,
            password_hash=str(password_hash or "").strip() or "mobile_shadow_managed",
            full_name=normalized_name or None,
        )
        payload = _db_user_to_mobile_user_payload(created)
        _ensure_legacy_store_user_shadow(
            payload,
            password_hash=str(password_hash or "").strip() or "mobile_shadow_managed",
        )
        return payload

    if normalized_name and not str(getattr(db_user, "full_name", "") or "").strip():
        try:
            db_user = repo.update_user(str(getattr(db_user, "id", "") or ""), full_name=normalized_name)
        except Exception as _exc:
            logger.warning("update_user full_name failed user_id=%s err=%s", getattr(db_user, "id", "?"), _exc)

    payload = _db_user_to_mobile_user_payload(db_user)
    _ensure_legacy_store_user_shadow(
        payload,
        password_hash=str(getattr(db_user, "password_hash", "") or "mobile_shadow_managed"),
    )
    return payload


def _extract_device_id_from_qr_payload(qr_payload: str, *, fallback_device_id: str = "") -> str:
    raw = str(qr_payload or "").strip()
    fallback = str(fallback_device_id or "").strip()
    candidate = raw or fallback
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    if parsed.query:
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if str(key or "").strip().lower() == "device_id":
                candidate = str(value or "").strip()
                break
    elif "device_id=" in candidate.lower():
        _, _, suffix = candidate.lower().partition("device_id=")
        candidate = suffix.strip()

    normalized = re.sub(r"[^A-Za-z0-9._-]+", "", str(candidate or "").strip()).upper()
    return normalized[:80]


def _extract_claim_token_from_qr_payload(qr_payload: str, *, fallback_claim_token: str = "") -> str:
    fallback = str(fallback_claim_token or "").strip()
    raw = str(qr_payload or "").strip()
    if not raw:
        return fallback

    parsed = urlparse(raw)
    if parsed.query:
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            normalized_key = str(key or "").strip().lower()
            if normalized_key in {"claim_token", "pairing_token", "pair_token", "token"}:
                candidate = re.sub(r"[^A-Za-z0-9._-]+", "", str(value or "").strip())
                if candidate:
                    return candidate[:120]
    else:
        for segment in re.split(r"[?&]", raw):
            if "=" not in segment:
                continue
            key, _, value = segment.partition("=")
            normalized_key = str(key or "").strip().lower()
            if normalized_key in {"claim_token", "pairing_token", "pair_token", "token"}:
                candidate = re.sub(r"[^A-Za-z0-9._-]+", "", str(value or "").strip())
                if candidate:
                    return candidate[:120]
    return re.sub(r"[^A-Za-z0-9._-]+", "", fallback)[:120]


def _mobile_pairing_claim_required() -> bool:
    return _env_truthy("MOBILE_PAIRING_REQUIRE_CLAIM_TOKEN", default=True)


def _mobile_pairing_allow_auto_register() -> bool:
    return _env_truthy("MOBILE_PAIRING_ALLOW_AUTO_REGISTER", default=False)


def _pairing_claim_matches_device(device_row: dict[str, Any], claim_token: str) -> bool:
    row = device_row if isinstance(device_row, dict) else {}
    stored = str(row.get("claim_token", "") or "").strip()
    if not stored:
        return not _mobile_pairing_claim_required()
    candidate = str(claim_token or "").strip()
    if not candidate:
        return False
    return hmac.compare_digest(stored, candidate)


def _append_query_params(url: str, params: dict[str, str]) -> str:
    raw_url = str(url or "").strip()
    if not raw_url:
        return raw_url
    parsed = urlparse(raw_url)
    query_pairs = list(parse_qsl(parsed.query, keep_blank_values=True))
    query_map = {str(key): str(value) for key, value in query_pairs}
    for key, value in (params or {}).items():
        if str(key or "").strip():
            query_map[str(key)] = str(value or "")
    encoded = urlencode(query_map)
    return urlunparse(parsed._replace(query=encoded))


def _safe_mobile_done_uri(candidate: str) -> str:
    value = str(candidate or "").strip()
    if not value:
        return ""
    lower = value.lower()
    if lower.startswith("danah://") or lower.startswith("smartbed://"):
        return value
    if lower.startswith("/"):
        return value
    return ""


def _load_registered_qr_device(
    device_id: str,
    bed_location: str = "Kuwait",
    *,
    auto_create: bool = True,
) -> dict[str, Any]:
    normalized_id = str(device_id or "").strip()
    if not normalized_id:
        return {}
    from qr_code.generate_qr import load_registered_devices, register_device

    devices = load_registered_devices()
    for row in devices:
        if str(row.get("device_id", "")).strip() == normalized_id:
            return row
    if not auto_create:
        return {}
    register_device(normalized_id, bed_location=bed_location or "Kuwait")
    devices = load_registered_devices()
    for row in devices:
        if str(row.get("device_id", "")).strip() == normalized_id:
            return row
    return {}


def _normalize_alarm_time(value: Any) -> str:
    raw = str(value or "").strip()
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw):
        return raw
    return "07:00"


def _normalize_alarm_days(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    seen: set[int] = set()
    out: list[int] = []
    for item in values:
        try:
            day = int(item)
        except Exception:
            continue
        if day < 1 or day > 7:
            continue
        if day in seen:
            continue
        seen.add(day)
        out.append(day)
    out.sort()
    return out


def _alarm_next_trigger_utc(
    alarm_payload: dict[str, Any],
    *,
    timezone_name: str = "Asia/Kuwait",
    now_utc: datetime | None = None,
) -> str:
    alarm = alarm_payload if isinstance(alarm_payload, dict) else {}
    if not bool(alarm.get("enabled", True)):
        return ""

    hh_mm = _normalize_alarm_time(alarm.get("time"))
    hour = int(hh_mm[:2])
    minute = int(hh_mm[3:])
    days = _normalize_alarm_days(alarm.get("days", []))
    now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())

    tz_name = str(timezone_name or "").strip() or "Asia/Kuwait"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now_local = now.astimezone(tz)

    for offset in range(0, 8):
        date_local = (now_local + timedelta(days=offset)).date()
        if days and date_local.isoweekday() not in days:
            continue
        candidate_local = datetime(
            year=date_local.year,
            month=date_local.month,
            day=date_local.day,
            hour=hour,
            minute=minute,
            tzinfo=tz,
        )
        if candidate_local <= now_local:
            continue
        return to_iso(candidate_local.astimezone(timezone.utc).replace(microsecond=0))
    return ""


def _normalize_mobile_alarm(
    payload: dict[str, Any] | None,
    *,
    existing_alarm_id: str = "",
    now_iso: str = "",
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    alarm_id = str(data.get("alarm_id", "") or "").strip() or str(existing_alarm_id or "").strip()
    if not alarm_id:
        alarm_id = f"alarm_{secrets.token_hex(6)}"

    label = str(data.get("label", "") or "").strip()[:48]
    sound = str(data.get("sound", "default") or "default").strip()[:48]
    if not sound:
        sound = "default"

    return {
        "alarm_id": alarm_id,
        "time": _normalize_alarm_time(data.get("time", "07:00")),
        "days": _normalize_alarm_days(data.get("days", [])),
        "enabled": bool(data.get("enabled", True)),
        "label": label,
        "sound": sound,
        "vibrate": bool(data.get("vibrate", True)),
        "created_at": str(data.get("created_at", "") or "").strip() or (str(now_iso or "").strip() or _now_utc_iso()),
        "updated_at": str(now_iso or "").strip() or _now_utc_iso(),
    }


def _serialize_mobile_alarm_rows(
    rows: list[dict[str, Any]] | None,
    *,
    timezone_name: str = "Asia/Kuwait",
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    alarms = rows if isinstance(rows, list) else []
    serialized: list[dict[str, Any]] = []
    for row in alarms:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_mobile_alarm(
            row,
            existing_alarm_id=str(row.get("alarm_id", "") or ""),
            now_iso=str(row.get("updated_at", "") or _now_utc_iso()),
        )
        normalized["next_trigger_at_utc"] = _alarm_next_trigger_utc(
            normalized,
            timezone_name=timezone_name,
            now_utc=now_utc,
        )
        serialized.append(normalized)
    serialized.sort(key=lambda item: str(item.get("time", "23:59")))
    return serialized


def _sanitize_user_key(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "guest"
    safe = re.sub(r"[^a-z0-9._-]+", "_", raw).strip("._-")
    return (safe or "guest")[:80]


def _memory_store_for_user(user_key: str):
    """Return a DB-backed memory store if DB is available, else fall back to JSON."""
    safe_key = _sanitize_user_key(user_key)
    try:
        conn = _database_connection()
        return DBLongTermMemoryStore(user_id=safe_key, db_connection=conn)
    except Exception:
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
            "display_name": "",
            "timezone": "Asia/Kuwait",
            "push_enabled": True,
            "email_enabled": False,
            "location_mode": "auto",
            "country_code": "KW",
            "city": "",
            "theme_mode": "system",
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
    location = _profile_location_summary(profile_prefs)
    lines = [
        f"user_name={_resolved_user_display_name(user, profile_prefs)}",
        f"user_timezone={str(profile_prefs.get('timezone', 'Asia/Kuwait') or 'Asia/Kuwait').strip()}",
        f"user_location_mode={str(location.get('mode', 'auto') or 'auto')}",
        f"user_location_label={str(location.get('label', '') or '').strip()}",
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
    if location.get("city"):
        lines.append(f"user_city={str(location.get('city', '')).strip()}")
    if location.get("country_code"):
        lines.append(f"user_country_code={str(location.get('country_code', '')).strip()}")
    if location.get("latitude") is not None and location.get("longitude") is not None:
        lines.append(
            "user_coordinates="
            f"{float(location.get('latitude', 0.0)):.6f},"
            f"{float(location.get('longitude', 0.0)):.6f}"
        )
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
            "premium": False,
        },
        "focus_momentum": {
            "key": "focus_momentum",
            "label": "Focus Momentum",
            "summary": "Steady pulse scene for focused evenings.",
            "brightness": 0.45,
            "audio_profile": "focus_loop",
            "premium": True,
        },
        "discipline_night": {
            "key": "discipline_night",
            "label": "Discipline Night",
            "summary": "Blue wave pattern with low-distraction audio.",
            "brightness": 0.35,
            "audio_profile": "night_drive",
            "premium": True,
        },
        "balanced_default": {
            "key": "balanced_default",
            "label": "Balanced Default",
            "summary": "Neutral white scene for everyday comfort.",
            "brightness": 0.40,
            "audio_profile": "ambient_neutral",
            "premium": False,
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
                "premium": bool(row.get("premium", False)),
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


def _scene_store_snapshot() -> list[dict[str, Any]]:
    return deepcopy(scene_store.get_all_templates())


def _restore_scene_store_snapshot(previous_state: Any) -> bool:
    rows = previous_state if isinstance(previous_state, list) else None
    if rows is None:
        return False

    normalize_scene = getattr(scene_store, "_normalize_scene", None)
    save_state = getattr(scene_store, "_save_state", None)
    current_state = getattr(scene_store, "_state", None)
    if not callable(normalize_scene) or not callable(save_state) or not isinstance(current_state, dict):
        return False

    restored_scenes: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            restored_scenes.append(normalize_scene(row))

    scene_store._state = {
        "version": current_state.get("version", 1),
        "scenes": restored_scenes,
    }
    save_state()
    return True


def _undo_seconds_remaining(action: dict[str, Any]) -> int | None:
    expires_at = _parse_iso_timestamp(str(action.get("expires_at", "") or ""))
    if expires_at is None:
        return None
    remaining_seconds = (expires_at - utcnow()).total_seconds()
    if remaining_seconds <= 0:
        return None
    return int(math.ceil(remaining_seconds))


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
    resolved_settings = _resolved_user_settings(profile, user)
    override_limit_minutes = max(
        30,
        min(
            240,
            int(
                resolved_settings.get(
                    "quiet_hours_override_limit_minutes",
                    settings.quiet_hours_override_max_minutes or 120,
                )
                or (settings.quiet_hours_override_max_minutes or 120)
            ),
        ),
    )
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


_AUTOMATION_FRIENDLY_NAMES: dict[str, str] = {
    "sleep_time_suggestion": "Dana reminded you to prepare for sleep",
    "work_and_plan_10pm": "Dana prompted evening work review",
    "morning_wake_scene": "Dana activated your sunrise wake scene",
    "fajr_gentle_light": "Dana set gentle lights for Fajr prayer",
    "bedtime_drift_alert": "Dana noticed your bedtime is drifting",
    "hydration_prebed_reminder": "Dana reminded you to hydrate before bed",
    "circadian_evening_transition": "Dana shifted LEDs to evening mode",
    "stress_evening_checkin": "Dana offered breathing help for stress",
    "calendar_evening_brief": "Dana briefed you on tomorrow's schedule",
    "nap_suggestion": "Dana suggested a recovery nap",
    "weekly_health_report": "Dana generated your weekly health report",
    "hot_night_comfort": "Dana activated cool lighting for the heat",
    "rainy_night_comfort": "Dana set cozy warm scene for the rain",
}


def _automation_cooldown_timeline_items(now_utc: datetime | None = None) -> list[dict[str, Any]]:
    registry = AutomationRegistry(state_path=AUTOMATION_STATE_PATH)
    for automation in build_default_automations():
        registry.register(automation)

    statuses = registry.cooldown_status(now_utc=now_utc)
    rows: list[dict[str, Any]] = []
    for row in statuses:
        raw_name = str(row.get("name", "automation") or "automation")
        friendly = _AUTOMATION_FRIENDLY_NAMES.get(raw_name, raw_name.replace("_", " ").title())
        remaining = max(0, int(row.get("next_run_in_minutes", 0) or 0))
        if remaining > 0:
            rows.append(
                {
                    "time": f"in {remaining} min",
                    "event": f"{friendly} · next: in {remaining} min",
                    "status": "cooldown",
                }
            )
        else:
            rows.append(
                {
                    "time": "Now",
                    "event": f"{friendly} · ready",
                    "status": "ready",
                }
            )
    return rows[:8]


def _timeline_priority_score(row: dict[str, Any] | None) -> int:
    data = row if isinstance(row, dict) else {}
    status = str(data.get("status", "active") or "active").strip().lower()
    event = str(data.get("event", "") or "").strip().lower()
    command_id = str(data.get("command_id", "") or "").strip()

    base = {
        "failed": 95,
        "danger": 95,
        "error": 95,
        "quiet": 96,
        "cooldown": 90,
        "override": 88,
        "review": 84,
        "queued": 82,
        "running": 76,
        "active": 74,
        "completed": 62,
        "ready": 60,
        "available": 42,
        "info": 42,
    }.get(status, 50)

    if "predictive alert" in event:
        base += 20
    if "quiet hours" in event:
        base += 16
    if "wind-down" in event:
        base += 12
    if ("failed" in event) or ("error" in event):
        base += 24
    if command_id:
        base += 4

    return max(0, min(100, int(base)))


def _normalize_timeline_items(items: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    source = items if isinstance(items, list) else []
    for row in source:
        if not isinstance(row, dict):
            continue
        raw_priority = row.get("priority", None)
        try:
            parsed_priority = int(raw_priority) if raw_priority is not None else None
        except Exception:
            parsed_priority = None
        priority = (
            max(0, min(100, parsed_priority))
            if isinstance(parsed_priority, int)
            else _timeline_priority_score(row)
        )
        out.append(
            {
                "time": str(row.get("time", "Anytime") or "Anytime"),
                "event": str(row.get("event", "Timeline event") or "Timeline event"),
                "status": str(row.get("status", "active") or "active"),
                "command_id": str(row.get("command_id", "") or ""),
                "priority": int(priority),
            }
        )
    return out[:20]


def _timeline_item_signature(item: dict[str, Any]) -> str:
    row = _normalize_timeline_items([item])[0]
    return "|".join(
        [
            str(row.get("command_id", "") or ""),
            str(row.get("event", "") or "").strip().lower(),
            str(row.get("status", "") or "").strip().lower(),
            str(row.get("time", "") or "").strip().lower(),
        ]
    )


def _with_min_timeline_priority(item: dict[str, Any] | None, minimum: int) -> dict[str, Any]:
    row = dict(item) if isinstance(item, dict) else {}
    try:
        existing = int(row.get("priority", 0) or 0)
    except Exception:
        existing = 0
    row["priority"] = max(existing, int(minimum))
    return row


def _is_runtime_status_row(row: dict[str, Any]) -> bool:
    event = str(row.get("event", "") or "").strip().lower()
    if not event:
        return False
    if event.startswith("quiet hours active"):
        return True
    if event.startswith("quiet hours override active"):
        return True
    if event.startswith("quiet hours override enabled"):
        return True
    if ": next run available in " in event:
        return True
    if event.endswith(": available now"):
        return True
    return False


def _strip_runtime_status_rows(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = _normalize_timeline_items(items)
    out: list[dict[str, Any]] = []
    for row in normalized:
        # Keep explicit command-linked rows; only prune synthesized runtime status rows.
        if str(row.get("command_id", "") or "").strip():
            out.append(row)
            continue
        if _is_runtime_status_row(row):
            continue
        out.append(row)
    return out


def _merge_timeline_items(
    primary: list[dict[str, Any]] | None,
    secondary: list[dict[str, Any]] | None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in (_normalize_timeline_items(primary), _normalize_timeline_items(secondary)):
        for row in source:
            signature = _timeline_item_signature(row)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(row)
            if len(merged) >= max(1, int(limit or 20)):
                return merged
    return merged


def _prioritize_timeline_items(
    items: list[dict[str, Any]] | None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    normalized = _normalize_timeline_items(items)
    ranked = sorted(
        enumerate(normalized),
        key=lambda pair: (
            -max(0, int((pair[1] or {}).get("priority", 0) or 0)),
            pair[0],
        ),
    )
    safe_limit = max(1, int(limit or 20))
    return [row for _, row in ranked][:safe_limit]


def _persist_mobile_timeline_item(user_id: str, item: dict[str, Any], trace_id: str = "") -> None:
    user_key = str(user_id or "").strip()
    if not user_key:
        return
    normalized = _normalize_timeline_items([item])
    if not normalized:
        return
    payload = dict(normalized[0])
    payload["captured_at_utc"] = _now_utc_iso()
    trace = str(trace_id or "").strip() or "web_runtime"
    try:
        _db_event_repository().log_event(
            user_id=user_key,
            event_type="mobile_timeline_item",
            metadata=payload,
            trace_id=trace,
        )
    except Exception as exc:
        if type(exc).__name__ == "IntegrityError":
            try:
                _ensure_db_user_shadow({"user_id": user_key})
                _db_event_repository().log_event(
                    user_id=user_key,
                    event_type="mobile_timeline_item",
                    metadata=payload,
                    trace_id=trace,
                )
                return
            except Exception as _retry_exc:
                logger.warning("timeline_item retry failed user_id=%s err=%s", user_key, _retry_exc)
        emit_json_log(
            logger,
            level="warning",
            event_type="mobile_timeline_db_write_failed",
            trace_id=trace,
            user_id=user_key,
            metadata={"error_type": type(exc).__name__},
        )


def _mobile_timeline_items_from_db(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return []
    safe_limit = max(1, min(int(limit or 20), 60))
    try:
        events = _db_event_repository().get_events_by_user(user_key, limit=max(40, safe_limit * 3))
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="mobile_timeline_db_read_failed",
            trace_id="web_runtime",
            user_id=user_key,
            metadata={"error_type": type(exc).__name__},
        )
        return []

    out: list[dict[str, Any]] = []
    for event in events:
        if str(getattr(event, "event_type", "") or "").strip().lower() != "mobile_timeline_item":
            continue
        metadata = event.metadata_json if isinstance(event.metadata_json, dict) else {}
        if not metadata:
            continue
        fallback_time = "Anytime"
        timestamp = getattr(event, "timestamp", None)
        if isinstance(timestamp, datetime):
            fallback_time = ensure_utc(timestamp).strftime("%H:%M")
        out.append(
            {
                "time": str(metadata.get("time", fallback_time) or fallback_time),
                "event": str(metadata.get("event", "Timeline event") or "Timeline event"),
                "status": str(metadata.get("status", "active") or "active"),
                "command_id": str(metadata.get("command_id", "") or ""),
                "priority": metadata.get("priority", 0),
            }
        )
        if len(out) >= safe_limit:
            break
    return _normalize_timeline_items(out)[:safe_limit]


def _persist_mobile_timeline_snapshot(user_id: str, items: list[dict[str, Any]] | None, trace_id: str = "") -> None:
    user_key = str(user_id or "").strip()
    if not user_key:
        return
    for row in _normalize_timeline_items(items if isinstance(items, list) else []):
        _persist_mobile_timeline_item(user_id=user_key, item=row, trace_id=trace_id)


def _mobile_timeline_items_db_first(
    user_id: str,
    profile_items: list[Any] | None,
    *,
    trace_id: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    user_key = str(user_id or "").strip()
    safe_limit = max(1, min(int(limit or 20), 60))
    normalized_profile = _normalize_timeline_items(profile_items if isinstance(profile_items, list) else [])[:safe_limit]
    if not user_key:
        return normalized_profile

    db_items = _strip_runtime_status_rows(_mobile_timeline_items_from_db(user_key, limit=safe_limit))
    if db_items:
        return _merge_timeline_items(db_items, normalized_profile, limit=safe_limit)

    if normalized_profile:
        _persist_mobile_timeline_snapshot(user_key, normalized_profile, trace_id=trace_id)
        refreshed_db_items = _strip_runtime_status_rows(_mobile_timeline_items_from_db(user_key, limit=safe_limit))
        if refreshed_db_items:
            return _merge_timeline_items(refreshed_db_items, normalized_profile, limit=safe_limit)
    return normalized_profile


def _restore_mobile_db_snapshots_from_profile(
    *,
    user_id: str,
    profile_key: str,
    profile_state: dict[str, Any],
    trace_id: str = "",
) -> None:
    user_key = str(user_id or "").strip()
    scoped_key = str(profile_key or "").strip()
    if (not user_key) or (not scoped_key):
        return

    try:
        command_section = _get_scoped_profile_section(profile_state, "web_device_commands")
        command_rows = (
            command_section.get(scoped_key, [])
            if isinstance(command_section.get(scoped_key, []), list)
            else []
        )
        normalized_commands = [
            _normalize_command_item(row) for row in command_rows if isinstance(row, dict)
        ]
        _db_command_repository().replace_user_commands(
            user_key,
            normalized_commands,
            now_utc=utcnow(),
        )

        timeline_section = _get_scoped_profile_section(profile_state, "web_timeline")
        timeline_rows = (
            timeline_section.get(scoped_key, [])
            if isinstance(timeline_section.get(scoped_key, []), list)
            else []
        )
        normalized_timeline = _normalize_timeline_items(timeline_rows)[:20]
        _db_event_repository().replace_mobile_timeline_events(
            user_key,
            normalized_timeline,
            trace_id=trace_id,
            now_utc=utcnow(),
        )
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="mobile_undo_db_restore_failed",
            trace_id=str(trace_id or "web_runtime"),
            user_id=user_key,
            metadata={"error_type": type(exc).__name__},
        )


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


def _progress_user_commands(profile: dict[str, Any], key: str, user_id: str = "") -> tuple[list[dict[str, Any]], bool]:
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
    if changed_any:
        _persist_mobile_commands_snapshot(user_id or key, out)
    return out[:60], changed_any


def _command_timestamp_utc(command: dict[str, Any], fallback_now: datetime) -> datetime:
    for key in ("completed_at", "updated_at", "created_at"):
        parsed = _parse_iso_timestamp(str(command.get(key, "") or ""))
        if parsed is not None:
            return ensure_utc(parsed)
    return ensure_utc(fallback_now)


def _persist_mobile_command_record(user_id: str, command: dict[str, Any]) -> None:
    user_key = str(user_id or "").strip()
    if not user_key:
        return
    normalized = _normalize_command_item(command if isinstance(command, dict) else {})
    command_id = str(normalized.get("id", "") or "").strip()
    if not command_id:
        return
    try:
        _db_command_repository().upsert_command(user_key, normalized)
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="mobile_command_db_write_failed",
            trace_id=str(normalized.get("trace_id", "") or "web_runtime"),
            user_id=user_key,
            metadata={"error_type": type(exc).__name__, "command_id": command_id},
        )


def _persist_mobile_commands_snapshot(user_id: str, commands: list[dict[str, Any]]) -> None:
    user_key = str(user_id or "").strip()
    if not user_key:
        return
    for row in commands if isinstance(commands, list) else []:
        if isinstance(row, dict):
            _persist_mobile_command_record(user_key, row)


def _command_metrics_7d_from_db(user_id: str, now_utc: datetime) -> dict[str, int] | None:
    user_key = str(user_id or "").strip()
    if not user_key:
        return None
    try:
        metrics = _db_command_repository().command_metrics_window(
            user_key,
            now_utc=ensure_utc(now_utc),
            window_days=7,
        )
        total = max(0, int(metrics.get("total", 0) or 0))
        completed = max(0, int(metrics.get("completed", 0) or 0))
        completion_rate_pct = max(0, min(100, int(metrics.get("completion_rate_pct", 0) or 0)))
        return {
            "total": total,
            "completed": completed,
            "completion_rate_pct": completion_rate_pct,
        }
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="mobile_command_db_read_failed",
            trace_id="web_runtime",
            user_id=user_key,
            metadata={"error_type": type(exc).__name__},
        )
        return None


def _winddown_sessions_7d_from_db(user_id: str, now_utc: datetime) -> int | None:
    user_key = str(user_id or "").strip()
    if not user_key:
        return None
    now = ensure_utc(now_utc)
    week_start_date = (now - timedelta(days=7)).date()
    try:
        sessions = _db_sleep_session_repository().get_recent_sessions(user_key, limit=14)
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="sleep_sessions_db_read_failed",
            trace_id="web_runtime",
            user_id=user_key,
            metadata={"error_type": type(exc).__name__},
        )
        return None

    total = 0
    for row in sessions:
        session_date = getattr(row, "date", None)
        if session_date is None or session_date < week_start_date:
            continue
        try:
            total += max(0, int(getattr(row, "winddowns_completed", 0) or 0))
        except Exception:
            continue
    return total


def _record_winddown_session_to_db(user_id: str, started_at_utc: datetime) -> None:
    user_key = str(user_id or "").strip()
    if not user_key:
        return
    started_at = ensure_utc(started_at_utc)
    _ensure_db_user_shadow({"user_id": user_key})
    target_date = started_at.date()
    try:
        repo = _db_sleep_session_repository()
        current = repo.get_session_by_date(user_key, target_date)
        current_count = 0
        if current is not None:
            try:
                current_count = max(0, int(getattr(current, "winddowns_completed", 0) or 0))
            except Exception:
                current_count = 0
        repo.create_or_update_session(
            user_id=user_key,
            date=target_date,
            bedtime=getattr(current, "bedtime", None) or started_at,
            winddowns_completed=current_count + 1,
        )
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="sleep_session_db_write_failed",
            trace_id="web_runtime",
            user_id=user_key,
            metadata={"error_type": type(exc).__name__},
        )


def _weekly_insight_payload(
    commands: list[dict[str, Any]] | None,
    *,
    user_id: str = "",
    now_utc: datetime | None = None,
    wind_down_minutes: int = 45,
    weekly_insight_enabled: bool = True,
    nightly_feedback: dict[str, Any] | None = None,
    command_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now_utc if isinstance(now_utc, datetime) else utcnow()
    now = ensure_utc(now)
    week_start = now - timedelta(days=7)

    normalized = [
        _normalize_command_item(row if isinstance(row, dict) else {})
        for row in (commands if isinstance(commands, list) else [])
    ]
    recent: list[dict[str, Any]] = []
    for row in normalized:
        ts = _command_timestamp_utc(row, now)
        if ts >= week_start:
            recent.append(row)

    action_count = len(recent)
    completed_count = sum(
        1
        for row in recent
        if str(row.get("status", "queued") or "queued").strip().lower() == "completed"
    )
    wind_down_rows = [
        row
        for row in recent
        if str(row.get("action", "") or "").strip().lower() == "winddown"
    ]
    wind_down_sessions = len(wind_down_rows)
    wind_down_completed = sum(
        1
        for row in wind_down_rows
        if str(row.get("status", "queued") or "queued").strip().lower() == "completed"
    )
    db_wind_down_sessions = _winddown_sessions_7d_from_db(user_id, now) if user_id else None
    if isinstance(db_wind_down_sessions, int):
        wind_down_sessions = max(0, db_wind_down_sessions)
        wind_down_completed = max(0, db_wind_down_sessions)
    quiet_overrides = sum(
        1
        for row in recent
        if str(row.get("action", "") or "").strip().lower() == "quiet_hours_override"
    )
    completion_rate_pct = int(round((completed_count / action_count) * 100.0)) if action_count > 0 else 0
    nightly_feedback_row = nightly_feedback if isinstance(nightly_feedback, dict) else {}
    command_feedback_row = command_feedback if isinstance(command_feedback, dict) else {}
    nightly_votes = max(0, int(nightly_feedback_row.get("total_votes", 0) or 0))
    nightly_helpful_pct = max(0, min(100, int(nightly_feedback_row.get("helpful_pct", 0) or 0)))
    command_votes = max(0, int(command_feedback_row.get("total_votes", 0) or 0))
    command_helpful_pct = max(0, min(100, int(command_feedback_row.get("helpful_pct", 0) or 0)))
    feedback_total_votes = nightly_votes + command_votes
    feedback_helpful_pct = (
        int(
            round(
                (
                    (nightly_helpful_pct * nightly_votes)
                    + (command_helpful_pct * command_votes)
                )
                / feedback_total_votes
            )
        )
        if feedback_total_votes > 0
        else 0
    )

    if not weekly_insight_enabled:
        trend = "paused"
        headline = "Weekly insight paused"
        summary = "Enable weekly insight in Settings to resume habit-loop coaching."
    elif feedback_total_votes >= 3 and feedback_helpful_pct < 50:
        trend = "attention"
        headline = "Feedback trend shows friction this week"
        summary = (
            f"Only {feedback_helpful_pct}% helpful feedback across {feedback_total_votes} vote(s). "
            "Run one clean wind-down tonight, avoid override noise, and review the timeline tomorrow."
        )
    elif wind_down_completed <= 0:
        trend = "attention"
        headline = "No completed wind-down sessions this week"
        summary = (
            f"Start wind-down tonight and aim for {int(wind_down_minutes)} minutes "
            "to begin your consistency streak."
        )
    elif (
        completion_rate_pct >= 80
        and feedback_total_votes >= 3
        and feedback_helpful_pct >= 75
    ):
        trend = "up"
        headline = "Feedback trend confirms your nightly loop is working"
        summary = (
            f"{feedback_helpful_pct}% helpful feedback across {feedback_total_votes} vote(s). "
            "Keep the same bedtime window and repeat tonight's winning routine."
        )
    elif completion_rate_pct >= 80:
        trend = "up"
        headline = f"{wind_down_completed} wind-down session(s) completed this week"
        summary = "Strong momentum. Keep bedtime timing stable for better next-day energy."
    else:
        trend = "steady"
        headline = f"{wind_down_completed} wind-down session(s) completed this week"
        if feedback_total_votes >= 2 and feedback_helpful_pct < 70:
            summary = (
                f"Consistency is building, but feedback is mixed ({feedback_helpful_pct}% helpful). "
                "Keep wind-down timing stable and simplify any noisy automation."
            )
        else:
            summary = (
                "Consistency is building. Repeat your wind-down at a similar time tonight "
                "to improve recovery."
            )

    return {
        "window_days": 7,
        "wind_down_sessions": wind_down_sessions,
        "completed_actions": completed_count,
        "automation_actions": action_count,
        "quiet_overrides": quiet_overrides,
        "completion_rate_pct": completion_rate_pct,
        "feedback_total_votes": feedback_total_votes,
        "feedback_helpful_pct": feedback_helpful_pct,
        "trend": trend,
        "headline": headline,
        "summary": summary,
    }


def _sleep_engine_now(now_utc: datetime | None = None) -> datetime:
    now = now_utc if isinstance(now_utc, datetime) else utcnow()
    now = ensure_utc(now)
    # The sleep intelligence engine uses local-style hour/date gates, so we
    # pass a naive UTC snapshot for deterministic API behavior.
    return now.replace(tzinfo=None)


def _nightly_summary_payload(
    profile: dict[str, Any],
    *,
    weekly_insight: dict[str, Any],
    last_command_result: dict[str, Any] | None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    _SLEEP_ENGINE.ensure_shape(profile)
    quality_line = _SLEEP_ENGINE.sleep_quality_score(profile)
    consistency_line = _SLEEP_ENGINE.sleep_consistency_score(profile)
    recovery_plan_line = _SLEEP_ENGINE.sleep_debt_recovery_plan(profile)
    focus_line = "No command executed yet tonight. Start with wind-down."
    if isinstance(last_command_result, dict):
        summary = str(last_command_result.get("summary", "") or "").strip()
        action = str(last_command_result.get("action", "") or "").strip().replace("_", " ")
        if summary:
            focus_line = f"Latest command: {summary}"
        elif action:
            focus_line = f"Latest command action: {action}"
    trend = str(weekly_insight.get("trend", "steady") or "steady").strip().lower()
    trend_title = {
        "up": "Momentum is improving",
        "attention": "Drift risk detected",
        "steady": "Steady progress",
        "paused": "Insights paused",
    }.get(trend, "Steady progress")
    return {
        "headline": "Tonight's sleep summary",
        "trend_title": trend_title,
        "focus_line": focus_line,
        "sleep_quality_line": quality_line,
        "consistency_line": consistency_line,
        "recovery_plan_line": recovery_plan_line,
        "generated_at_utc": to_iso(ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())),
    }


_FIRST_3_NIGHTS_STEP_FIELDS = {
    "signup": "signup_completed_at_utc",
    "first_scene_preview": "first_scene_preview_completed_at_utc",
    "first_automation": "first_automation_completed_at_utc",
    "first_winddown": "first_winddown_completed_at_utc",
    "timeline_review": "timeline_review_completed_at_utc",
}

_FIRST_3_NIGHTS_STEP_DEFINITIONS = (
    {
        "key": "signup",
        "label": "Create mobile access",
        "description": "Sign up and sign in from the mobile app.",
    },
    {
        "key": "first_scene_preview",
        "label": "Preview first scene",
        "description": "Run one scene preview and confirm the mood fit.",
    },
    {
        "key": "first_automation",
        "label": "Trigger first automation",
        "description": "Use one quick action from the command center.",
    },
    {
        "key": "first_winddown",
        "label": "Start wind-down",
        "description": "Run wind-down once so bedtime habit tracking begins.",
    },
    {
        "key": "timeline_review",
        "label": "Review timeline",
        "description": "Open timeline the next day and review what happened.",
    },
)


def _normalize_first_3_nights_state(row: dict[str, Any] | None) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {}
    out: dict[str, Any] = {}
    for field in _FIRST_3_NIGHTS_STEP_FIELDS.values():
        out[field] = str(data.get(field, "") or "").strip()
    out["created_at_utc"] = str(data.get("created_at_utc", "") or "").strip()
    out["updated_at_utc"] = str(data.get("updated_at_utc", "") or "").strip()
    return out


def _mark_first_3_nights_step(state: dict[str, Any], step_key: str, now_iso: str) -> bool:
    field = _FIRST_3_NIGHTS_STEP_FIELDS.get(str(step_key or "").strip(), "")
    if not field:
        return False
    if str(state.get(field, "") or "").strip():
        return False
    state[field] = now_iso
    return True


def _first_3_nights_payload(state: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_first_3_nights_state(state)
    steps: list[dict[str, Any]] = []
    completed_steps = 0
    next_step_key = ""

    for meta in _FIRST_3_NIGHTS_STEP_DEFINITIONS:
        key = str(meta.get("key", "") or "")
        field = _FIRST_3_NIGHTS_STEP_FIELDS.get(key, "")
        completed_at = str(normalized.get(field, "") or "").strip()
        completed = bool(completed_at)
        if completed:
            completed_steps += 1
        elif not next_step_key:
            next_step_key = key
        steps.append(
            {
                "key": key,
                "label": str(meta.get("label", "Step") or "Step"),
                "description": str(meta.get("description", "") or ""),
                "completed": completed,
                "completed_at_utc": completed_at,
            }
        )

    total_steps = len(_FIRST_3_NIGHTS_STEP_DEFINITIONS)
    progress_pct = int(round((completed_steps / total_steps) * 100.0)) if total_steps > 0 else 0
    return {
        "title": "First 3 Nights",
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "progress_pct": progress_pct,
        "is_complete": bool(completed_steps >= total_steps and total_steps > 0),
        "next_step_key": next_step_key,
        "steps": steps,
    }


def _has_scene_preview_for_user(profile: dict[str, Any], key: str) -> bool:
    preview_section = _get_scoped_profile_section(profile, "web_scene_preview")
    preview_row = preview_section.get(key, {}) if key else {}
    if isinstance(preview_row, dict) and str(preview_row.get("scene_key", "") or "").strip():
        return True

    timeline_section = _get_scoped_profile_section(profile, "web_timeline")
    rows = timeline_section.get(key, []) if isinstance(timeline_section.get(key, []), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        event = str(row.get("event", "") or "").strip().lower()
        if "scene preview" in event or "scene saved for tonight" in event:
            return True
    return False


def _commands_for_user(
    profile: dict[str, Any],
    key: str,
    *,
    commands: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(commands, list):
        return [_normalize_command_item(row if isinstance(row, dict) else {}) for row in commands]

    cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
    raw = cmd_section.get(key, []) if isinstance(cmd_section.get(key, []), list) else []
    return [_normalize_command_item(row if isinstance(row, dict) else {}) for row in raw]


def _sync_first_3_nights_state(
    profile: dict[str, Any],
    user: dict[str, Any],
    *,
    commands: list[dict[str, Any]] | None = None,
    mark_step_key: str = "",
    now_utc: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    key = _user_profile_key(user)
    if not key:
        return _first_3_nights_payload(_normalize_first_3_nights_state({})), False

    now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
    normalized_commands = _commands_for_user(profile, key, commands=commands)
    step_keys: list[str] = ["signup"]
    if _has_scene_preview_for_user(profile, key):
        step_keys.append("first_scene_preview")
    if any(str(cmd.get("action", "") or "").strip().lower() for cmd in normalized_commands):
        step_keys.append("first_automation")
    has_winddown_command = any(
        str(cmd.get("action", "") or "").strip().lower() == "winddown"
        for cmd in normalized_commands
    )
    sleep = profile.get("sleep", {}) if isinstance(profile.get("sleep", {}), dict) else {}
    if has_winddown_command or str(sleep.get("wind_down_started_at_utc", "") or "").strip():
        step_keys.append("first_winddown")
    if mark_step_key:
        step_keys.append(mark_step_key)

    try:
        repo = _db_beta_progress_repository()
        state, changed = repo.sync_first_three_nights_steps(
            user_id=key,
            step_keys=step_keys,
            now_utc=now,
        )
        return _first_3_nights_payload(_normalize_first_3_nights_state(state)), changed
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="first_3_nights_db_unavailable",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )

    # Fallback path keeps app flow alive if DB is temporarily unavailable.
    now_iso = to_iso(now)
    section = _get_scoped_profile_section(profile, "web_first_3_nights")
    state = _normalize_first_3_nights_state(section.get(key, {}))
    changed = False
    for step_key in step_keys:
        if _mark_first_3_nights_step(state, step_key, now_iso):
            changed = True
    if not str(state.get("created_at_utc", "") or "").strip():
        state["created_at_utc"] = now_iso
        changed = True
    if changed:
        state["updated_at_utc"] = now_iso
        section[key] = state
        profile["web_first_3_nights"] = section
    return _first_3_nights_payload(state), changed


def _normalize_nightly_summary_feedback(row: dict[str, Any] | None) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {}
    try:
        helpful_count = int(data.get("helpful_count", 0) or 0)
    except Exception:
        helpful_count = 0
    try:
        not_helpful_count = int(data.get("not_helpful_count", 0) or 0)
    except Exception:
        not_helpful_count = 0
    helpful_count = max(0, helpful_count)
    not_helpful_count = max(0, not_helpful_count)
    last_vote = str(data.get("last_vote", "") or "").strip().lower()
    if last_vote not in {"helpful", "not_helpful"}:
        last_vote = ""
    return {
        "helpful_count": helpful_count,
        "not_helpful_count": not_helpful_count,
        "last_vote": last_vote,
        "last_vote_at_utc": str(data.get("last_vote_at_utc", "") or "").strip(),
        "last_summary_generated_at_utc": str(data.get("last_summary_generated_at_utc", "") or "").strip(),
    }


def _nightly_summary_feedback_payload(row: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_nightly_summary_feedback(row)
    helpful_count = int(normalized.get("helpful_count", 0) or 0)
    not_helpful_count = int(normalized.get("not_helpful_count", 0) or 0)
    total_votes = helpful_count + not_helpful_count
    helpful_pct = int(round((helpful_count / total_votes) * 100.0)) if total_votes > 0 else 0
    return {
        "helpful_count": helpful_count,
        "not_helpful_count": not_helpful_count,
        "total_votes": total_votes,
        "helpful_pct": helpful_pct,
        "last_vote": str(normalized.get("last_vote", "") or ""),
        "last_vote_at_utc": str(normalized.get("last_vote_at_utc", "") or ""),
    }


def _nightly_summary_feedback_for_user(profile: dict[str, Any], key: str) -> dict[str, Any]:
    if not key:
        return _normalize_nightly_summary_feedback({})
    try:
        repo = _db_beta_progress_repository()
        row = repo.get_nightly_summary_feedback(key)
        return _normalize_nightly_summary_feedback(row if isinstance(row, dict) else {})
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="nightly_feedback_db_unavailable",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )
    section = _get_scoped_profile_section(profile, "web_nightly_summary_feedback")
    row = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    return _normalize_nightly_summary_feedback(row if isinstance(row, dict) else {})


def _record_nightly_summary_feedback(
    profile: dict[str, Any],
    key: str,
    *,
    vote: str,
    summary_generated_at_utc: str = "",
    now_utc: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    if not key:
        return _nightly_summary_feedback_payload(_normalize_nightly_summary_feedback({})), False

    normalized_vote = str(vote or "").strip().lower()
    if normalized_vote not in {"helpful", "not_helpful"}:
        return _nightly_summary_feedback_payload(_normalize_nightly_summary_feedback({})), False

    now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
    summary_marker = str(summary_generated_at_utc or "").strip()
    try:
        repo = _db_beta_progress_repository()
        state, changed = repo.record_nightly_summary_feedback(
            key,
            vote=normalized_vote,
            summary_generated_at_utc=summary_marker,
            now_utc=now,
        )
        return _nightly_summary_feedback_payload(_normalize_nightly_summary_feedback(state)), changed
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="nightly_feedback_db_write_failed",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )

    section = _get_scoped_profile_section(profile, "web_nightly_summary_feedback")
    state = _normalize_nightly_summary_feedback(section.get(key, {}))
    duplicate_vote = (
        bool(summary_marker)
        and str(state.get("last_summary_generated_at_utc", "") or "").strip() == summary_marker
        and str(state.get("last_vote", "") or "").strip().lower() == normalized_vote
    )

    if not duplicate_vote:
        target_key = "helpful_count" if normalized_vote == "helpful" else "not_helpful_count"
        state[target_key] = int(state.get(target_key, 0) or 0) + 1

    state["last_vote"] = normalized_vote
    state["last_vote_at_utc"] = to_iso(now)
    if summary_marker:
        state["last_summary_generated_at_utc"] = summary_marker

    section[key] = state
    profile["web_nightly_summary_feedback"] = section
    return _nightly_summary_feedback_payload(state), True


def _normalize_command_feedback_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {}
    try:
        helpful_count = int(data.get("helpful_count", 0) or 0)
    except Exception:
        helpful_count = 0
    try:
        not_helpful_count = int(data.get("not_helpful_count", 0) or 0)
    except Exception:
        not_helpful_count = 0
    helpful_count = max(0, helpful_count)
    not_helpful_count = max(0, not_helpful_count)
    last_vote = str(data.get("last_vote", "") or "").strip().lower()
    if last_vote not in {"helpful", "not_helpful"}:
        last_vote = ""
    return {
        "helpful_count": helpful_count,
        "not_helpful_count": not_helpful_count,
        "last_vote": last_vote,
        "last_vote_at_utc": str(data.get("last_vote_at_utc", "") or "").strip(),
        "last_command_id": str(data.get("last_command_id", "") or "").strip(),
        "last_command_action": str(data.get("last_command_action", "") or "").strip().lower(),
    }


def _command_feedback_payload(row: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_command_feedback_summary(row)
    helpful_count = int(normalized.get("helpful_count", 0) or 0)
    not_helpful_count = int(normalized.get("not_helpful_count", 0) or 0)
    total_votes = helpful_count + not_helpful_count
    helpful_pct = int(round((helpful_count / total_votes) * 100.0)) if total_votes > 0 else 0
    if total_votes <= 0:
        status_line = "No command feedback yet. Rate your latest automation to tune reliability."
    elif helpful_pct >= 70:
        status_line = "Automation feedback is strong. Keep repeating this routine."
    elif helpful_pct >= 40:
        status_line = "Automation feedback is mixed. Keep tuning timing and scene choice."
    else:
        status_line = "Automation feedback needs attention. Focus on reliability before adding features."
    return {
        "helpful_count": helpful_count,
        "not_helpful_count": not_helpful_count,
        "total_votes": total_votes,
        "helpful_pct": helpful_pct,
        "last_vote": str(normalized.get("last_vote", "") or ""),
        "last_vote_at_utc": str(normalized.get("last_vote_at_utc", "") or ""),
        "last_command_id": str(normalized.get("last_command_id", "") or ""),
        "last_command_action": str(normalized.get("last_command_action", "") or ""),
        "status_line": status_line,
    }


def _command_feedback_summary_from_profile(profile: dict[str, Any], key: str) -> dict[str, Any]:
    section = _get_scoped_profile_section(profile, "web_command_feedback")
    rows = section.get(key, {}) if key else {}
    if not isinstance(rows, dict):
        rows = {}
    helpful_count = 0
    not_helpful_count = 0
    latest_vote = ""
    latest_vote_at = ""
    latest_command_id = ""
    latest_command_action = ""
    latest_ts = float("-inf")

    for command_id, raw_row in rows.items():
        row = raw_row if isinstance(raw_row, dict) else {}
        vote = str(row.get("vote", "") or "").strip().lower()
        if vote == "helpful":
            helpful_count += 1
        elif vote == "not_helpful":
            not_helpful_count += 1
        else:
            continue
        ts_raw = str(row.get("voted_at_utc", "") or "").strip()
        ts = _parse_iso_timestamp(ts_raw)
        if isinstance(ts, datetime):
            ts_value = ensure_utc(ts).timestamp()
        else:
            ts_value = float("-inf")
        if ts_value >= latest_ts:
            latest_ts = ts_value
            latest_vote = vote
            latest_vote_at = ts_raw
            latest_command_id = str(command_id or "").strip()
            latest_command_action = str(row.get("action", "") or "").strip().lower()

    return _normalize_command_feedback_summary(
        {
            "helpful_count": helpful_count,
            "not_helpful_count": not_helpful_count,
            "last_vote": latest_vote,
            "last_vote_at_utc": latest_vote_at,
            "last_command_id": latest_command_id,
            "last_command_action": latest_command_action,
        }
    )


def _command_feedback_for_user(profile: dict[str, Any], key: str) -> dict[str, Any]:
    if not key:
        return _normalize_command_feedback_summary({})
    try:
        row = _db_command_repository().command_feedback_summary_window(
            key,
            window_days=30,
        )
        return _normalize_command_feedback_summary(row if isinstance(row, dict) else {})
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="command_feedback_db_unavailable",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )
    return _command_feedback_summary_from_profile(profile, key)


def _record_command_feedback(
    profile: dict[str, Any],
    key: str,
    *,
    command_id: str,
    command_action: str = "",
    vote: str,
    note: str = "",
    trace_id: str = "",
    now_utc: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    if not key:
        return _command_feedback_payload(_normalize_command_feedback_summary({})), False

    command_key = str(command_id or "").strip()
    normalized_vote = str(vote or "").strip().lower()
    if (not command_key) or (normalized_vote not in {"helpful", "not_helpful"}):
        return _command_feedback_payload(_normalize_command_feedback_summary({})), False

    now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
    normalized_action = str(command_action or "").strip().lower()
    normalized_note = str(note or "").strip()
    if len(normalized_note) > 240:
        normalized_note = normalized_note[:240]
    trace = str(trace_id or "").strip()

    try:
        state, changed = _db_command_repository().record_command_feedback(
            key,
            command_id=command_key,
            vote=normalized_vote,
            command_action=normalized_action,
            note=normalized_note,
            trace_id=trace,
            now_utc=now,
            window_days=30,
        )
        return _command_feedback_payload(_normalize_command_feedback_summary(state)), changed
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="command_feedback_db_write_failed",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )

    section = _get_scoped_profile_section(profile, "web_command_feedback")
    rows = section.get(key, {}) if isinstance(section.get(key, {}), dict) else {}
    previous = rows.get(command_key, {}) if isinstance(rows.get(command_key, {}), dict) else {}
    previous_vote = str(previous.get("vote", "") or "").strip().lower()
    previous_note = str(previous.get("note", "") or "").strip()
    changed = bool(previous_vote != normalized_vote or previous_note != normalized_note)
    rows[command_key] = {
        "vote": normalized_vote,
        "note": normalized_note,
        "action": normalized_action,
        "trace_id": trace,
        "voted_at_utc": to_iso(now),
    }
    section[key] = rows
    profile["web_command_feedback"] = section
    state = _command_feedback_summary_from_profile(profile, key)
    return _command_feedback_payload(state), changed


def _beta_metrics_payload(
    *,
    checklist: dict[str, Any],
    commands: list[dict[str, Any]],
    feedback: dict[str, Any],
    command_feedback: dict[str, Any] | None = None,
    user_id: str = "",
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
    week_start = now - timedelta(days=7)
    normalized_commands = [_normalize_command_item(row if isinstance(row, dict) else {}) for row in commands]

    recent_commands: list[dict[str, Any]] = []
    for row in normalized_commands:
        ts = _command_timestamp_utc(row, now)
        if ts >= week_start:
            recent_commands.append(row)

    command_total_7d = len(recent_commands)
    completed_commands_7d = sum(
        1
        for row in recent_commands
        if str(row.get("status", "queued") or "queued").strip().lower() == "completed"
    )
    wind_down_sessions_7d = sum(
        1
        for row in recent_commands
        if str(row.get("action", "") or "").strip().lower() == "winddown"
    )
    db_wind_down_sessions = _winddown_sessions_7d_from_db(user_id, now) if user_id else None
    if isinstance(db_wind_down_sessions, int):
        wind_down_sessions_7d = max(0, db_wind_down_sessions)
    command_completion_rate_pct = int(round((completed_commands_7d / command_total_7d) * 100.0)) if command_total_7d > 0 else 0
    db_command_metrics = _command_metrics_7d_from_db(user_id, now) if user_id else None
    if isinstance(db_command_metrics, dict):
        command_total_7d = max(0, int(db_command_metrics.get("total", command_total_7d) or 0))
        completed_commands_7d = max(0, int(db_command_metrics.get("completed", completed_commands_7d) or 0))
        command_completion_rate_pct = max(
            0,
            min(100, int(db_command_metrics.get("completion_rate_pct", command_completion_rate_pct) or 0)),
        )

    checklist_progress = max(0, min(100, int(checklist.get("progress_pct", 0) or 0)))
    helpful_pct = max(0, min(100, int(feedback.get("helpful_pct", 0) or 0)))
    feedback_total = max(0, int(feedback.get("total_votes", 0) or 0))
    normalized_command_feedback = _command_feedback_payload(
        _normalize_command_feedback_summary(
            command_feedback if isinstance(command_feedback, dict) else {}
        )
    )
    command_feedback_total = max(0, int(normalized_command_feedback.get("total_votes", 0) or 0))
    command_feedback_helpful_pct = max(
        0,
        min(100, int(normalized_command_feedback.get("helpful_pct", 0) or 0)),
    )

    activation_progress_pct = int(
        round(
            min(
                100.0,
                (checklist_progress * 0.7)
                + min(20.0, float(completed_commands_7d) * 4.0)
                + (5.0 if feedback_total > 0 else 0.0)
                + (5.0 if command_feedback_total > 0 else 0.0),
            )
        )
    )

    if activation_progress_pct >= 80:
        cohort_status_line = "Activation is strong for this beta account."
    elif activation_progress_pct >= 50:
        cohort_status_line = "Activation is building. Keep nightly loops consistent."
    else:
        cohort_status_line = "Activation is early. Finish First 3 Nights to stabilize usage."

    if command_total_7d == 0:
        quality_gate_line = "Run tonight's flow to start collecting reliability signals."
    elif (
        command_completion_rate_pct >= 90
        and (feedback_total == 0 or helpful_pct >= 70)
        and (command_feedback_total == 0 or command_feedback_helpful_pct >= 70)
    ):
        quality_gate_line = "Scripted flow quality is healthy for beta progression."
    else:
        quality_gate_line = "Hold feature expansion and improve reliability before scaling beta."

    return {
        "window_days": 7,
        "activation_progress_pct": activation_progress_pct,
        "first_3_nights_completed": int(checklist.get("completed_steps", 0) or 0),
        "first_3_nights_total": int(checklist.get("total_steps", 5) or 5),
        "command_total_7d": command_total_7d,
        "command_completion_rate_pct": command_completion_rate_pct,
        "wind_down_sessions_7d": wind_down_sessions_7d,
        "nightly_feedback_total": feedback_total,
        "nightly_feedback_helpful_pct": helpful_pct,
        "automation_feedback_total": command_feedback_total,
        "automation_feedback_helpful_pct": command_feedback_helpful_pct,
        "cohort_status_line": cohort_status_line,
        "quality_gate_line": quality_gate_line,
        "generated_at_utc": to_iso(now),
    }


def _beta_acceptance_cohort_report(
    *,
    max_testers: int = 5,
    min_required: int = 3,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    safe_max = max(1, min(int(max_testers or 5), 25))
    safe_min = max(1, min(int(min_required or 3), safe_max))
    scripted_target_pct = 90
    now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())

    try:
        users = _db_user_repository().list_all(limit=5000)
        beta_repo = _db_beta_progress_repository()
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="beta_acceptance_report_unavailable",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )
        return {
            "window_label": "Day 36-45 beta exit gate",
            "required_testers_min": safe_min,
            "max_testers_considered": safe_max,
            "quality_target_pct": scripted_target_pct,
            "testers_in_scope": 0,
            "milestone_complete_testers": 0,
            "scripted_flow_success_testers": 0,
            "scripted_flow_success_pct": 0,
            "exit_gate_ready_testers": 0,
            "exit_gate_pass": False,
            "blockers": ["Beta cohort data is unavailable. Restore DB connectivity first."],
            "generated_at_utc": to_iso(now),
            "testers": [],
        }

    testers: list[dict[str, Any]] = []
    for user in users:
        user_id = str(getattr(user, "id", "") or "").strip()
        if not user_id:
            continue
        email = str(getattr(user, "email", "") or "").strip().lower()
        full_name = str(getattr(user, "full_name", "") or "").strip()

        try:
            checklist_state = beta_repo.get_first_three_nights_state(user_id)
            checklist = _first_3_nights_payload(
                _normalize_first_3_nights_state(checklist_state if isinstance(checklist_state, dict) else {})
            )
        except Exception:
            checklist = _first_3_nights_payload(_normalize_first_3_nights_state({}))

        metrics_raw: dict[str, Any] = {}
        try:
            snapshot = beta_repo.get_beta_metrics_snapshot(user_id)
            if isinstance(snapshot, dict):
                metrics_raw = dict(snapshot)
        except Exception:
            metrics_raw = {}

        if not metrics_raw:
            try:
                feedback_state = beta_repo.get_nightly_summary_feedback(user_id)
            except Exception:
                feedback_state = {}
            feedback = _nightly_summary_feedback_payload(feedback_state if isinstance(feedback_state, dict) else {})
            metrics_raw = _beta_metrics_payload(
                checklist=checklist,
                commands=[],
                feedback=feedback,
                user_id=user_id,
                now_utc=now,
            )

        command_total_7d = max(0, int(metrics_raw.get("command_total_7d", 0) or 0))
        command_completion_rate_pct = max(0, min(100, int(metrics_raw.get("command_completion_rate_pct", 0) or 0)))
        wind_down_sessions_7d = max(0, int(metrics_raw.get("wind_down_sessions_7d", 0) or 0))
        activation_progress_pct = max(0, min(100, int(metrics_raw.get("activation_progress_pct", 0) or 0)))
        first_3_nights_completed = max(0, int(checklist.get("completed_steps", 0) or 0))
        first_3_nights_total = max(1, int(checklist.get("total_steps", 5) or 5))
        milestone_complete = bool(checklist.get("is_complete", False))
        scripted_flow_success = bool(
            command_total_7d > 0
            and wind_down_sessions_7d > 0
            and command_completion_rate_pct >= scripted_target_pct
        )
        exit_gate_ready = bool(milestone_complete and scripted_flow_success)
        generated_at_utc = str(metrics_raw.get("generated_at_utc", "") or "").strip()

        testers.append(
            {
                "user_id": user_id,
                "email": email,
                "name": full_name,
                "first_3_nights_completed": first_3_nights_completed,
                "first_3_nights_total": first_3_nights_total,
                "milestone_complete": milestone_complete,
                "activation_progress_pct": activation_progress_pct,
                "command_total_7d": command_total_7d,
                "command_completion_rate_pct": command_completion_rate_pct,
                "wind_down_sessions_7d": wind_down_sessions_7d,
                "scripted_flow_success": scripted_flow_success,
                "exit_gate_ready": exit_gate_ready,
                "generated_at_utc": generated_at_utc,
            }
        )

    def _tester_sort_key(row: dict[str, Any]) -> tuple[int, int, int, int, int, float]:
        generated_at = _parse_iso_timestamp(str(row.get("generated_at_utc", "") or ""))
        generated_ts = ensure_utc(generated_at).timestamp() if isinstance(generated_at, datetime) else 0.0
        return (
            int(bool(row.get("exit_gate_ready", False))),
            int(bool(row.get("milestone_complete", False))),
            int(row.get("activation_progress_pct", 0) or 0),
            int(row.get("command_completion_rate_pct", 0) or 0),
            int(row.get("wind_down_sessions_7d", 0) or 0),
            generated_ts,
        )

    testers.sort(key=_tester_sort_key, reverse=True)
    in_scope = testers[:safe_max]

    testers_in_scope = len(in_scope)
    milestone_complete_testers = sum(1 for row in in_scope if bool(row.get("milestone_complete", False)))
    scripted_flow_success_testers = sum(1 for row in in_scope if bool(row.get("scripted_flow_success", False)))
    exit_gate_ready_testers = sum(1 for row in in_scope if bool(row.get("exit_gate_ready", False)))
    scripted_flow_success_pct = (
        int(round((scripted_flow_success_testers / testers_in_scope) * 100.0))
        if testers_in_scope > 0
        else 0
    )

    blockers: list[str] = []
    if testers_in_scope < safe_min:
        blockers.append(f"Need at least {safe_min} beta testers in scope; found {testers_in_scope}.")
    if milestone_complete_testers < safe_min:
        blockers.append(
            f"First 3 Nights is fully completed for {milestone_complete_testers}/{safe_min} required testers."
        )
    if scripted_flow_success_pct < scripted_target_pct:
        blockers.append(
            f"Scripted flow success is {scripted_flow_success_pct}% (target: {scripted_target_pct}%+)."
        )
    if exit_gate_ready_testers < safe_min:
        blockers.append(
            f"Only {exit_gate_ready_testers}/{safe_min} testers pass both milestone and scripted quality gates."
        )

    exit_gate_pass = bool(
        testers_in_scope >= safe_min
        and scripted_flow_success_pct >= scripted_target_pct
        and exit_gate_ready_testers >= safe_min
    )

    return {
        "window_label": "Day 36-45 beta exit gate",
        "required_testers_min": safe_min,
        "max_testers_considered": safe_max,
        "quality_target_pct": scripted_target_pct,
        "testers_in_scope": testers_in_scope,
        "milestone_complete_testers": milestone_complete_testers,
        "scripted_flow_success_testers": scripted_flow_success_testers,
        "scripted_flow_success_pct": scripted_flow_success_pct,
        "exit_gate_ready_testers": exit_gate_ready_testers,
        "exit_gate_pass": exit_gate_pass,
        "blockers": blockers,
        "generated_at_utc": to_iso(now),
        "testers": in_scope,
    }


def _normalize_cohort_key(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "kuwait_beta"
    compact = "_".join(part for part in raw.replace("-", "_").split("_") if part)
    return compact or "kuwait_beta"


def _beta_cohort_progress_report(
    *,
    cohort_key: str = "kuwait_beta",
    target_min: int = 10,
    target_max: int = 15,
    max_rows: int = 50,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    normalized_cohort = _normalize_cohort_key(cohort_key)
    safe_target_min = max(1, min(int(target_min or 10), 250))
    safe_target_max = max(safe_target_min, min(int(target_max or 15), 500))
    safe_max_rows = max(1, min(int(max_rows or 50), 500))
    scripted_target_pct = 90
    now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())

    try:
        beta_repo = _db_beta_progress_repository()
        user_repo = _db_user_repository()
        cohort_members = beta_repo.list_cohort_members(
            cohort_key=normalized_cohort,
            limit=safe_max_rows,
        )
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="beta_cohort_progress_unavailable",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )
        return {
            "cohort_key": normalized_cohort,
            "target_min_active_testers": safe_target_min,
            "target_max_active_testers": safe_target_max,
            "enrolled_testers": 0,
            "active_testers_7d": 0,
            "active_rate_pct": 0,
            "remaining_to_target_min": safe_target_min,
            "over_target_by": 0,
            "target_band_hit": False,
            "first_3_nights_complete_testers": 0,
            "scripted_flow_success_testers": 0,
            "scripted_flow_success_pct": 0,
            "status_line": "Cohort data unavailable. Restore DB connectivity first.",
            "blockers": [
                "Cohort data unavailable. Restore DB connectivity first.",
            ],
            "generated_at_utc": to_iso(now),
            "testers": [],
        }

    testers: list[dict[str, Any]] = []
    for member in cohort_members:
        user_id = str(member.get("user_id", "") or "").strip()
        if not user_id:
            continue
        user = user_repo.get_user_by_id(user_id)
        email = str(getattr(user, "email", "") or "").strip().lower()
        name = str(getattr(user, "full_name", "") or "").strip()
        timezone_value = str(getattr(user, "timezone", "") or "").strip()

        checklist_state = beta_repo.get_first_three_nights_state(user_id)
        checklist = _first_3_nights_payload(
            _normalize_first_3_nights_state(checklist_state if isinstance(checklist_state, dict) else {})
        )
        first_3_nights_complete = bool(checklist.get("is_complete", False))

        metrics = beta_repo.get_beta_metrics_snapshot(user_id)
        if not isinstance(metrics, dict):
            metrics = {}
        command_total_7d = max(0, int(metrics.get("command_total_7d", 0) or 0))
        command_completion_rate_pct = max(
            0,
            min(100, int(metrics.get("command_completion_rate_pct", 0) or 0)),
        )
        wind_down_sessions_7d = max(0, int(metrics.get("wind_down_sessions_7d", 0) or 0))
        activation_progress_pct = max(0, min(100, int(metrics.get("activation_progress_pct", 0) or 0)))
        generated_at_utc = str(metrics.get("generated_at_utc", "") or "").strip()
        nightly_feedback_total = max(0, int(metrics.get("nightly_feedback_total", 0) or 0))
        automation_feedback_total = max(0, int(metrics.get("automation_feedback_total", 0) or 0))
        active_7d = bool(
            command_total_7d > 0
            or wind_down_sessions_7d > 0
            or nightly_feedback_total > 0
            or automation_feedback_total > 0
        )
        scripted_flow_success = bool(
            command_total_7d > 0
            and wind_down_sessions_7d > 0
            and command_completion_rate_pct >= scripted_target_pct
        )

        testers.append(
            {
                "user_id": user_id,
                "email": email,
                "name": name,
                "timezone": timezone_value,
                "country_code": str(member.get("country_code", "") or "").strip().upper() or "KW",
                "status": str(member.get("status", "") or "").strip().lower() or "active",
                "source": str(member.get("source", "") or "").strip().lower() or "admin_manual",
                "notes": str(member.get("notes", "") or ""),
                "cohort_enrolled_at_utc": str(member.get("created_at_utc", "") or ""),
                "active_7d": active_7d,
                "first_3_nights_complete": first_3_nights_complete,
                "activation_progress_pct": activation_progress_pct,
                "command_total_7d": command_total_7d,
                "command_completion_rate_pct": command_completion_rate_pct,
                "wind_down_sessions_7d": wind_down_sessions_7d,
                "scripted_flow_success": scripted_flow_success,
                "metrics_generated_at_utc": generated_at_utc,
            }
        )

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, int, int, float]:
        generated_at = _parse_iso_timestamp(str(row.get("metrics_generated_at_utc", "") or ""))
        generated_ts = ensure_utc(generated_at).timestamp() if isinstance(generated_at, datetime) else 0.0
        return (
            int(bool(row.get("active_7d", False))),
            int(bool(row.get("first_3_nights_complete", False))),
            int(row.get("activation_progress_pct", 0) or 0),
            int(row.get("command_completion_rate_pct", 0) or 0),
            generated_ts,
        )

    testers.sort(key=_sort_key, reverse=True)

    enrolled_testers = len(testers)
    active_testers_7d = sum(1 for row in testers if bool(row.get("active_7d", False)))
    active_rate_pct = int(round((active_testers_7d / enrolled_testers) * 100.0)) if enrolled_testers > 0 else 0
    first_3_nights_complete_testers = sum(1 for row in testers if bool(row.get("first_3_nights_complete", False)))
    scripted_flow_success_testers = sum(1 for row in testers if bool(row.get("scripted_flow_success", False)))
    scripted_flow_success_pct = int(round((scripted_flow_success_testers / enrolled_testers) * 100.0)) if enrolled_testers > 0 else 0

    remaining_to_target_min = max(0, safe_target_min - active_testers_7d)
    over_target_by = max(0, active_testers_7d - safe_target_max)
    target_band_hit = bool(active_testers_7d >= safe_target_min and active_testers_7d <= safe_target_max)

    blockers: list[str] = []
    if active_testers_7d < safe_target_min:
        blockers.append(
            f"Need {remaining_to_target_min} more active tester(s) in the last 7 days to reach minimum target."
        )
    if scripted_flow_success_pct < scripted_target_pct:
        blockers.append(
            f"Scripted flow success is {scripted_flow_success_pct}% (target: {scripted_target_pct}%+)."
        )

    if target_band_hit:
        status_line = "Kuwait beta cohort is within target band and ready for Month 2 polish cycles."
    elif active_testers_7d < safe_target_min:
        status_line = "Kuwait beta cohort needs more active testers before scaling."
    else:
        status_line = "Kuwait beta cohort is above target band. Stabilize reliability before expanding."

    return {
        "cohort_key": normalized_cohort,
        "target_min_active_testers": safe_target_min,
        "target_max_active_testers": safe_target_max,
        "enrolled_testers": enrolled_testers,
        "active_testers_7d": active_testers_7d,
        "active_rate_pct": active_rate_pct,
        "remaining_to_target_min": remaining_to_target_min,
        "over_target_by": over_target_by,
        "target_band_hit": target_band_hit,
        "first_3_nights_complete_testers": first_3_nights_complete_testers,
        "scripted_flow_success_testers": scripted_flow_success_testers,
        "scripted_flow_success_pct": scripted_flow_success_pct,
        "status_line": status_line,
        "blockers": blockers,
        "generated_at_utc": to_iso(now),
        "testers": testers,
    }


def _bedtime_drift_timeline_item(
    profile: dict[str, Any],
    *,
    now_utc: datetime | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    _SLEEP_ENGINE.ensure_shape(profile)
    now_for_engine = _sleep_engine_now(now_utc)
    alert_line = _SLEEP_ENGINE.bedtime_drift_alert(profile)
    if not str(alert_line).startswith("Predictive alert:"):
        return None, False
    should_mark = bool(_SLEEP_ENGINE.should_send_bedtime_drift_alert(profile, now=now_for_engine))
    if should_mark:
        _SLEEP_ENGINE.mark_bedtime_drift_alert_sent(profile, now=now_for_engine)
    return {
        "time": "Tonight",
        "event": str(alert_line),
        "status": "review",
        "command_id": "",
    }, should_mark


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


def _spotify_create_oauth_state(
    *,
    profile: dict[str, Any],
    user_key: str,
    done_uri: str = "",
) -> str:
    if not user_key:
        return ""
    states = _get_scoped_profile_section(profile, "spotify_oauth_state")
    state = secrets.token_urlsafe(24)
    row: dict[str, Any] = {
        "state": state,
        "created_at": _now_utc_iso(),
    }
    safe_done_uri = _safe_mobile_done_uri(done_uri)
    if safe_done_uri:
        row["done_uri"] = safe_done_uri
    states[user_key] = row
    profile["spotify_oauth_state"] = states
    _save_profile(profile)
    return state


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


def _spotify_user_token(user_key: str, user_email: str = "") -> dict[str, Any]:
    from database import SpotifyTokenRepository
    repo = SpotifyTokenRepository()
    token = repo.get(user_key)
    if token:
        return token
    if not user_email:
        return {}
    # Fallback: look up by spotify_email if user_key changed (e.g. id vs email)
    return {}


def _spotify_refresh_user_token_if_needed(user_key: str, user_email: str = "") -> dict[str, Any]:
    from database import SpotifyTokenRepository
    repo = SpotifyTokenRepository()
    token = _spotify_user_token(user_key, user_email=user_email)
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
    new_access_token = str(refreshed.get("access_token", "") or "")
    if not new_access_token:
        return token

    new_expires_at = _spotify_expires_at(refreshed.get("expires_in", 3600))
    repo.update_access_token(user_key, access_token=new_access_token, expires_at=new_expires_at)

    token["access_token"] = new_access_token
    token["expires_at"] = new_expires_at
    return token


def _bump(metric: str, inc: int = 1):
    TELEMETRY[metric] = int(TELEMETRY.get(metric, 0)) + int(inc)


def _new_trace_id() -> str:
    return f"req_{uuid.uuid4().hex[:8]}"


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
    fallback = _new_trace_id()
    request.state.trace_id = fallback
    return fallback


def _status_error_code(status_code: int) -> str:
    code = int(status_code)
    if code == 429:
        return RATE_LIMITED
    if code == 503:
        return DEVICE_OFFLINE
    if code in {401, 403}:
        return UNAUTHORIZED
    if code >= 500:
        return INTERNAL_ERROR
    return VALIDATION_ERROR


def _error_envelope(*, trace_id: str, code: str, message: str, retry_after: int | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": str(code or INTERNAL_ERROR),
            "message": str(message or "Request failed"),
            "trace_id": str(trace_id),
            "retry_after": int(retry_after) if retry_after is not None else None,
        },
    }


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    trace_id = _request_trace_id(request)
    response = error_response(exc.code, exc.message, trace_id, retry_after=exc.retry_after)
    response.status_code = int(exc.status_code)
    response.headers[_TRACE_ID_HEADER] = trace_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    trace_id = _request_trace_id(request)
    message = str(exc.detail) if isinstance(exc.detail, str) and str(exc.detail).strip() else "Request failed"
    code = _status_error_code(exc.status_code)
    retry_after: int | None = None
    if isinstance(exc.headers, dict):
        raw_retry = exc.headers.get("Retry-After")
        if raw_retry is not None:
            try:
                retry_after = max(0, int(float(str(raw_retry))))
            except Exception:
                retry_after = None
    _event(
        "warning",
        "http_exception",
        trace_id=trace_id,
        path=request.url.path,
        status_code=exc.status_code,
        code=code,
    )
    response = error_response(code, message, trace_id, retry_after=retry_after)
    response.status_code = int(exc.status_code)
    response.headers[_TRACE_ID_HEADER] = trace_id
    return response


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
    response = error_response(VALIDATION_ERROR, "Request validation failed", trace_id)
    response.status_code = 422
    response.headers[_TRACE_ID_HEADER] = trace_id
    return response


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
    response = error_response(INTERNAL_ERROR, "Internal server error", trace_id)
    response.status_code = 500
    response.headers[_TRACE_ID_HEADER] = trace_id
    return response


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    if not normalized:
        return False
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    return any(partial in normalized for partial in _SENSITIVE_PARTIAL_KEYS)


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
    except Exception as _mem_exc:
        logger.warning("memory_store.record_turn failed user_id=%s err=%s", str(actor.get("user_id", "")), _mem_exc)

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
    # Prefer the authoritative server hostname over the client-supplied Host header.
    host = _SERVER_HOSTNAME or (request.headers.get("host", "") or "").strip().lower()
    if not host:
        raise HTTPException(status_code=403, detail="Origin validation failed")
    parsed = urlparse(origin)
    origin_host = (parsed.netloc or "").strip().lower()
    if not origin_host:
        _bump("same_origin_denied")
        _event("warning", "same_origin_block", path=request.url.path, origin=origin, host=host, reason="missing_origin_host")
        raise HTTPException(status_code=403, detail="Cross-site request blocked")
    if origin_host == host:
        return

    # Dev/browser support: allow explicit CORS origins and regex-matched origins.
    if origin in ALLOWED_ORIGINS:
        return
    if ALLOWED_ORIGIN_REGEX and re.match(ALLOWED_ORIGIN_REGEX, origin):
        return

    _bump("same_origin_denied")
    _event("warning", "same_origin_block", path=request.url.path, origin=origin, host=host)
    raise HTTPException(status_code=403, detail="Cross-site request blocked")


def _cookie_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("sb_user_token", "")
    if not token:
        return None
    user = store.validate_user_token(token)
    if not isinstance(user, dict):
        return None

    user_id = str(user.get("user_id", "") or "").strip()
    email = str(user.get("email", "") or "").strip().lower()
    db_user = _db_user_repository().get_user_by_id(user_id) if user_id else None
    if db_user is None and email:
        db_user = _db_user_repository().get_user_by_email(email)

    if db_user is not None:
        payload = {
            "user_id": str(getattr(db_user, "id", "") or ""),
            "email": str(getattr(db_user, "email", "") or ""),
            "name": str(getattr(db_user, "full_name", "") or ""),
        }
        _ensure_legacy_store_user_shadow(payload, password_hash=str(getattr(db_user, "password_hash", "") or ""))
        return payload

    _ensure_db_user_shadow(user)
    return user


def _bearer_token(request: Request) -> str:
    header = str(request.headers.get("authorization", "") or "").strip()
    if not header:
        return ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return str(token or "").strip()


def _mobile_user(request: Request) -> dict[str, Any] | None:
    token = _bearer_token(request)
    if not token:
        return None
    payload = _mobile_user_from_access_token(token)
    if isinstance(payload, dict):
        return payload
    user = store.validate_mobile_access_token(token)
    if isinstance(user, dict):
        _ensure_db_user_shadow(user)
    return user if isinstance(user, dict) else None


def _mobile_user_from_query_access_token(request: Request) -> dict[str, Any] | None:
    token = str(request.query_params.get("access_token", "") or "").strip()
    if not token:
        return None
    user = _mobile_user_from_access_token(token)
    if isinstance(user, dict):
        return user
    legacy = store.validate_mobile_access_token(token)
    if isinstance(legacy, dict):
        _ensure_db_user_shadow(legacy)
        return legacy
    return None


def _cookie_admin(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("sb_admin_token", "")
    if not token:
        return None
    admin = store.validate_admin_token(token)
    return admin if isinstance(admin, dict) else None


def _authenticated_user(request: Request) -> dict[str, Any] | None:
    return _mobile_user(request) or _cookie_user(request)


def _authenticated_actor(request: Request) -> dict[str, Any] | None:
    return _authenticated_user(request) or _cookie_admin(request)


def _require_user(request: Request) -> dict[str, Any]:
    user = _authenticated_user(request)
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


def _require_premium_plan(request: Request) -> dict[str, Any]:
    """Require an authenticated user with an active premium or trial subscription."""
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    if user_id:
        status_payload = _subscription_status_payload(user_id)
        sub_status = str(status_payload.get("subscription_status", "free") or "free").lower()
        trial_active = bool(status_payload.get("trial_active", False))
        if sub_status not in ("premium", "pro", "standard") and not trial_active:
            _bump("guard_premium_denied")
            _event("warning", "premium_guard_denied", user_id=user_id, path=request.url.path)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Premium subscription required for this feature.",
            )
    return user


def _database_connection():
    global _DB_CONNECTION
    global _DB_CONNECTION_URL
    global _DB_USER_REPOSITORY
    global _SUBSCRIPTION_GATE
    global _DB_BETA_PROGRESS_REPOSITORY
    global _DB_EVENT_REPOSITORY
    global _DB_SLEEP_SESSION_REPOSITORY
    global _DB_COMMAND_REPOSITORY
    global _DB_MOBILE_AUTH_REPOSITORY
    global _BILLING_SERVICE
    global _DB_UPDATE_REPOSITORY
    global _DB_FEATURE_FLAG_REPOSITORY

    env_url = str(os.getenv("DATABASE_URL", "") or "").strip()
    # Fast path — already initialised with the same URL (no lock needed).
    if _DB_CONNECTION is not None and _DB_CONNECTION_URL == env_url:
        return _DB_CONNECTION
    with _DB_INIT_LOCK:
        # Re-check inside the lock: another thread may have initialised while
        # we were waiting.
        if (_DB_CONNECTION is None) or (_DB_CONNECTION_URL != env_url):
            from database import DatabaseConnection

            connection = DatabaseConnection(database_url=env_url or None)
            connection.create_tables()
            _DB_CONNECTION = connection
            _DB_CONNECTION_URL = env_url
            _DB_USER_REPOSITORY = None
            _SUBSCRIPTION_GATE = None
            _DB_BETA_PROGRESS_REPOSITORY = None
            _DB_EVENT_REPOSITORY = None
            _DB_SLEEP_SESSION_REPOSITORY = None
            _DB_COMMAND_REPOSITORY = None
            _DB_MOBILE_AUTH_REPOSITORY = None
            _BILLING_SERVICE = None
            _DB_UPDATE_REPOSITORY = None
            _DB_FEATURE_FLAG_REPOSITORY = None
    return _DB_CONNECTION


def _db_user_repository():
    global _DB_USER_REPOSITORY
    if _DB_USER_REPOSITORY is None:
        from database import UserRepository

        _DB_USER_REPOSITORY = UserRepository(db=_database_connection())
    return _DB_USER_REPOSITORY


def _db_beta_progress_repository():
    global _DB_BETA_PROGRESS_REPOSITORY
    if _DB_BETA_PROGRESS_REPOSITORY is None:
        from database import BetaProgressRepository

        _DB_BETA_PROGRESS_REPOSITORY = BetaProgressRepository(db=_database_connection())
    return _DB_BETA_PROGRESS_REPOSITORY


def _db_event_repository():
    global _DB_EVENT_REPOSITORY
    if _DB_EVENT_REPOSITORY is None:
        from database import EventRepository

        _DB_EVENT_REPOSITORY = EventRepository(db=_database_connection())
    return _DB_EVENT_REPOSITORY


def _db_sleep_session_repository():
    global _DB_SLEEP_SESSION_REPOSITORY
    if _DB_SLEEP_SESSION_REPOSITORY is None:
        from database import SleepSessionRepository

        _DB_SLEEP_SESSION_REPOSITORY = SleepSessionRepository(db=_database_connection())
    return _DB_SLEEP_SESSION_REPOSITORY


def _db_command_repository():
    global _DB_COMMAND_REPOSITORY
    if _DB_COMMAND_REPOSITORY is None:
        from database import MobileCommandRepository

        _DB_COMMAND_REPOSITORY = MobileCommandRepository(db=_database_connection())
    return _DB_COMMAND_REPOSITORY


def _db_mobile_auth_repository():
    global _DB_MOBILE_AUTH_REPOSITORY
    if _DB_MOBILE_AUTH_REPOSITORY is None:
        from database import MobileAuthRepository

        _DB_MOBILE_AUTH_REPOSITORY = MobileAuthRepository(db=_database_connection())
    return _DB_MOBILE_AUTH_REPOSITORY


def _db_update_repository():
    global _DB_UPDATE_REPOSITORY
    if _DB_UPDATE_REPOSITORY is None:
        from database import UpdateRepository
        _DB_UPDATE_REPOSITORY = UpdateRepository(db=_database_connection())
    return _DB_UPDATE_REPOSITORY


def _db_feature_flag_repository():
    global _DB_FEATURE_FLAG_REPOSITORY
    if _DB_FEATURE_FLAG_REPOSITORY is None:
        from database import FeatureFlagRepository
        _DB_FEATURE_FLAG_REPOSITORY = FeatureFlagRepository(db=_database_connection())
    return _DB_FEATURE_FLAG_REPOSITORY


def _billing_service() -> BillingService:
    global _BILLING_SERVICE
    if _BILLING_SERVICE is None:
        _BILLING_SERVICE = BillingService.from_settings(store=store)
    return _BILLING_SERVICE


def _mobile_user_from_access_token(access_token: str) -> dict[str, Any] | None:
    token = str(access_token or "").strip()
    if not token:
        return None

    try:
        session_payload = _db_mobile_auth_repository().validate_access_token(token)
    except Exception:
        session_payload = {}
    if not isinstance(session_payload, dict) or not session_payload:
        return None

    user_id = str(session_payload.get("user_id", "") or "").strip()
    if not user_id:
        return None

    db_user = _db_user_repository().get_user_by_id(user_id)
    if db_user is None:
        # Keep bearer sessions usable even when legacy JSON users and DB shadow
        # users are temporarily out of sync in local/dev tests.
        legacy_user = store.get_user(user_id)
        if isinstance(legacy_user, dict):
            _ensure_db_user_shadow(legacy_user)
            return {
                "user_id": user_id,
                "email": str(legacy_user.get("email", "") or ""),
                "name": str(legacy_user.get("name", "") or ""),
                "client_name": str(session_payload.get("client_name", "") or ""),
                "auth_type": "mobile_bearer",
            }
        return None

    return {
        "user_id": user_id,
        "email": str(getattr(db_user, "email", "") or ""),
        "name": str(getattr(db_user, "full_name", "") or ""),
        "client_name": str(session_payload.get("client_name", "") or ""),
        "auth_type": "mobile_bearer",
    }


def _ensure_db_user_shadow(user: dict[str, Any] | None) -> None:
    row = user if isinstance(user, dict) else {}
    user_id = str(row.get("user_id", "") or "").strip()
    email = str(row.get("email", "") or "").strip().lower()
    if not email and user_id:
        local = re.sub(r"[^a-z0-9._-]+", "_", user_id.lower()).strip("._-") or "shadow_user"
        email = f"{local}@shadow.local"
    full_name = str(row.get("name", "") or "").strip() or None
    password_hash = str(row.get("password_hash", "") or "").strip() or "mobile_shadow_managed"
    if not user_id or not email:
        return

    try:
        repo = _db_user_repository()
        existing = repo.get_user_by_id(user_id)
        if existing is None:
            by_email = repo.get_user_by_email(email)
            if by_email is None:
                repo.create_user(
                    email=email,
                    password_hash=password_hash,
                    full_name=full_name,
                    user_id=user_id,
                )
            elif str(getattr(by_email, "id", "") or "") == user_id and full_name:
                repo.update_user(user_id, full_name=full_name)
            return

        updates: dict[str, Any] = {}
        existing_name = str(getattr(existing, "full_name", "") or "").strip()
        if full_name and full_name != existing_name:
            updates["full_name"] = full_name
        existing_password_hash = str(getattr(existing, "password_hash", "") or "").strip()
        if password_hash and (existing_password_hash in {"", "mobile_shadow_managed"}) and (password_hash != existing_password_hash):
            updates["password_hash"] = password_hash
        existing_email = str(getattr(existing, "email", "") or "").strip().lower()
        if existing_email != email:
            clash = repo.get_user_by_email(email)
            if clash is None or str(getattr(clash, "id", "") or "") == user_id:
                updates["email"] = email
        if updates:
            repo.update_user(user_id, **updates)
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="db_user_shadow_sync_failed",
            trace_id="web_runtime",
            user_id=user_id,
            metadata={"error_type": type(exc).__name__},
        )


def _subscription_gate():
    global _SUBSCRIPTION_GATE
    if _SUBSCRIPTION_GATE is None:
        from subscriptions import SubscriptionGate

        _SUBSCRIPTION_GATE = SubscriptionGate(user_repo=_db_user_repository())
    return _SUBSCRIPTION_GATE


def _to_iso_nullable(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return to_iso(value)


def _subscription_features(subscription_status: str) -> dict[str, int]:
    premium_like = str(subscription_status or "free").strip().lower() in {"trial", "premium"}
    return {
        "max_scenes": 999 if premium_like else 3,
        "wind_down_minutes": 30 if premium_like else 10,
        "automations_limit": 999 if premium_like else 2,
    }


def _resolve_subscription_actor_user_id(request: Request, requested_user_id: str = "") -> str:
    requested = str(requested_user_id or "").strip()
    user = _authenticated_user(request)
    admin = _cookie_admin(request)

    if not user and not admin:
        raise HTTPException(status_code=401, detail="Authentication required")

    if admin:
        if requested:
            return requested
        admin_user_id = str(admin.get("user_id", "") or "").strip()
        if admin_user_id:
            return admin_user_id
        raise HTTPException(status_code=400, detail="user_id is required")

    actor_user_id = str((user or {}).get("user_id", "") or "").strip()
    if not actor_user_id:
        raise HTTPException(status_code=400, detail="Unable to resolve authenticated user")

    if requested and requested != actor_user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's subscription")

    return requested or actor_user_id


def _subscription_status_payload(user_id: str) -> dict[str, Any]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return {
            "subscription_status": "free",
            "trial_active": False,
            "trial_days_remaining": None,
            "trial_end_date": None,
            "features": _subscription_features("free"),
        }

    user = _db_user_repository().get_user_by_id(user_key)
    if user is None:
        return {
            "subscription_status": "free",
            "trial_active": False,
            "trial_days_remaining": None,
            "trial_end_date": None,
            "features": _subscription_features("free"),
        }

    status_value = str(getattr(user, "subscription_status", "free") or "free").strip().lower()
    if status_value not in {"free", "trial", "premium"}:
        status_value = "free"

    trial_active = False
    trial_days_remaining: int | None = None
    if status_value == "trial":
        gate = _subscription_gate()
        trial_active = bool(gate.is_trial_active(user))
        trial_days_remaining = int(gate.get_trial_days_remaining(user))

    effective_status = status_value
    if status_value == "trial" and not trial_active:
        effective_status = "free"

    return {
        "subscription_status": effective_status,
        "trial_active": trial_active,
        "trial_days_remaining": trial_days_remaining,
        "trial_end_date": _to_iso_nullable(getattr(user, "trial_end_date", None)),
        "features": _subscription_features(effective_status),
    }


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


@app.get("/healthz/detailed")
def healthz_detailed() -> dict[str, Any]:
    checks: dict[str, Any] = {"service": "web_runtime"}

    try:
        from database.connection import DatabaseConnection
        db_conn = DatabaseConnection()
        checks["database"] = {"ok": db_conn.health_check(), "version": db_conn.schema_version()}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    try:
        import shutil
        disk = shutil.disk_usage("/")
        checks["disk"] = {
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "free_gb": round(disk.free / (1024 ** 3), 2),
            "used_pct": round((disk.used / disk.total) * 100, 1),
        }
    except Exception:
        checks["disk"] = {"ok": False}

    checks["deepgram_configured"] = bool(str(settings.deepgram_api_key or "").strip())

    all_ok = checks.get("database", {}).get("ok", False)
    checks["ok"] = all_ok
    return checks


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/bed/state")
@app.get("/v1/bedstate")
def bed_state_bridge(request: Request) -> dict[str, Any]:
    user = _authenticated_user(request)
    admin = _cookie_admin(request)
    if not (user or admin):
        raise APIError(code=UNAUTHORIZED, message="Login required", status_code=401)

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    snapshot = _stable_state_snapshot(profile)
    if not isinstance(snapshot, dict):
        snapshot = {}
    updated_at, stale, device_online, source = _bed_state_freshness_meta()
    return {
        "ok": True,
        "generated_at": _now_utc_iso(),
        "emotion_state": str(snapshot.get("emotion_state", "neutral") or "neutral"),
        "active_personality": str(snapshot.get("active_personality", "guide") or "guide"),
        "last_memory_context": _last_memory_context(),
        "biometric_summary": snapshot.get("biometric_summary", {}),
        "device_health_status": snapshot.get("device_health_status", {}),
        "schema_version": "1.1",
        "device_online": bool(device_online),
        "stale": bool(stale),
        "updated_at": updated_at,
        "source": source,
        "capabilities": _bed_capabilities(snapshot),
    }


@app.get("/v1/device/status")
def device_status(request: Request) -> dict[str, Any]:
    """Returns device status indicator: Green = online, Yellow = stale, Red = offline."""
    _require_user(request)
    trace_id_raw = getattr(request.state, "trace_id", "")
    trace_id = str(trace_id_raw).strip() or "no-trace"
    now = utcnow()
    updated_at = _now_utc_iso()

    latest_seen: datetime | None = None
    try:
        devices = store.list_fleet_devices(limit=1000)
    except Exception:
        devices = []

    if isinstance(devices, list):
        for row in devices:
            if not isinstance(row, dict):
                continue
            seen_raw = str(row.get("last_seen", "") or row.get("last_seen_at", "") or "")
            seen_at = _parse_iso_timestamp(seen_raw)
            if seen_at is not None and (latest_seen is None or seen_at > latest_seen):
                latest_seen = seen_at

    last_seen_iso: str | None = to_iso(latest_seen) if latest_seen is not None else None

    if latest_seen is None:
        status_value = "offline"
        color = "red"
        message = "Bed is offline. Last seen unavailable."
    else:
        age_seconds = max(0.0, (now - latest_seen).total_seconds())
        age_int = int(age_seconds)
        if age_seconds <= 30.0:
            status_value = "online"
            color = "green"
            message = f"Bed is online. Last seen {age_int} seconds ago."
        elif age_seconds <= 300.0:
            status_value = "stale"
            color = "yellow"
            message = f"Bed status is stale. Last seen {age_int} seconds ago."
        else:
            status_value = "offline"
            color = "red"
            age_minutes = max(1, int(age_seconds // 60))
            message = f"Bed is offline. Last seen {age_minutes} minutes ago."

    return {
        "status": status_value,
        "color": color,
        "message": message,
        "last_seen": last_seen_iso,
        "updated_at": updated_at,
        "trace_id": trace_id,
    }


@app.get("/v1/state")
def v1_state(request: Request) -> dict[str, Any]:
    if not (_authenticated_user(request) or _cookie_admin(request)):
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
    if not (_authenticated_user(request) or _cookie_admin(request)):
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


@app.get("/admin-billing")
def admin_billing(request: Request):
    if not _cookie_admin(request):
        return RedirectResponse(url="/login?role=admin&next=/admin-billing", status_code=302)
    return FileResponse(
        WEB_DIR / "admin-billing.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/admin")
def admin_v2(request: Request):
    if not _cookie_admin(request):
        return RedirectResponse(url="/login?role=admin&next=/admin", status_code=302)
    return FileResponse(
        WEB_DIR / "admin.html",
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
    import re as _re
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Valid email address is required")
    if len(email) > 254:
        raise HTTPException(status_code=400, detail="Email address is too long")
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters")
    if not _re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not _re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="Password must be 128 characters or fewer")
    try:
        # Public registration creates a normal app user only.
        # Admin roles (especially "owner") are not granted here and must come
        # from a separate secure provisioning/setup step.
        user = _register_mobile_user_db_first(email=email, password=password, name=name)
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
    email = str(payload.email or "").strip().lower()
    if _is_account_locked(email):
        _bump("auth_user_login_failure")
        _event("warning", "user_login_locked", email=email)
        raise HTTPException(status_code=429, detail="Account temporarily locked due to too many failed attempts. Try again in 15 minutes.")
    user = _login_mobile_user_db_first(email=email, password=payload.password or "")
    if not user:
        _record_login_failure(email)
        _bump("auth_user_login_failure")
        _event("warning", "user_login_failed", email=email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _clear_login_failures(email)
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
    email = str(payload.email or "").strip().lower()
    if _is_account_locked(email):
        _bump("auth_admin_login_failure")
        _event("warning", "admin_login_locked", email=email)
        raise HTTPException(status_code=429, detail="Account temporarily locked due to too many failed attempts. Try again in 15 minutes.")
    user = _login_mobile_user_db_first(email=email, password=payload.password or "")
    if not user:
        _record_login_failure(email)
        _bump("auth_admin_login_failure")
        _event("warning", "admin_login_failed", email=email, reason="invalid_credentials")
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

    _clear_login_failures(email)
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


@app.post("/v1/auth/revoke-all-sessions")
def auth_revoke_all_sessions(response: Response, request: Request) -> dict[str, Any]:
    """Invalidate every active session for the current user across both auth systems.
    Use this after a password change or when a device is lost.
    """
    _enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Unable to identify user for session revocation")

    legacy_revoked = store.revoke_all_sessions_for_user(user_id)
    try:
        mobile_revoked = _db_mobile_auth_repository().revoke_all_tokens_for_user(user_id)
    except Exception as _exc:
        logger.warning("mobile revoke_all_tokens_for_user failed user_id=%s err=%s", user_id, _exc)
        mobile_revoked = 0

    _clear_session_cookies(response)
    _event(
        "info",
        "revoke_all_sessions",
        user_id=user_id,
        legacy_revoked=legacy_revoked,
        mobile_revoked=mobile_revoked,
    )
    return {"ok": True, "legacy_revoked": legacy_revoked, "mobile_revoked": mobile_revoked}


@app.post("/v1/auth/delete-data")
def auth_delete_data(response: Response, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _cookie_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_token = str(request.cookies.get("sb_user_token", "") or "").strip()
    with _profile_rw():
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


@app.get("/v1/admin/diagnostics")
def admin_diagnostics(request: Request) -> dict[str, Any]:
    """Live snapshot of module-level global state for ops visibility."""
    _require_admin(request)
    with _CHAT_ENGINE_LOCK:
        chat_engines_count = len(_CHAT_ENGINES)
        chat_engine_keys = list(_CHAT_ENGINES.keys())[:20]
    undo_info = {}
    try:
        undo_info = {
            "pending_count": len(getattr(undo_manager, "_store", {})),
        }
    except Exception:
        pass
    return {
        "ok": True,
        "chat_engines": {
            "count": chat_engines_count,
            "max": _MAX_CHAT_ENGINES,
            "sample_keys": chat_engine_keys,
        },
        "profile_rw_lock": {
            "locked": _PROFILE_RW_LOCK.locked() if hasattr(_PROFILE_RW_LOCK, "locked") else "n/a",
        },
        "undo_manager": undo_info,
        "db_connection_active": _DB_CONNECTION is not None,
        "telemetry_keys": list(TELEMETRY.keys()),
        "uptime_ts": _now_utc_iso(),
    }


@app.get("/v1/mobile/dashboard")
def mobile_dashboard(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    key = _user_profile_key(user)
    profile_prefs = _chat_profile_prefs_for_user(profile, user)
    resolved_name = _resolved_user_display_name(user, profile_prefs)
    location_summary = _profile_location_summary(profile_prefs)
    resolved = _resolved_user_settings(profile, user)
    commands: list[dict[str, Any]] = []
    last_command_result = _last_command_result_from_profile(profile, key)
    profile_dirty = False
    if key:
        commands, changed = _progress_user_commands(
            profile,
            key,
            user_id=str(user.get("user_id", "") or key),
        )
        if commands:
            latest_result = _build_last_command_result_from_command(commands[0])
            last_command_result = latest_result
            if changed:
                _store_last_command_result(profile, key, latest_result)
        if changed:
            cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
            cmd_section[key] = commands
            profile["web_device_commands"] = cmd_section
            profile_dirty = True
    first_3_nights_checklist = _first_3_nights_payload(_normalize_first_3_nights_state({}))
    nightly_summary_feedback = _nightly_summary_feedback_payload(_normalize_nightly_summary_feedback({}))
    command_feedback_loop = _command_feedback_payload(_normalize_command_feedback_summary({}))
    if key:
        first_3_nights_checklist, _ = _sync_first_3_nights_state(
            profile,
            user,
            commands=commands,
        )
        nightly_summary_feedback = _nightly_summary_feedback_payload(
            _nightly_summary_feedback_for_user(profile, key)
        )
        command_feedback_loop = _command_feedback_payload(
            _command_feedback_for_user(profile, key)
        )
    if profile_dirty:
        _save_profile(profile)
    weekly_insight = _weekly_insight_payload(
        commands,
        user_id=key,
        wind_down_minutes=int(resolved.get("wind_down_minutes", 45) or 45),
        weekly_insight_enabled=bool(resolved.get("weekly_insight_enabled", True)),
        nightly_feedback=nightly_summary_feedback,
        command_feedback=command_feedback_loop,
    )
    bedtime_drift_alert = ""
    if bool(resolved.get("bedtime_drift_automation_enabled", True)):
        bedtime_drift_alert = _SLEEP_ENGINE.bedtime_drift_alert(profile)
    if not str(bedtime_drift_alert).startswith("Predictive alert:"):
        bedtime_drift_alert = ""
    nightly_summary = _nightly_summary_payload(
        profile,
        weekly_insight=weekly_insight,
        last_command_result=last_command_result,
    )

    return {
        "name": resolved_name,
        "location": str(location_summary.get("label", "Location pending") or "Location pending"),
        "response_style": resolved["response_style"],
        "engagement_level": resolved["engagement_level"],
        "partner_mode_enabled": resolved["partner_mode_enabled"],
        "wind_down_minutes": resolved["wind_down_minutes"],
        "last_command_result": last_command_result,
        "bedtime_drift_alert": bedtime_drift_alert,
        "weekly_insight": weekly_insight,
        "nightly_summary": nightly_summary,
        "first_3_nights_checklist": first_3_nights_checklist,
        "nightly_summary_feedback": nightly_summary_feedback,
        "automation_feedback_loop": command_feedback_loop,
    }


@app.get("/v1/mobile/scenes")
def mobile_scenes(request: Request) -> dict[str, Any]:
    _require_user(request)
    return {
        "ok": True,
        "preview_duration_seconds": SCENE_PREVIEW_SECONDS,
        "items": _scene_gallery_items(),
    }


@app.get("/v1/scenes/templates")
def scene_templates(request: Request, premium_only: bool = False) -> dict[str, Any]:
    user = _authenticated_user(request)
    templates = scene_store.get_templates_for_api()
    if premium_only:
        templates = [row for row in templates if bool(row.get("premium", False))]
    # Hide premium templates from unauthenticated callers or free-plan users.
    if user is None:
        templates = [row for row in templates if not bool(row.get("premium", False))]
    return {
        "ok": True,
        "templates": templates,
        "total": len(templates),
    }


@app.get("/v1/sleep/overview")
async def sleep_overview(request: Request) -> dict[str, Any]:
    import asyncio
    _require_user(request)
    now_utc = utcnow().replace(microsecond=0)
    readiness_score = await asyncio.to_thread(_sleep_readiness_score, now_utc)
    return {
        "ok": True,
        "readiness_score": readiness_score,
        "readiness_explanation": _sleep_readiness_explanation(readiness_score),
        "recommended_scene": _recommended_scene_for_sleep_overview(now_utc),
        "pending_reminders": 0,
        "sensor_confidence": 100,
        "quick_actions": _sleep_quick_actions(now_utc),
        "last_updated": to_iso(now_utc),
    }


@app.post("/v1/scenes/compose")
def compose_scene(payload: SceneComposeRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    _require_premium_plan(request)
    trace_id = _request_trace_id(request)

    required_fields = {
        "name": str(payload.name or "").strip(),
        "light": payload.light if isinstance(payload.light, dict) else None,
        "audio": payload.audio if isinstance(payload.audio, dict) else None,
    }
    for field_name in ("name", "light", "audio"):
        value = required_fields[field_name]
        if (value is None) or (isinstance(value, str) and not value):
            return JSONResponse(
                status_code=422,
                content=_error_envelope(
                    trace_id=trace_id,
                    code=INVALID_SCENE_CONFIG,
                    message=f"Missing required field: {field_name}",
                ),
                headers={_TRACE_ID_HEADER: trace_id},
            )

    if bool(payload.premium):
        actor = _cookie_user(request)
        access = _subscription_gate().check_scene_access(
            user_id=str((actor or {}).get("user_id", "") or ""),
            scene_name=str(payload.name or "").strip(),
            scene_is_premium=True,
        )
        if not bool(access.get("allowed", False)):
            return JSONResponse(
                status_code=403,
                content=_error_envelope(
                    trace_id=trace_id,
                    code=UNAUTHORIZED,
                    message="Upgrade to premium to access this scene.",
                ),
                headers={_TRACE_ID_HEADER: trace_id},
            )

    previous_scene_state = _scene_store_snapshot()
    scene = scene_store.save_scene(
        {
            "name": str(payload.name or "").strip(),
            "light": dict(payload.light or {}),
            "audio": dict(payload.audio or {}),
            "premium": bool(payload.premium),
            "category": str(payload.category or "").strip(),
            "tags": [str(tag).strip() for tag in payload.tags if str(tag).strip()],
        }
    )

    undo_user = _cookie_user(request)
    undo_user_key = _user_profile_key(undo_user) if isinstance(undo_user, dict) else ""
    if undo_user_key:
        undo_manager.record_action(
            undo_user_key,
            "scene_compose",
            previous_scene_state,
            _scene_store_snapshot(),
        )

    return {
        "ok": True,
        "scene": scene,
        "applied_state": {
            "light": dict(scene.get("light", {})) if isinstance(scene.get("light", {}), dict) else {},
            "audio": dict(scene.get("audio", {})) if isinstance(scene.get("audio", {}), dict) else {},
            "activated_at": to_iso(utcnow().replace(microsecond=0)),
        },
    }


@app.post("/v1/actions/undo")
def undo_last_action(payload: UndoActionRequest, request: Request):
    _enforce_same_origin(request)
    user = _require_user(request)
    trace_id = _request_trace_id(request)
    user_id = _user_profile_key(user)

    action = undo_manager.pop_undo(user_id)
    if not isinstance(action, dict):
        return JSONResponse(
                status_code=404,
                content=_error_envelope(
                    trace_id=trace_id,
                    code=NOTHING_TO_UNDO,
                    message="No undo action found for this user.",
                ),
                headers={_TRACE_ID_HEADER: trace_id},
            )

    action_type = str(action.get("action_type", "") or "").strip()
    previous_state = action.get("previous_state")
    if action_type == "scene_compose":
        restored = _restore_scene_store_snapshot(previous_state)
        if not restored:
            return JSONResponse(
                status_code=500,
                content=_error_envelope(
                    trace_id=trace_id,
                    code=INTERNAL_ERROR,
                    message="Unable to restore previous scene state.",
                ),
                headers={_TRACE_ID_HEADER: trace_id},
            )
    elif action_type == "device_command" and isinstance(previous_state, dict):
        _save_profile(previous_state)
        _restore_mobile_db_snapshots_from_profile(
            user_id=user_id,
            profile_key=user_id,
            profile_state=previous_state,
            trace_id=trace_id,
        )

    return {
        "ok": True,
        "undone": action_type,
        "restored_state": previous_state,
        "message": "Action undone successfully.",
    }


@app.get("/v1/actions/undo/status")
def undo_action_status(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    action = undo_manager.get_undoable_action(key) if key else None
    if not isinstance(action, dict):
        return {
            "ok": True,
            "can_undo": False,
            "action_type": None,
            "seconds_remaining": None,
        }

    action_type = str(action.get("action_type", "") or "").strip() or None
    seconds_remaining = _undo_seconds_remaining(action)
    can_undo = action_type is not None and seconds_remaining is not None
    return {
        "ok": True,
        "can_undo": can_undo,
        "action_type": action_type if can_undo else None,
        "seconds_remaining": seconds_remaining if can_undo else None,
    }


@app.get("/v1/mobile/actions/undo/status")
def mobile_undo_action_status(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user key")

    action = undo_manager.get_undoable_action(key)
    if not isinstance(action, dict):
        return {
            "ok": True,
            "can_undo": False,
            "action_type": None,
            "seconds_remaining": None,
        }

    action_type = str(action.get("action_type", "") or "").strip() or None
    seconds_remaining = _undo_seconds_remaining(action)
    can_undo = action_type is not None and seconds_remaining is not None
    return {
        "ok": True,
        "can_undo": can_undo,
        "action_type": action_type if can_undo else None,
        "seconds_remaining": seconds_remaining if can_undo else None,
    }


@app.post("/v1/mobile/actions/undo")
def mobile_undo_last_action(request: Request):
    _enforce_same_origin(request)
    user = _require_user(request)
    key = _user_profile_key(user)
    trace_id = _request_trace_id(request)
    if not key:
        return JSONResponse(
            status_code=400,
            content=_error_envelope(
                trace_id=trace_id,
                code=VALIDATION_ERROR,
                message="Unable to identify user key.",
            ),
            headers={_TRACE_ID_HEADER: trace_id},
        )

    action = undo_manager.pop_undo(key)
    if not isinstance(action, dict):
        return JSONResponse(
            status_code=404,
            content=_error_envelope(
                trace_id=trace_id,
                code=NOTHING_TO_UNDO,
                message="No undo action found for this user.",
            ),
            headers={_TRACE_ID_HEADER: trace_id},
        )

    action_type = str(action.get("action_type", "") or "").strip()
    previous_state = action.get("previous_state")
    if action_type == "scene_compose":
        restored = _restore_scene_store_snapshot(previous_state)
        if not restored:
            return JSONResponse(
                status_code=500,
                content=_error_envelope(
                    trace_id=trace_id,
                    code=INTERNAL_ERROR,
                    message="Unable to restore previous scene state.",
                ),
                headers={_TRACE_ID_HEADER: trace_id},
            )
    elif action_type == "device_command" and isinstance(previous_state, dict):
        _save_profile(previous_state)
        _restore_mobile_db_snapshots_from_profile(
            user_id=str(user.get("user_id", "") or key),
            profile_key=key,
            profile_state=previous_state,
            trace_id=trace_id,
        )

    return {
        "ok": True,
        "undone": action_type,
        "restored_state": previous_state,
        "message": "Action undone successfully.",
    }


@app.post("/v1/subscriptions/trial/start")
def start_trial_subscription(payload: TrialStartRequest, request: Request):
    _enforce_same_origin(request)
    trace_id = _request_trace_id(request)
    user_id = str(payload.user_id or "").strip()
    if not user_id:
        return JSONResponse(
            status_code=400,
            content=_error_envelope(
                trace_id=trace_id,
                code=VALIDATION_ERROR,
                message="User ID is required.",
            ),
            headers={_TRACE_ID_HEADER: trace_id},
        )
    resolved_user_id = _resolve_subscription_actor_user_id(request, user_id)

    repo = _db_user_repository()
    user = repo.get_user_by_id(resolved_user_id)
    if user is None:
        return JSONResponse(
            status_code=404,
            content=_error_envelope(
                trace_id=trace_id,
                code=VALIDATION_ERROR,
                message="User not found.",
            ),
            headers={_TRACE_ID_HEADER: trace_id},
        )

    status_value = str(getattr(user, "subscription_status", "free") or "free").strip().lower()
    trial_already_used = bool(getattr(user, "trial_start_date", None))
    if trial_already_used or status_value in {"trial", "premium"}:
        return JSONResponse(
            status_code=409,
            content=_error_envelope(
                trace_id=trace_id,
                code=TRIAL_ALREADY_USED,
                message="Trial already activated.",
            ),
            headers={_TRACE_ID_HEADER: trace_id},
        )

    start_at = utcnow().replace(microsecond=0)
    end_at = start_at + timedelta(days=7)
    updated_user = repo.update_subscription(
        user_id=resolved_user_id,
        status="trial",
        trial_start=start_at,
        trial_end=end_at,
    )
    return {
        "ok": True,
        "trial_start": _to_iso_nullable(getattr(updated_user, "trial_start_date", start_at)),
        "trial_end": _to_iso_nullable(getattr(updated_user, "trial_end_date", end_at)),
        "days": 7,
        "message": "Your 7-day premium trial has started!",
    }


@app.get("/v1/subscriptions/status")
def subscription_status(request: Request, user_id: str = "") -> dict[str, Any]:
    resolved_user_id = _resolve_subscription_actor_user_id(request, user_id)
    payload = _subscription_status_payload(resolved_user_id)
    return {"ok": True, **payload}


@app.get("/v1/subscriptions/trial/status")
def trial_subscription_status(request: Request, user_id: str = "") -> dict[str, Any]:
    resolved_user_id = _resolve_subscription_actor_user_id(request, user_id)
    payload = _subscription_status_payload(resolved_user_id)
    return {
        "ok": True,
        "subscription_status": payload.get("subscription_status", "free"),
        "trial_active": bool(payload.get("trial_active", False)),
        "trial_days_remaining": payload.get("trial_days_remaining"),
        "trial_end_date": payload.get("trial_end_date"),
        "features": payload.get("features", _subscription_features("free")),
    }


def _subscription_checkout_session(session_id: str) -> dict[str, Any] | None:
    return store.get_checkout_session(session_id)


def _mobile_subscription_status_response(user_id: str) -> dict[str, Any]:
    base = _subscription_status_payload(user_id)
    checkout = store.get_subscription(user_id)
    return {
        "ok": True,
        "subscription_status": base.get("subscription_status", "free"),
        "trial_active": bool(base.get("trial_active", False)),
        "trial_days_remaining": base.get("trial_days_remaining"),
        "trial_end_date": base.get("trial_end_date"),
        "features": base.get("features", _subscription_features("free")),
        "plan_tier": str(checkout.get("tier", "free") or "free"),
        "billing_interval": str(checkout.get("interval", "monthly") or "monthly"),
        "payment_provider": str(checkout.get("payment_provider", "none") or "none"),
        "price_kwd": float(checkout.get("price_kwd", 0.0) or 0.0),
        "status": str(checkout.get("status", "active") or "active"),
        "next_renewal_at": str(checkout.get("next_renewal_at", "") or ""),
        "grace_end_at": str(checkout.get("grace_end_at", "") or ""),
        "provider_subscription_id": str(checkout.get("provider_subscription_id", "") or ""),
        "provider_plan_id": str(checkout.get("provider_plan_id", "") or ""),
        "provider_status": str(checkout.get("provider_status", "") or ""),
        "started_at": str(checkout.get("started_at", "") or ""),
        "last_payment_at": str(checkout.get("last_payment_at", "") or ""),
        "cancelled_at": str(checkout.get("cancelled_at", "") or ""),
    }


def _capture_mobile_checkout(
    *,
    user_id: str,
    checkout: dict[str, Any],
    payer_id: str = "",
    provider_order_id: str = "",
    provider_subscription_id: str = "",
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        updated_checkout = _billing_service().capture_checkout_session(
            session_id=str(checkout.get("session_id", "") or ""),
            user_id=user_id,
            payer_id=payer_id,
            provider_order_id=provider_order_id,
            provider_subscription_id=provider_subscription_id,
            raw_payload=raw_payload or {"session_id": str(checkout.get("session_id", "") or "")},
        )
    except BillingServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if str(updated_checkout.get("status", "") or "").strip().lower() == "completed":
        try:
            _db_user_repository().update_subscription(user_id=user_id, status="premium")
        except Exception as _exc:
            logger.warning("update_subscription premium failed user_id=%s err=%s", user_id, _exc)
    return {
        **_mobile_subscription_status_response(user_id),
        "checkout": updated_checkout,
    }


@app.get("/v1/mobile/subscription/status")
async def mobile_subscription_status(request: Request) -> dict[str, Any]:
    import asyncio
    user = _require_user(request)
    return await asyncio.to_thread(_mobile_subscription_status_response, str(user.get("user_id", "") or ""))


@app.get("/v1/mobile/plan")
def mobile_plan(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    status = _mobile_subscription_status_response(str(user.get("user_id", "") or ""))
    tier = str(status.get("plan_tier", "") or "").strip().lower()
    if tier == "standard":
        tier = "premium"
    if not tier:
        tier = "free"
    return {
        "ok": True,
        "plan": tier,
        "subscription": status,
    }


@app.get("/v1/mobile/subscription/history")
def mobile_subscription_history(request: Request, limit: int = 12) -> dict[str, Any]:
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    return {
        "ok": True,
        "events": store.list_payment_events(user_id, limit=limit),
    }


@app.post("/v1/mobile/subscription/checkout")
def mobile_subscription_checkout(
    payload: MobileSubscriptionCheckoutRequest,
    request: Request,
) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    checkout = _billing_service().create_checkout_session(
        user_id=user_id,
        tier=str(payload.tier or "standard"),
        interval=str(payload.interval or "monthly"),
        return_url=str(payload.return_url or "").strip(),
        cancel_url=str(payload.cancel_url or "").strip(),
        payer_email=str(user.get("email", "") or "").strip(),
    )
    return {"ok": True, "checkout": checkout}


@app.post("/v1/mobile/subscription/capture")
def mobile_subscription_capture(
    payload: MobileSubscriptionCaptureRequest,
    request: Request,
) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    checkout = _subscription_checkout_session(payload.session_id)
    if not isinstance(checkout, dict):
        raise HTTPException(status_code=404, detail="Checkout session not found")
    if str(checkout.get("user_id", "") or "").strip() != user_id:
        raise HTTPException(status_code=403, detail="Checkout session does not belong to this user")
    return _capture_mobile_checkout(
        user_id=user_id,
        checkout=checkout,
        payer_id=str(payload.payer_id or "").strip(),
        provider_order_id=str(payload.provider_order_id or "").strip(),
        provider_subscription_id=str(payload.provider_subscription_id or "").strip(),
        raw_payload={
            "session_id": str(payload.session_id or "").strip(),
            "provider_order_id": str(payload.provider_order_id or "").strip(),
            "provider_subscription_id": str(payload.provider_subscription_id or "").strip(),
            "source": "mobile_capture",
        },
    )


@app.post("/v1/mobile/subscription/cancel")
def mobile_subscription_cancel(
    payload: MobileSubscriptionCancelRequest,
    request: Request,
) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    checkout = _subscription_checkout_session(payload.session_id)
    if not isinstance(checkout, dict):
        raise HTTPException(status_code=404, detail="Checkout session not found")
    if str(checkout.get("user_id", "") or "").strip() != user_id:
        raise HTTPException(status_code=403, detail="Checkout session does not belong to this user")
    checkout = _billing_service().cancel_checkout_session(
        session_id=str(payload.session_id or "").strip(),
        user_id=user_id,
        reason="mobile_cancel",
    )
    return {
        **_mobile_subscription_status_response(user_id),
        "message": "Checkout was cancelled.",
        "checkout": checkout,
    }


@app.post("/v1/mobile/subscription/pause")
def mobile_subscription_pause(
    payload: MobileSubscriptionActionRequest,
    request: Request,
) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    try:
        _billing_service().pause_active_subscription(
            user_id=user_id,
            reason=str(payload.reason or "").strip() or "Paused by user",
        )
    except BillingServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        _db_user_repository().update_subscription(user_id=user_id, status="premium")
    except Exception as _exc:
        logger.warning("update_subscription premium (pause) failed user_id=%s err=%s", user_id, _exc)
    return {
        **_mobile_subscription_status_response(user_id),
        "message": "Subscription paused.",
    }


@app.post("/v1/mobile/subscription/cancel-active")
def mobile_subscription_cancel_active(
    payload: MobileSubscriptionActionRequest,
    request: Request,
) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    try:
        _billing_service().cancel_active_subscription(
            user_id=user_id,
            reason=str(payload.reason or "").strip() or "Cancelled by user",
        )
    except BillingServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        _db_user_repository().update_subscription(user_id=user_id, status="free")
    except Exception as _exc:
        logger.warning("update_subscription free (cancel) failed user_id=%s err=%s", user_id, _exc)
    return {
        **_mobile_subscription_status_response(user_id),
        "message": "Subscription cancelled.",
    }


@app.get("/billing/paypal/approve")
def billing_paypal_approve(
    session_id: str = "",
    token: str = "",
    ba_token: str = "",
    subscription_id: str = "",
    PayerID: str = "",
):
    checkout = _subscription_checkout_session(session_id)
    if not isinstance(checkout, dict):
        raise HTTPException(status_code=404, detail="Checkout session not found")
    user_id = str(checkout.get("user_id", "") or "").strip()
    provider_subscription_id = (
        str(subscription_id or "").strip()
        or str(ba_token or "").strip()
        or str(token or "").strip()
    )
    result = _capture_mobile_checkout(
        user_id=user_id,
        checkout=checkout,
        payer_id=str(PayerID or "").strip(),
        provider_order_id=str(token or "").strip(),
        provider_subscription_id=provider_subscription_id,
        raw_payload={
            "session_id": session_id,
            "provider_order_id": str(token or "").strip(),
            "provider_subscription_id": provider_subscription_id,
            "payer_id": str(PayerID or "").strip(),
            "source": "paypal_approve_redirect",
        },
    )
    return_url = str(checkout.get("return_url", "") or "").strip()
    payment_state = (
        "success"
        if str(result.get("checkout", {}).get("status", "") or "").strip().lower() == "completed"
        else "pending"
    )
    if return_url:
        separator = "&" if "?" in return_url else "?"
        return RedirectResponse(
            url=f"{return_url}{separator}payment={payment_state}&session_id={session_id}",
            status_code=302,
        )
    return result


@app.get("/billing/paypal/cancel")
def billing_paypal_cancel(session_id: str = ""):
    checkout = _subscription_checkout_session(session_id)
    if not isinstance(checkout, dict):
        raise HTTPException(status_code=404, detail="Checkout session not found")
    user_id = str(checkout.get("user_id", "") or "").strip()
    _billing_service().cancel_checkout_session(
        session_id=session_id,
        user_id=user_id,
        reason="paypal_cancel_redirect",
    )
    cancel_url = str(checkout.get("cancel_url", "") or "").strip()
    if cancel_url:
        separator = "&" if "?" in cancel_url else "?"
        return RedirectResponse(
            url=f"{cancel_url}{separator}payment=cancelled&session_id={session_id}",
            status_code=302,
        )
    return {
        **_mobile_subscription_status_response(user_id),
        "message": "Checkout was cancelled.",
    }


@app.post("/v1/billing/paypal/webhook")
async def billing_paypal_webhook(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid webhook JSON payload") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Webhook payload must be a JSON object")

    try:
        result = _billing_service().handle_paypal_webhook(
            headers={str(key): str(value) for key, value in request.headers.items()},
            payload=payload,
        )
    except BillingServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_event = result.event_type.strip().lower()
    if not result.duplicate:
        if normalized_event in {
            "checkout.completed",
            "payment.succeeded",
            "subscription.renewed",
            "billing.subscription.activated",
            "billing.subscription.re-activated",
            "billing.subscription.renewed",
            "payment.sale.completed",
        }:
            try:
                _db_user_repository().update_subscription(user_id=result.user_id, status="premium")
            except Exception as _exc:
                logger.warning("webhook update_subscription premium failed user_id=%s err=%s", result.user_id, _exc)
        elif normalized_event in {
            "billing.subscription.cancelled",
            "billing.subscription.expired",
            "subscription.cancelled",
            "subscription.expired",
        }:
            try:
                _db_user_repository().update_subscription(user_id=result.user_id, status="free")
            except Exception as _exc:
                logger.warning("webhook update_subscription free failed user_id=%s err=%s", result.user_id, _exc)
    return {
        **_mobile_subscription_status_response(result.user_id),
        "verified": result.verified,
        "event_type": result.event_type,
        "checkout_session_id": result.checkout_session_id,
        "duplicate": result.duplicate,
        "replayed": result.replayed,
        "webhook_event_id": result.webhook_event_id,
        "transmission_id": result.transmission_id,
        "idempotency_key": result.idempotency_key,
    }


@app.get("/v1/mobile/settings")
async def mobile_settings(request: Request) -> dict[str, Any]:
    import asyncio
    user = _require_user(request)
    profile = await asyncio.to_thread(_safe_profile)
    if not isinstance(profile, dict):
        profile = {}
    resolved = _resolved_user_settings(profile, user)
    return {"ok": True, "settings": resolved}


@app.post("/v1/mobile/settings")
def upsert_mobile_settings(payload: UserSettingsRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    key = str(user.get("user_id", "")).strip() or str(user.get("email", "")).strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user settings key")

    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        settings_map = profile.get("web_settings", {})
        if not isinstance(settings_map, dict):
            settings_map = {}
        normalized = _normalize_user_settings(payload.model_dump())
        settings_map[key] = normalized
        profile["web_settings"] = settings_map
        _save_profile(profile)

    _event("info", "user_settings_saved", user_id=str(user.get("user_id", "")), key=key)
    return {"ok": True, "settings": normalized}


def _mobile_auth_response(user: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "user": {
            "user_id": str(user.get("user_id", "") or ""),
            "email": str(user.get("email", "") or ""),
            "name": str(user.get("name", "") or ""),
            "client_name": str(tokens.get("client_name", "") or ""),
        },
        "access_token": str(tokens.get("access_token", "") or ""),
        "token_type": str(tokens.get("token_type", "Bearer") or "Bearer"),
        "expires_at": str(tokens.get("expires_at", "") or ""),
        "expires_in": int(tokens.get("expires_in", 0) or 0),
        "refresh_token": str(tokens.get("refresh_token", "") or ""),
        "refresh_expires_at": str(tokens.get("refresh_expires_at", "") or ""),
    }


def _issue_mobile_auth_tokens_for_user(user: dict[str, Any], *, client_name: str = "flutter_app") -> dict[str, Any]:
    tokens = _db_mobile_auth_repository().issue_tokens(
        user_id=str(user.get("user_id", "") or ""),
        client_name=str(client_name or "flutter_app").strip() or "flutter_app",
    )
    return _mobile_auth_response(user, tokens)


def _db_user_to_mobile_user_payload(db_user: Any, *, client_name: str = "") -> dict[str, Any]:
    return {
        "user_id": str(getattr(db_user, "id", "") or ""),
        "email": str(getattr(db_user, "email", "") or ""),
        "name": str(getattr(db_user, "full_name", "") or ""),
        "client_name": str(client_name or ""),
    }


def _legacy_user_by_email(email: str) -> dict[str, Any] | None:
    email_key = str(email or "").strip().lower()
    if not email_key:
        return None
    users = store.db.get("users", [])
    if not isinstance(users, list):
        return None
    for row in users:
        if not isinstance(row, dict):
            continue
        if str(row.get("email", "") or "").strip().lower() == email_key:
            return row
    return None


def _ensure_legacy_store_user_shadow(user: dict[str, Any], *, password_hash: str = "") -> None:
    user_id = str(user.get("user_id", "") or "").strip()
    email = str(user.get("email", "") or "").strip().lower()
    if not user_id or not email:
        return

    name = str(user.get("name", "") or "").strip()
    hash_value = str(password_hash or "").strip() or "mobile_shadow_managed"
    now_iso = _now_utc_iso()
    changed = False

    users = store.db.get("users", [])
    if not isinstance(users, list):
        users = []
        store.db["users"] = users
        changed = True

    match: dict[str, Any] | None = None
    for row in users:
        if not isinstance(row, dict):
            continue
        row_user_id = str(row.get("user_id", "") or "").strip()
        row_email = str(row.get("email", "") or "").strip().lower()
        if row_user_id == user_id or row_email == email:
            match = row
            break

    if match is None:
        users.append(
            {
                "user_id": user_id,
                "email": email,
                "name": name,
                "password_hash": hash_value,
                "created_at": now_iso,
            }
        )
        changed = True
    else:
        if str(match.get("user_id", "") or "").strip() != user_id:
            match["user_id"] = user_id
            changed = True
        if str(match.get("email", "") or "").strip().lower() != email:
            match["email"] = email
            changed = True
        if str(match.get("name", "") or "").strip() != name:
            match["name"] = name
            changed = True
        if str(match.get("password_hash", "") or "").strip() != hash_value:
            match["password_hash"] = hash_value
            changed = True
        if not str(match.get("created_at", "") or "").strip():
            match["created_at"] = now_iso
            changed = True

    subscriptions = store.db.get("subscriptions", [])
    if not isinstance(subscriptions, list):
        subscriptions = []
        store.db["subscriptions"] = subscriptions
        changed = True
    has_subscription = any(str(row.get("user_id", "") or "").strip() == user_id for row in subscriptions if isinstance(row, dict))
    if not has_subscription:
        subscriptions.append(
            {
                "user_id": user_id,
                "tier": "free",
                "interval": "monthly",
                "status": "active",
                "payment_provider": "none",
                "price_kwd": 0.0,
                "next_renewal_at": "",
                "grace_end_at": "",
                "updated_at": now_iso,
            }
        )
        changed = True

    if changed:
        store.save()


def _register_mobile_user_db_first(email: str, password: str, name: str) -> dict[str, Any]:
    repo = _db_user_repository()
    if repo.get_user_by_email(email) is not None:
        raise ValueError("Email already registered")

    # If a legacy user already owns this email, treat it as existing account.
    if isinstance(_legacy_user_by_email(email), dict):
        raise ValueError("Email already registered")

    password_hash = store.hash_password(password)
    created = repo.create_user(
        email=email,
        password_hash=password_hash,
        full_name=name or None,
    )
    payload = _db_user_to_mobile_user_payload(created)
    _ensure_legacy_store_user_shadow(payload, password_hash=password_hash)
    return payload


# ── Account-level brute-force lockout (Redis-backed) ─────────────────────────
# IP-level rate limiting is handled by RateLimitMiddleware; this provides
# per-account lockout so a distributed attack against one account is blocked
# even if each attacker IP stays under the IP rate limit.

_LOGIN_MAX_FAILURES = 5        # failures before lockout
_LOGIN_LOCKOUT_SECONDS = 900   # 15-minute lockout window
_LOGIN_WINDOW_SECONDS = 900    # rolling window to count failures

_redis_lockout_client = None
_redis_lockout_lock = threading.Lock()


def _get_lockout_redis():
    """Return a sync Redis client for lockout counters, or None if unavailable."""
    global _redis_lockout_client
    if _redis_lockout_client is not None:
        return _redis_lockout_client
    with _redis_lockout_lock:
        if _redis_lockout_client is not None:
            return _redis_lockout_client
        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            return None
        try:
            import redis as _redis_lib
            client = _redis_lib.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
            client.ping()
            _redis_lockout_client = client
        except Exception:
            return None
    return _redis_lockout_client


def _lockout_key(email: str) -> str:
    import hashlib
    return "login_fail:" + hashlib.sha256(email.encode()).hexdigest()[:32]


def _is_account_locked(email: str) -> bool:
    """Return True if this account has too many recent failures."""
    r = _get_lockout_redis()
    if r is None:
        return False
    try:
        count = r.get(_lockout_key(email))
        return count is not None and int(count) >= _LOGIN_MAX_FAILURES
    except Exception:
        return False


def _record_login_failure(email: str) -> int:
    """Increment failure counter; return new count. Sets TTL on first hit."""
    r = _get_lockout_redis()
    if r is None:
        return 0
    try:
        key = _lockout_key(email)
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _LOGIN_WINDOW_SECONDS, nx=True)
        results = pipe.execute()
        return int(results[0])
    except Exception:
        return 0


def _clear_login_failures(email: str) -> None:
    """Remove lockout key on successful login."""
    r = _get_lockout_redis()
    if r is None:
        return
    try:
        r.delete(_lockout_key(email))
    except Exception:
        pass


def _login_mobile_user_db_first(email: str, password: str) -> dict[str, Any] | None:
    repo = _db_user_repository()
    db_user = repo.get_user_by_email(email)
    if db_user is not None:
        stored_hash = str(getattr(db_user, "password_hash", "") or "")
        if not store.check_password(password, stored_hash):
            return None
        payload = _db_user_to_mobile_user_payload(db_user)
        _ensure_legacy_store_user_shadow(payload, password_hash=stored_hash)
        return payload

    # Migration fallback: allow login for legacy-only users, then mirror to DB.
    legacy_user = store.authenticate_user(email, password)
    if not isinstance(legacy_user, dict):
        return None

    _ensure_db_user_shadow(legacy_user)
    synced = repo.get_user_by_id(str(legacy_user.get("user_id", "") or "").strip()) or repo.get_user_by_email(email)
    if synced is not None:
        payload = _db_user_to_mobile_user_payload(synced)
    else:
        payload = {
            "user_id": str(legacy_user.get("user_id", "") or ""),
            "email": str(legacy_user.get("email", "") or ""),
            "name": str(legacy_user.get("name", "") or ""),
            "client_name": "",
        }
    _ensure_legacy_store_user_shadow(payload, password_hash=str(legacy_user.get("password_hash", "") or ""))
    return payload


@app.post("/v1/mobile/auth/register")
def mobile_auth_register(payload: MobileRegisterRequest, request: Request) -> dict[str, Any]:
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    name = (payload.name or "").strip()
    client_name = str(payload.client_name or "flutter_app").strip() or "flutter_app"
    import re as _re
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="A valid email address is required")
    if len(email) > 254:
        raise HTTPException(status_code=422, detail="Email address is too long")
    if len(password) < 10:
        raise HTTPException(status_code=422, detail="Password must be at least 10 characters")
    if not _re.search(r"[A-Z]", password):
        raise HTTPException(status_code=422, detail="Password must contain at least one uppercase letter")
    if not _re.search(r"[0-9]", password):
        raise HTTPException(status_code=422, detail="Password must contain at least one number")
    if len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be 128 characters or fewer")
    try:
        user = _register_mobile_user_db_first(email=email, password=password, name=name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    tokens = _db_mobile_auth_repository().issue_tokens(
        user_id=str(user.get("user_id", "") or ""),
        client_name=client_name,
    )
    _event("info", "mobile_register_success", user_id=str(user.get("user_id", "")), email=email, client_name=client_name)
    return _mobile_auth_response(user, tokens)


@app.post("/v1/mobile/auth/login")
def mobile_auth_login(payload: MobileLoginRequest, request: Request) -> dict[str, Any]:
    email = str(payload.email or "").strip().lower()
    if _is_account_locked(email):
        _event("warning", "mobile_login_locked", email=email)
        raise HTTPException(status_code=429, detail="Account temporarily locked due to too many failed attempts. Try again in 15 minutes.")
    user = _login_mobile_user_db_first(email=email, password=payload.password or "")
    if not user:
        failures = _record_login_failure(email)
        _event("warning", "mobile_login_failed", email=email, failures=failures)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _clear_login_failures(email)
    client_name = str(payload.client_name or "flutter_app").strip() or "flutter_app"
    tokens = _db_mobile_auth_repository().issue_tokens(
        user_id=str(user.get("user_id", "") or ""),
        client_name=client_name,
    )
    _event("info", "mobile_login_success", user_id=str(user.get("user_id", "")), email=user.get("email", ""), client_name=client_name)
    return _mobile_auth_response(user, tokens)


@app.post("/v1/mobile/auth/otp/request")
def mobile_auth_request_otp(payload: MobileOtpRequestRequest, request: Request) -> dict[str, Any]:
    phone_number = _normalize_phone_number(payload.phone_number)
    if not phone_number:
        raise HTTPException(status_code=422, detail="A valid phone_number is required")

    now = ensure_utc(utcnow())
    expires_dt = (now + timedelta(seconds=_MOBILE_OTP_TTL_SECONDS)).replace(microsecond=0)
    expires_at = to_iso(expires_dt)
    client_name = str(payload.client_name or "flutter_app").strip() or "flutter_app"
    otp_code = f"{secrets.randbelow(1000000):06d}"
    request_id = f"otp_{secrets.token_hex(10)}"

    from database import OtpRepository
    otp_repo = OtpRepository()
    otp_repo.cleanup_expired()

    delivery_result = _mobile_send_otp_code(phone_number, otp_code, request_id)
    delivery_provider = str(delivery_result.get("provider", "simulated") or "simulated")
    delivery_status = str(delivery_result.get("status", "accepted") or "accepted")
    delivery_message_id = str(delivery_result.get("message_id", "") or "")

    otp_repo.create(
        request_id=request_id,
        phone_number=phone_number,
        otp_digest=_otp_hmac_digest(
            phone_number=phone_number,
            request_id=request_id,
            otp_code=otp_code,
        ),
        expires_at=expires_dt,
        client_name=client_name,
        delivery_provider=delivery_provider,
        delivery_status=delivery_status,
        delivery_message_id=delivery_message_id,
    )

    _event(
        "info",
        "mobile_otp_requested",
        phone=_mask_phone_number(phone_number),
        client_name=client_name,
        delivery=delivery_provider,
    )
    response: dict[str, Any] = {
        "ok": True,
        "request_id": request_id,
        "phone_number_masked": _mask_phone_number(phone_number),
        "expires_in": _MOBILE_OTP_TTL_SECONDS,
        "expires_at": expires_at,
        "delivery": delivery_provider,
    }
    if _mobile_otp_debug_enabled():
        response["debug_code"] = otp_code
    return response


@app.post("/v1/mobile/auth/otp/verify")
def mobile_auth_verify_otp(payload: MobileOtpVerifyRequest, request: Request) -> dict[str, Any]:
    request_id = str(payload.request_id or "").strip()
    phone_number = _normalize_phone_number(payload.phone_number)
    otp_code = "".join(ch for ch in str(payload.otp_code or "").strip() if ch.isdigit())
    client_name = str(payload.client_name or "flutter_app").strip() or "flutter_app"
    if not request_id:
        raise HTTPException(status_code=422, detail="request_id is required")
    if not phone_number:
        raise HTTPException(status_code=422, detail="A valid phone_number is required")
    if len(otp_code) < 4:
        raise HTTPException(status_code=422, detail="otp_code must be at least 4 digits")

    from database import OtpRepository
    otp_repo = OtpRepository()

    row = otp_repo.get(request_id)
    if not row:
        raise HTTPException(status_code=401, detail="OTP request is invalid or expired")

    now = ensure_utc(utcnow())
    expires_at = row["expires_at"]
    if (not isinstance(expires_at, datetime)) or ensure_utc(expires_at) < now:
        otp_repo.delete(request_id)
        raise HTTPException(status_code=401, detail="OTP request is expired")

    expected_phone = _normalize_phone_number(row.get("phone_number"))
    if expected_phone != phone_number:
        raise HTTPException(status_code=401, detail="OTP phone number does not match")

    attempts = int(row.get("attempts", 0) or 0)
    if attempts >= _MOBILE_OTP_MAX_ATTEMPTS:
        otp_repo.delete(request_id)
        raise HTTPException(status_code=429, detail="OTP attempts exceeded. Request a new code.")

    expected_digest = str(row.get("otp_digest", "") or "")
    actual_digest = _otp_hmac_digest(
        phone_number=phone_number,
        request_id=request_id,
        otp_code=otp_code,
    )
    if (not expected_digest) or (not hmac.compare_digest(expected_digest, actual_digest)):
        otp_repo.increment_attempts(request_id)
        raise HTTPException(status_code=401, detail="OTP code is invalid")

    otp_repo.delete(request_id)

    user: dict[str, Any] | None = None
    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}

        phone_users = _get_scoped_profile_section(profile, "mobile_phone_users")
        mapped = phone_users.get(phone_number, {})
        mapped_user_id = ""
        if isinstance(mapped, dict):
            mapped_user_id = str(mapped.get("user_id", "") or "").strip()
        elif isinstance(mapped, str):
            mapped_user_id = mapped.strip()

        user = _mobile_user_payload_by_id(mapped_user_id) if mapped_user_id else None
        if user is None:
            resolved_name = str(payload.name or "").strip() or f"Phone user {phone_number[-4:]}"
            user = _ensure_external_identity_user(
                email=_phone_shadow_email(phone_number),
                name=resolved_name,
                password_hash="mobile_phone_auth",
            )
            mapped_user_id = str(user.get("user_id", "") or "")

        phone_users[phone_number] = {
            "user_id": mapped_user_id,
            "updated_at": _now_utc_iso(),
        }
        profile["mobile_phone_users"] = phone_users
        _save_profile(profile)

    _event(
        "info",
        "mobile_otp_verified",
        user_id=str(user.get("user_id", "") or ""),
        phone=_mask_phone_number(phone_number),
        client_name=client_name,
    )
    return _issue_mobile_auth_tokens_for_user(user, client_name=client_name)


@app.post("/v1/mobile/auth/social")
def mobile_auth_social_login(payload: MobileSocialLoginRequest, request: Request) -> dict[str, Any]:
    provider = str(payload.provider or "").strip().lower()
    client_name = str(payload.client_name or "flutter_app").strip() or "flutter_app"
    verified_identity = _verify_mobile_social_identity(payload)
    provider_user_id = str(verified_identity.get("provider_user_id", "") or "").strip()
    if not provider_user_id:
        raise HTTPException(status_code=401, detail="Social provider identity could not be verified")
    verification_method = str(verified_identity.get("verification_method", "") or "").strip()

    provided_email = str(payload.email or "").strip().lower()
    if provided_email and "@" not in provided_email:
        raise HTTPException(status_code=422, detail="email must be valid")
    verified_email = str(verified_identity.get("email", "") or "").strip().lower()
    verified_name = str(verified_identity.get("name", "") or "").strip()

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    identity_section = _get_scoped_profile_section(profile, "mobile_social_identities")
    identity_key = f"{provider}:{_sanitize_identity_value(provider_user_id, max_len=72)}"
    mapped = identity_section.get(identity_key, {})
    mapped_user_id = ""
    mapped_email = ""
    if isinstance(mapped, dict):
        mapped_user_id = str(mapped.get("user_id", "") or "").strip()
        mapped_email = str(mapped.get("email", "") or "").strip().lower()

    user = _mobile_user_payload_by_id(mapped_user_id) if mapped_user_id else None
    if user is None:
        email_candidate = verified_email or provided_email or mapped_email or _social_shadow_email(provider, provider_user_id)
        user = _ensure_external_identity_user(
            email=email_candidate,
            name=str(payload.name or "").strip() or verified_name or provider.title(),
            password_hash="mobile_social_auth",
        )

    identity_section[identity_key] = {
        "provider": provider,
        "provider_user_id": _sanitize_identity_value(provider_user_id, max_len=72),
        "user_id": str(user.get("user_id", "") or ""),
        "email": str(user.get("email", "") or ""),
        "email_verified": bool(verified_identity.get("email_verified", False)),
        "verification_method": verification_method or "token_verified",
        "last_verified_at": _now_utc_iso(),
        "updated_at": _now_utc_iso(),
    }
    profile["mobile_social_identities"] = identity_section
    _save_profile(profile)

    _event(
        "info",
        "mobile_social_login_success",
        provider=provider,
        user_id=str(user.get("user_id", "") or ""),
        client_name=client_name,
        verification_method=verification_method or "token_verified",
    )
    response = _issue_mobile_auth_tokens_for_user(user, client_name=client_name)
    response["social_provider"] = provider
    response["social_verification"] = verification_method or "token_verified"
    return response


@app.post("/v1/mobile/auth/refresh")
def mobile_auth_refresh(payload: MobileRefreshRequest, request: Request) -> dict[str, Any]:
    refresh_token = str(payload.refresh_token or "").strip()
    if not refresh_token:
        raise HTTPException(status_code=422, detail="refresh_token is required")
    tokens = _db_mobile_auth_repository().refresh_tokens(refresh_token)
    if not isinstance(tokens, dict) or not tokens:
        # Compatibility path for older sessions issued before DB-backed mobile auth.
        _log("warning", "mobile_token_refresh_db_miss", reason="token_not_found_or_expired_in_db")
        tokens = store.refresh_mobile_access_token(refresh_token)
    if not isinstance(tokens, dict) or not tokens:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")

    user = _mobile_user_from_access_token(str(tokens.get("access_token", "") or ""))
    if not isinstance(user, dict):
        user = store.validate_mobile_access_token(str(tokens.get("access_token", "") or ""))
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Unable to restore mobile session")
    _ensure_db_user_shadow(user)
    _event("info", "mobile_token_refreshed", user_id=str(user.get("user_id", "")), client_name=str(tokens.get("client_name", "") or ""))
    return _mobile_auth_response(user, tokens)


@app.post("/v1/mobile/auth/logout")
def mobile_auth_logout(payload: MobileLogoutRequest, request: Request) -> dict[str, Any]:
    access_token = _bearer_token(request)
    refresh_token = str(payload.refresh_token or "").strip()
    revoked_db = _db_mobile_auth_repository().revoke_tokens(access_token=access_token, refresh_token=refresh_token)
    revoked_legacy = store.revoke_mobile_tokens(access_token=access_token, refresh_token=refresh_token)
    return {"ok": True, "revoked": bool(revoked_db or revoked_legacy)}


@app.get("/v1/mobile/auth/me")
def mobile_auth_me(request: Request) -> dict[str, Any]:
    user = _mobile_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "ok": True,
        "user": {
            "user_id": str(user.get("user_id", "") or ""),
            "email": str(user.get("email", "") or ""),
            "name": str(user.get("name", "") or ""),
            "client_name": str(user.get("client_name", "") or ""),
        },
    }


@app.get("/v1/mobile/routine")
async def mobile_routine(request: Request) -> dict[str, Any]:
    import asyncio
    user = _require_user(request)
    profile = await asyncio.to_thread(_safe_profile)
    defaults = _normalize_user_routine({"bedtime": "22:30", "wake": "07:00", "weekends": True})
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_routines")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    return {"ok": True, "routine": _normalize_user_routine({**defaults, **scoped})}


@app.post("/v1/mobile/push-token")
def register_push_token(payload: RegisterPushTokenRequest, request: Request) -> dict[str, Any]:
    """Store the user's Expo push token so the backend can send notifications."""
    _enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or user.get("email", "")).strip()
    token = str(payload.expo_token or "").strip()
    platform = str(payload.platform or "android").strip().lower()
    if not token:
        raise HTTPException(status_code=400, detail="expo_token is required")

    # Persist in DB
    try:
        from database.models import UserPushToken
        from sqlalchemy import select
        conn = _database_connection()
        with conn.get_session() as session:
            existing = session.execute(
                select(UserPushToken).where(UserPushToken.user_id == user_id)
            ).scalar_one_or_none()
            if existing is None:
                session.add(UserPushToken(user_id=user_id, expo_token=token, platform=platform))
            else:
                existing.expo_token = token
                existing.platform = platform
    except Exception as exc:
        logger.warning("push-token DB write failed: %s", exc)

    # Also persist in the JSON file used by ExpoPushSender (for backwards compat)
    try:
        from notifications.expo_sender import ExpoPushSender
        ExpoPushSender().register_token(user_id=user_id, expo_token=token, platform=platform)
    except Exception as exc:
        logger.warning("push-token JSON write failed: %s", exc)

    _event("info", "push_token_registered", user_id=user_id, platform=platform)
    return {"ok": True, "registered": True}


@app.post("/v1/mobile/routine")
def upsert_mobile_routine(payload: UserRoutineRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user routine key")

    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        section = _get_scoped_profile_section(profile, "web_routines")
        normalized = _normalize_user_routine(payload.model_dump())
        section[key] = normalized
        profile["web_routines"] = section
        _save_profile(profile)

    _event("info", "user_routine_saved", user_id=str(user.get("user_id", "")), key=key)
    return {"ok": True, "routine": normalized}


@app.get("/v1/mobile/profile")
async def mobile_profile(request: Request) -> dict[str, Any]:
    import asyncio
    user = _require_user(request)
    profile = await asyncio.to_thread(_safe_profile)
    defaults = _normalize_user_profile_prefs({
        "display_name": "",
        "timezone": "Asia/Kuwait",
        "push_enabled": True,
        "email_enabled": False,
        "location_mode": "auto",
        "country_code": "KW",
        "city": "",
        "theme_mode": "system",
    })
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_profile_prefs")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    resolved = _normalize_user_profile_prefs({**defaults, **scoped})
    return {
        "ok": True,
        "profile": resolved,
        "resolved_display_name": _resolved_user_display_name(user, resolved),
        "resolved_location": _profile_location_summary(resolved),
    }


@app.post("/v1/mobile/profile")
def upsert_mobile_profile(payload: UserProfilePrefsRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user profile key")

    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}
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


@app.get("/v1/mobile/islamic/overview")
def mobile_islamic_overview(request: Request) -> dict[str, Any]:
    user = _require_premium_plan(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    overview = _mobile_islamic_overview_payload(user, profile)
    return {"ok": True, **overview}


@app.get("/v1/mobile/islamic/prayer-times")
def mobile_islamic_prayer_times(request: Request) -> dict[str, Any]:
    user = _require_premium_plan(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    _, prayer_bundle, location, _ = _mobile_prayer_service_for_user(user, profile)
    return {
        "ok": True,
        "prayers": prayer_bundle.get("prayers", {}) if isinstance(prayer_bundle, dict) else {},
        "location": location,
    }


@app.get("/v1/mobile/islamic/next-prayer")
def mobile_islamic_next_prayer(request: Request) -> dict[str, Any]:
    user = _require_premium_plan(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    service, _, location, _ = _mobile_prayer_service_for_user(user, profile)
    next_prayer = service.get_next_prayer()
    return {
        "ok": True,
        "next_prayer": next_prayer,
        "location": location,
        "led_color": service.get_prayer_led_color(str(next_prayer.get("name", "") or "")),
    }


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


@app.get("/v1/mobile/bed/pairing")
def mobile_bed_pairing_status(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "mobile_bed_links")
    link_row = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}

    device_id = str(link_row.get("device_id", "") or "").strip()
    if not device_id:
        return {
            "ok": True,
            "paired": False,
            "device_id": "",
            "bed_location": "",
            "paired_at": "",
            "provisioning_verified": False,
        }

    status_payload: dict[str, Any] = {}
    try:
        from qr_code.pair_device import get_device_status

        status_payload = get_device_status(device_id)
    except Exception:
        status_payload = {}

    return {
        "ok": True,
        "paired": bool(status_payload.get("success", False) and status_payload.get("paired", False)),
        "device_id": device_id,
        "bed_location": str(
            status_payload.get("bed_location", "")
            or link_row.get("bed_location", "")
            or ""
        ),
        "paired_at": str(
            status_payload.get("paired_at", "")
            or link_row.get("paired_at", "")
            or ""
        ),
        "provisioning_verified": bool(link_row.get("provisioning_verified", False)),
    }


@app.post("/v1/mobile/bed/pair")
def mobile_bed_pair(payload: MobileBedPairRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    device_id = _extract_device_id_from_qr_payload(
        payload.qr_payload,
        fallback_device_id=payload.device_id,
    )
    if not device_id:
        raise HTTPException(status_code=422, detail="device_id is required in qr_payload or device_id")
    claim_token = _extract_claim_token_from_qr_payload(
        payload.qr_payload,
        fallback_claim_token=payload.claim_token,
    )

    bed_location = str(payload.bed_location or "Kuwait").strip() or "Kuwait"
    registered_device: dict[str, Any] = {}
    try:
        registered_device = _load_registered_qr_device(
            device_id,
            bed_location=bed_location,
            auto_create=_mobile_pairing_allow_auto_register(),
        )
        from qr_code.pair_device import get_device_status, pair_device
    except Exception as exc:
        raise HTTPException(status_code=500, detail="QR pairing service unavailable") from exc

    if not isinstance(registered_device, dict) or not str(registered_device.get("device_id", "")).strip():
        raise HTTPException(status_code=404, detail="Device is not provisioned for pairing")
    if not _pairing_claim_matches_device(registered_device, claim_token):
        raise HTTPException(status_code=401, detail="Pairing claim token is invalid or missing")

    user_id = str(user.get("user_id", "") or "").strip()
    user_name = str(user.get("name", "") or "").strip() or _email_local_part(str(user.get("email", "") or "")) or "Mobile User"
    pair_result = pair_device(
        device_id=device_id,
        user_id=user_id,
        user_name=user_name,
    )
    if not bool(pair_result.get("success", False)):
        status_payload = get_device_status(device_id)
        current_owner = str(status_payload.get("user_id", "") or "").strip()
        if not current_owner or current_owner != user_id:
            raise HTTPException(status_code=409, detail=str(pair_result.get("message", "Unable to pair bed"))[:180])

    status_payload = get_device_status(device_id)
    if not bool(status_payload.get("success", False)):
        raise HTTPException(status_code=500, detail="Pairing status could not be confirmed")

    key = _user_profile_key(user)
    links = _get_scoped_profile_section(profile, "mobile_bed_links")
    links[key] = {
        "device_id": device_id,
        "bed_location": str(status_payload.get("bed_location", "") or bed_location),
        "paired_at": str(status_payload.get("paired_at", "") or _now_utc_iso()),
        "provisioning_verified": True,
        "updated_at": _now_utc_iso(),
    }
    profile["mobile_bed_links"] = links
    _save_profile(profile)

    return {
        "ok": True,
        "paired": bool(status_payload.get("paired", False)),
        "device_id": device_id,
        "bed_location": str(status_payload.get("bed_location", "") or bed_location),
        "paired_at": str(status_payload.get("paired_at", "") or ""),
        "provisioning_verified": True,
    }


@app.post("/v1/mobile/bed/unpair")
def mobile_bed_unpair(payload: MobileBedUnpairRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    links = _get_scoped_profile_section(profile, "mobile_bed_links")
    link_row = links.get(key, {}) if key and isinstance(links.get(key, {}), dict) else {}
    device_id = _extract_device_id_from_qr_payload(
        "",
        fallback_device_id=str(payload.device_id or "").strip() or str(link_row.get("device_id", "") or ""),
    )
    if not device_id:
        raise HTTPException(status_code=422, detail="No paired device found")

    try:
        from qr_code.pair_device import get_device_status, unpair_device
    except Exception as exc:
        raise HTTPException(status_code=500, detail="QR pairing service unavailable") from exc

    status_payload = get_device_status(device_id)
    if bool(status_payload.get("success", False)):
        owner_id = str(status_payload.get("user_id", "") or "").strip()
        if owner_id and owner_id != str(user.get("user_id", "") or "").strip():
            raise HTTPException(status_code=403, detail="Cannot unpair a bed linked to another account")

    result = unpair_device(device_id)
    if not bool(result.get("success", False)):
        raise HTTPException(status_code=404, detail=str(result.get("message", "Device not found"))[:180])

    links.pop(key, None)
    profile["mobile_bed_links"] = links
    _save_profile(profile)
    return {"ok": True, "paired": False, "device_id": device_id}


@app.get("/v1/mobile/alarms")
def mobile_alarms(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "mobile_alarm_schedules")
    rows = section.get(key, []) if key and isinstance(section.get(key, []), list) else []
    timezone_name = str(_chat_profile_prefs_for_user(profile, user).get("timezone", "Asia/Kuwait") or "Asia/Kuwait")
    alarms = _serialize_mobile_alarm_rows(rows, timezone_name=timezone_name)
    return {"ok": True, "alarms": alarms}


@app.post("/v1/mobile/alarms")
def mobile_upsert_alarm(payload: MobileAlarmUpsertRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "mobile_alarm_schedules")
    existing_rows = section.get(key, []) if key and isinstance(section.get(key, []), list) else []
    normalized_existing = _serialize_mobile_alarm_rows(existing_rows, timezone_name="UTC")

    target_alarm_id = str(payload.alarm_id or "").strip()
    now_iso = _now_utc_iso()
    normalized_alarm = _normalize_mobile_alarm(
        payload.model_dump(),
        existing_alarm_id=target_alarm_id,
        now_iso=now_iso,
    )

    replaced = False
    next_rows: list[dict[str, Any]] = []
    for row in normalized_existing:
        if str(row.get("alarm_id", "") or "") == str(normalized_alarm.get("alarm_id", "") or ""):
            normalized_alarm["created_at"] = str(row.get("created_at", "") or normalized_alarm.get("created_at", ""))
            next_rows.append(normalized_alarm)
            replaced = True
        else:
            next_rows.append(row)

    if not replaced:
        if len(next_rows) >= _MOBILE_ALARM_MAX_ITEMS:
            raise HTTPException(status_code=409, detail=f"Alarm limit reached ({_MOBILE_ALARM_MAX_ITEMS})")
        next_rows.append(normalized_alarm)

    section[key] = next_rows
    profile["mobile_alarm_schedules"] = section
    _save_profile(profile)

    timezone_name = str(_chat_profile_prefs_for_user(profile, user).get("timezone", "Asia/Kuwait") or "Asia/Kuwait")
    alarms = _serialize_mobile_alarm_rows(next_rows, timezone_name=timezone_name)
    target = next(
        (row for row in alarms if str(row.get("alarm_id", "") or "") == str(normalized_alarm.get("alarm_id", "") or "")),
        normalized_alarm,
    )
    return {"ok": True, "alarm": target, "alarms": alarms}


@app.post("/v1/mobile/alarms/{alarm_id}/toggle")
def mobile_toggle_alarm(alarm_id: str, payload: MobileAlarmToggleRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    key = _user_profile_key(user)
    target_id = str(alarm_id or "").strip()

    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        section = _get_scoped_profile_section(profile, "mobile_alarm_schedules")
        rows = section.get(key, []) if key and isinstance(section.get(key, []), list) else []
        updated = False
        next_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = _normalize_mobile_alarm(
                row,
                existing_alarm_id=str(row.get("alarm_id", "") or ""),
                now_iso=str(row.get("updated_at", "") or _now_utc_iso()),
            )
            if str(normalized.get("alarm_id", "") or "") == target_id:
                normalized["enabled"] = bool(payload.enabled)
                normalized["updated_at"] = _now_utc_iso()
                updated = True
            next_rows.append(normalized)

        if not updated:
            raise HTTPException(status_code=404, detail="Alarm not found")

        section[key] = next_rows
        profile["mobile_alarm_schedules"] = section
        _save_profile(profile)

    return {"ok": True, "alarm_id": target_id, "enabled": bool(payload.enabled)}


@app.delete("/v1/mobile/alarms/{alarm_id}")
def mobile_delete_alarm(alarm_id: str, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    key = _user_profile_key(user)
    target_id = str(alarm_id or "").strip()

    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        section = _get_scoped_profile_section(profile, "mobile_alarm_schedules")
        rows = section.get(key, []) if key and isinstance(section.get(key, []), list) else []
        next_rows = [
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("alarm_id", "") or "").strip() != target_id
        ]
        if len(next_rows) == len(rows):
            raise HTTPException(status_code=404, detail="Alarm not found")
        section[key] = next_rows
        profile["mobile_alarm_schedules"] = section
        _save_profile(profile)

    return {"ok": True, "deleted_alarm_id": target_id}


@app.get("/v1/mobile/spotify/auth-url")
def mobile_spotify_auth_url(request: Request, done_uri: str = "") -> dict[str, Any]:
    user = _require_user(request)
    config = _spotify_env_config(request)
    if not _spotify_is_configured(config, require_redirect_uri=True):
        missing = _spotify_missing_config_fields(config, require_redirect_uri=True)
        raise HTTPException(status_code=503, detail=f"Spotify OAuth is not configured: {', '.join(missing)}")

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user Spotify key")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    state = _spotify_create_oauth_state(
        profile=profile,
        user_key=key,
        done_uri=done_uri,
    )
    if not state:
        raise HTTPException(status_code=500, detail="Unable to initialize Spotify OAuth state")
    return {"ok": True, "auth_url": _spotify_auth_url(config, state)}


@app.get("/v1/mobile/spotify/connect")
def mobile_spotify_connect(request: Request):
    done_uri = _safe_mobile_done_uri(str(request.query_params.get("done_uri", "") or ""))
    safe_base_redirect = done_uri or "/user-dashboard"
    safe_error_redirect = _append_query_params(safe_base_redirect, {"spotify": "error"})

    user = _mobile_user_from_query_access_token(request) or _authenticated_user(request)
    if not isinstance(user, dict):
        if done_uri:
            return RedirectResponse(
                url=_append_query_params(done_uri, {"spotify": "error", "reason": "unauthenticated"}),
                status_code=302,
            )
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

    state = _spotify_create_oauth_state(
        profile=profile,
        user_key=key,
        done_uri=done_uri,
    )
    if not state:
        return RedirectResponse(url=f"{safe_error_redirect}&reason=state_init_failed", status_code=302)

    return RedirectResponse(url=_spotify_auth_url(config, state), status_code=302)


@app.get("/v1/mobile/spotify/callback")
def mobile_spotify_callback(request: Request, code: str = "", state: str = ""):
    default_error_redirect = "/user-dashboard?spotify=error"
    if not code or not state:
        return RedirectResponse(url=f"{default_error_redirect}&reason=missing_code_or_state", status_code=302)

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    states = _get_scoped_profile_section(profile, "spotify_oauth_state")
    matched_key = ""
    done_uri = ""
    for candidate_key, row in states.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("state", "")).strip() == state.strip():
            matched_key = str(candidate_key)
            done_uri = _safe_mobile_done_uri(str(row.get("done_uri", "") or ""))
            break

    safe_base_redirect = done_uri or "/user-dashboard"
    safe_error_redirect = _append_query_params(safe_base_redirect, {"spotify": "error"})
    safe_success_redirect = _append_query_params(safe_base_redirect, {"spotify": "connected"})

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
        if done_uri:
            return RedirectResponse(
                url=_append_query_params(done_uri, {"spotify": "error", "reason": "exchange_failed"}),
                status_code=302,
            )
        return RedirectResponse(url=f"/user-dashboard?{redirect_qs}", status_code=302)

    from database import SpotifyTokenRepository
    SpotifyTokenRepository().upsert(
        matched_key,
        access_token=access_token,
        refresh_token=str(token_payload.get("refresh_token", "") or ""),
        expires_at=_spotify_expires_at(token_payload.get("expires_in", 3600)),
        scope=str(token_payload.get("scope", "") or ""),
        spotify_user_id=str(spotify_profile.get("id", "") or ""),
        display_name=str(spotify_profile.get("display_name", "") or ""),
        spotify_email=str(spotify_profile.get("email", "") or ""),
    )

    states.pop(matched_key, None)
    profile["spotify_oauth_state"] = states
    _save_profile(profile)
    return RedirectResponse(url=safe_success_redirect, status_code=302)


@app.get("/v1/mobile/spotify/status")
def mobile_spotify_status(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user Spotify key")

    user_email = str(user.get("email", "") or "").strip().lower()
    token = _spotify_refresh_user_token_if_needed(key, user_email=user_email)
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

    from database import SpotifyTokenRepository
    SpotifyTokenRepository().delete(key)
    return {"ok": True}


@app.get("/v1/mobile/spotify/playback-status")
def mobile_spotify_playback_status(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user Spotify key")

    user_email = str(user.get("email", "") or "").strip().lower()
    token = _spotify_refresh_user_token_if_needed(key, user_email=user_email)
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

    user_email = str(user.get("email", "") or "").strip().lower()
    token = _spotify_refresh_user_token_if_needed(key, user_email=user_email)
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
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user device control key")

    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}
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
    trace_id = _request_trace_id(request)
    if not isinstance(profile, dict):
        profile = {}
    section = _get_scoped_profile_section(profile, "web_timeline")
    scoped = section.get(key, []) if key else []
    if key:
        items = _mobile_timeline_items_db_first(
            str(user.get("user_id", "") or key),
            scoped if isinstance(scoped, list) else [],
            trace_id=trace_id,
        )
    else:
        items = _normalize_timeline_items(scoped if isinstance(scoped, list) else [])
    profile_dirty = False

    if key:
        commands, changed = _progress_user_commands(
            profile,
            key,
            user_id=str(user.get("user_id", "") or key),
        )
        command_map = {str(c.get("id", "")): c for c in commands if str(c.get("id", ""))}
        items = _apply_command_status_to_timeline(items, command_map)
        if changed and commands:
            _store_last_command_result(profile, key, _build_last_command_result_from_command(commands[0]))
            profile_dirty = True
        if changed:
            cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
            cmd_section[key] = commands
            profile["web_device_commands"] = cmd_section
            profile_dirty = True
    now = utcnow()
    resolved_settings = _resolved_user_settings(profile, user)
    drift_enabled = bool(resolved_settings.get("bedtime_drift_automation_enabled", True))
    drift_row, drift_marked = (
        _bedtime_drift_timeline_item(profile, now_utc=now)
        if drift_enabled
        else (None, False)
    )
    quiet_row = _quiet_hours_status_timeline_item(profile, user, now_utc=now)
    cooldown_rows = _automation_cooldown_timeline_items(now_utc=now)
    if drift_row:
        items = [drift_row] + items
    if drift_marked:
        profile_dirty = True
    if cooldown_rows:
        pinned_cooldowns: list[dict[str, Any]] = []
        normalized_cooldowns = _normalize_timeline_items(cooldown_rows)
        for idx, row in enumerate(normalized_cooldowns):
            pinned_cooldowns.append(_with_min_timeline_priority(row, 98 - min(idx, 6)))
        items = pinned_cooldowns + items
    if quiet_row:
        items = [_with_min_timeline_priority(quiet_row, 99)] + items

    if not items:
        items = _default_user_timeline()
    normalized_items = _prioritize_timeline_items(items, limit=20)
    if profile_dirty:
        _save_profile(profile)
    return {"ok": True, "items": normalized_items}


@app.get("/v1/mobile/first-3-nights")
def mobile_first_3_nights(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user checklist key")

    with _profile_rw():
        profile = _safe_profile()
        commands, changed = _progress_user_commands(
            profile,
            key,
            user_id=str(user.get("user_id", "") or key),
        )
        if changed:
            cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
            cmd_section[key] = commands
            profile["web_device_commands"] = cmd_section
            if commands:
                _store_last_command_result(profile, key, _build_last_command_result_from_command(commands[0]))
            _save_profile(profile)

        checklist, _ = _sync_first_3_nights_state(profile, user, commands=commands)

    return {"ok": True, "checklist": checklist}


@app.post("/v1/mobile/first-3-nights/complete")
def mobile_first_3_nights_complete(payload: FirstThreeNightsStepRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user checklist key")

    checklist, changed = _sync_first_3_nights_state(
        profile,
        user,
        mark_step_key=str(payload.step_key or "").strip(),
    )
    _event(
        "info",
        "first_3_nights_step_completed",
        user_id=str(user.get("user_id", "")),
        step_key=str(payload.step_key or ""),
        changed=changed,
    )
    return {"ok": True, "checklist": checklist}


@app.post("/v1/mobile/nightly-summary/feedback")
def mobile_nightly_summary_feedback(payload: NightlySummaryFeedbackRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user feedback key")

    feedback, _ = _record_nightly_summary_feedback(
        profile,
        key,
        vote=str(payload.vote or "").strip(),
        summary_generated_at_utc=str(payload.summary_generated_at_utc or "").strip(),
    )
    _event(
        "info",
        "nightly_summary_feedback_recorded",
        user_id=str(user.get("user_id", "")),
        vote=str(payload.vote or ""),
    )
    return {"ok": True, "feedback": feedback}


@app.post("/v1/mobile/device-commands/{command_id}/feedback")
def mobile_device_command_feedback(
    command_id: str,
    payload: DeviceCommandFeedbackRequest,
    request: Request,
) -> dict[str, Any]:
    _enforce_same_origin(request)
    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user feedback key")
    command_key = str(command_id or "").strip()
    if not command_key:
        raise HTTPException(status_code=400, detail="Command id is required")

    trace_id = _request_trace_id(request)
    commands, changed = _progress_user_commands(
        profile,
        key,
        user_id=str(user.get("user_id", "") or key),
    )
    profile_dirty = False
    if changed:
        cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
        cmd_section[key] = commands
        profile["web_device_commands"] = cmd_section
        if commands:
            _store_last_command_result(profile, key, _build_last_command_result_from_command(commands[0]))
        profile_dirty = True

    target = next((row for row in commands if str(row.get("id", "") or "") == command_key), None)
    if not isinstance(target, dict):
        try:
            db_rows = _db_command_repository().get_recent_commands(key, limit=400)
        except Exception:
            db_rows = []
        target = next(
            (
                _normalize_command_item(row if isinstance(row, dict) else {})
                for row in db_rows
                if str((row if isinstance(row, dict) else {}).get("command_id", "") or "") == command_key
            ),
            None,
        )
    if not isinstance(target, dict):
        raise HTTPException(status_code=404, detail="Command not found")

    feedback, feedback_changed = _record_command_feedback(
        profile,
        key,
        command_id=command_key,
        command_action=str(target.get("action", "") or ""),
        vote=str(payload.vote or ""),
        note=str(payload.note or ""),
        trace_id=trace_id,
    )
    if profile_dirty or feedback_changed:
        _save_profile(profile)

    _event(
        "info",
        "device_command_feedback_recorded",
        trace_id=trace_id,
        user_id=str(user.get("user_id", "")),
        command_id=command_key,
        command_action=str(target.get("action", "") or ""),
        vote=str(payload.vote or ""),
    )
    return {
        "ok": True,
        "command_id": command_key,
        "feedback": feedback,
    }


@app.get("/v1/mobile/beta/metrics")
def mobile_beta_metrics(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    profile = _safe_profile()
    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user metrics key")

    commands, changed = _progress_user_commands(
        profile,
        key,
        user_id=str(user.get("user_id", "") or key),
    )
    profile_dirty = False
    if changed:
        cmd_section = _get_scoped_profile_section(profile, "web_device_commands")
        cmd_section[key] = commands
        profile["web_device_commands"] = cmd_section
        if commands:
            _store_last_command_result(profile, key, _build_last_command_result_from_command(commands[0]))
        profile_dirty = True

    checklist, _ = _sync_first_3_nights_state(profile, user, commands=commands)

    feedback = _nightly_summary_feedback_payload(_nightly_summary_feedback_for_user(profile, key))
    command_feedback = _command_feedback_payload(_command_feedback_for_user(profile, key))
    metrics = _beta_metrics_payload(
        checklist=checklist,
        commands=commands,
        feedback=feedback,
        command_feedback=command_feedback,
        user_id=key,
    )
    try:
        _db_beta_progress_repository().upsert_beta_metrics_snapshot(key, metrics)
    except Exception as exc:
        emit_json_log(
            logger,
            level="warning",
            event_type="beta_metrics_snapshot_write_failed",
            trace_id="web_runtime",
            metadata={"error_type": type(exc).__name__},
        )

    if profile_dirty:
        _save_profile(profile)
    return {
        "ok": True,
        "metrics": metrics,
        "checklist": checklist,
        "nightly_summary_feedback": feedback,
        "automation_feedback": command_feedback,
    }


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
    trace_id = _request_trace_id(request)
    scene_is_premium = bool(scene_entry.get("premium", False))

    if scene_is_premium:
        gate_user_id = str(user.get("user_id", "") or "").strip()
        access = _subscription_gate().check_scene_access(
            user_id=gate_user_id,
            scene_name=scene_label,
            scene_is_premium=True,
        )
        if not bool(access.get("allowed", False)):
            return JSONResponse(
                status_code=403,
                content=_error_envelope(
                    trace_id=trace_id,
                    code=UNAUTHORIZED,
                    message="Upgrade to premium to save this scene tonight.",
                ),
                headers={_TRACE_ID_HEADER: trace_id},
            )

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
    timeline_row = {
        "time": "Now",
        "event": f"Scene saved for tonight: {scene_label}",
        "status": "ready",
        "command_id": "",
    }
    rows.insert(0, timeline_row)
    timeline_section[key] = rows[:20]
    profile["web_timeline"] = timeline_section

    _save_profile(profile)
    _persist_mobile_timeline_item(
        user_id=str(user.get("user_id", "") or key),
        item=timeline_row,
        trace_id=trace_id,
    )

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
        "premium": scene_is_premium,
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
    previous_profile_state = deepcopy(profile)

    action_key = str(payload.action or "").strip().lower()
    catalog = _user_action_catalog()
    entry = catalog.get(action_key)
    if not entry:
        raise HTTPException(status_code=400, detail="Unsupported user action")

    key = _user_profile_key(user)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user action key")
    request_trace_id = _request_trace_id(request)
    wind_down_minutes_for_response: int | None = None

    if action_key == "winddown":
        sleep = profile.get("sleep", {}) if isinstance(profile.get("sleep", {}), dict) else {}
        resolved = _resolved_user_settings(profile, user)
        wind_down_minutes_for_response = int(resolved.get("wind_down_minutes", 45) or 45)
        wind_down_minutes_for_response = max(15, min(120, wind_down_minutes_for_response))
        wind_down_started_at_utc = utcnow().replace(microsecond=0)
        wind_down_target_end_utc = wind_down_started_at_utc + timedelta(
            minutes=wind_down_minutes_for_response
        )
        bedtime_history = (
            sleep.get("bedtime_history", [])
            if isinstance(sleep.get("bedtime_history", []), list)
            else []
        )
        bedtime_history.append(to_iso(wind_down_started_at_utc))
        sleep["wind_down_enabled"] = True
        sleep["wind_down_minutes"] = wind_down_minutes_for_response
        sleep["wind_down_started_at_utc"] = to_iso(wind_down_started_at_utc)
        sleep["wind_down_target_end_utc"] = to_iso(wind_down_target_end_utc)
        sleep["bedtime_history"] = bedtime_history[-60:]
        profile["sleep"] = sleep
        _record_winddown_session_to_db(
            user_id=str(user.get("user_id", "") or key),
            started_at_utc=wind_down_started_at_utc,
        )

        controls_section = _get_scoped_profile_section(profile, "web_device_controls")
        current_controls = _normalize_device_controls(controls_section.get(key, {}))
        target_light_level = max(18, min(45, int(round(45 - (wind_down_minutes_for_response / 6)))))
        controls_section[key] = _normalize_device_controls(
            {
                **current_controls,
                "lights_on": True,
                "audio_on": True,
                "alarm_on": True,
                "light_level": target_light_level,
            }
        )
        profile["web_device_controls"] = controls_section

    if action_key == "quiet_hours_override":
        prefs = profile.get("preferences", {}) if isinstance(profile.get("preferences", {}), dict) else {}
        profile["preferences"] = prefs
        now_iso = _now_utc_iso()
        override_until_utc = _compute_quiet_hours_override_until_utc(profile, user, now_utc=utcnow())
        prefs["quiet_hours_override_until_utc"] = override_until_utc

        section = _get_scoped_profile_section(profile, "web_timeline")
        rows = section.get(key, []) if isinstance(section.get(key, []), list) else []
        rows = _normalize_timeline_items(rows)
        timeline_row = {
            "time": "Now",
            "event": "Quiet hours override enabled",
            "status": "override",
            "command_id": "",
        }
        rows.insert(0, timeline_row)
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
        _persist_mobile_timeline_item(
            user_id=str(user.get("user_id", "") or key),
            item=timeline_row,
            trace_id=request_trace_id,
        )
        undo_manager.record_action(key, "device_command", previous_profile_state, deepcopy(profile))

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
            "timeline": _mobile_timeline_items_db_first(
                str(user.get("user_id", "") or key),
                section[key],
                trace_id=request_trace_id,
            ),
        }

    command_id = f"cmd_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
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
    queued_row = {
        "time": datetime.now().strftime("%H:%M"),
        "event": str(entry.get("event", "Action triggered")),
        "status": "queued",
        "command_id": command_id,
    }
    rows.insert(0, queued_row)
    timeline_rows_to_persist = [queued_row]
    if action_key == "winddown" and wind_down_minutes_for_response is not None:
        winddown_row = {
            "time": "Now",
            "event": f"Wind-down routine armed ({wind_down_minutes_for_response} min target)",
            "status": "active",
            "command_id": "",
        }
        rows.insert(1, winddown_row)
        timeline_rows_to_persist.append(winddown_row)
    section[key] = rows[:20]
    profile["web_timeline"] = section
    last_command_result = _store_last_command_result(
        profile,
        key,
        _build_last_command_result_from_command(command),
    )
    _save_profile(profile)
    _persist_mobile_command_record(
        user_id=str(user.get("user_id", "") or key),
        command=command,
    )
    for timeline_row in timeline_rows_to_persist:
        _persist_mobile_timeline_item(
            user_id=str(user.get("user_id", "") or key),
            item=timeline_row,
            trace_id=request_trace_id,
        )
    undo_manager.record_action(key, "device_command", previous_profile_state, deepcopy(profile))

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
        "message": (
            f"Wind-down autopilot is now active for {wind_down_minutes_for_response} minute(s)."
            if action_key == "winddown" and wind_down_minutes_for_response is not None
            else str(entry.get("message", "Action completed."))
        ),
        "timeline": _mobile_timeline_items_db_first(
            str(user.get("user_id", "") or key),
            section[key],
            trace_id=request_trace_id,
        ),
    }


@app.get("/v1/mobile/device-commands/{command_id}")
def mobile_device_command_status(command_id: str, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    key = _user_profile_key(user)
    trace_id = _request_trace_id(request)
    if not key:
        raise HTTPException(status_code=400, detail="Unable to identify user action key")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    commands, changed = _progress_user_commands(
        profile,
        key,
        user_id=str(user.get("user_id", "") or key),
    )
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
    timeline_rows = _mobile_timeline_items_db_first(
        str(user.get("user_id", "") or key),
        rows,
        trace_id=trace_id,
    )
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
    user = _require_user(request)
    profile = _safe_profile()
    hardware = profile.get("hardware", {}) if isinstance(profile, dict) else {}
    key = _user_profile_key(user)
    bed_links = _get_scoped_profile_section(profile, "mobile_bed_links")
    link_row = bed_links.get(key, {}) if key and isinstance(bed_links.get(key, {}), dict) else {}
    alarms_section = _get_scoped_profile_section(profile, "mobile_alarm_schedules")
    alarms = alarms_section.get(key, []) if key and isinstance(alarms_section.get(key, []), list) else []
    alarm_count = sum(1 for row in alarms if isinstance(row, dict))

    return {
        "firmware_version": "1.0.0",
        "device_status": "online",
        "user_strip_pin": hardware.get("user_strip_pin", 18),
        "state_strip_pin": hardware.get("state_strip_pin", 13),
        "user_strip_led_count": hardware.get("user_strip_led_count", 120),
        "state_strip_led_count": hardware.get("state_strip_led_count", 60),
        "paired_device_id": str(link_row.get("device_id", "") or ""),
        "paired_at": str(link_row.get("paired_at", "") or ""),
        "paired_bed_location": str(link_row.get("bed_location", "") or ""),
        "provisioning_verified": bool(link_row.get("provisioning_verified", False)),
        "alarm_count": int(alarm_count),
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


@app.get("/v1/admin/billing/timeline")
def admin_billing_timeline(
    request: Request,
    limit: int = 50,
    only_failures: bool = False,
    user_query: str = "",
    status_query: str = "",
) -> dict[str, Any]:
    _require_admin(request)
    rows = store.list_payment_events_admin(
        limit=limit,
        only_failures=only_failures,
        user_filter=user_query,
        status_filter=status_query,
    )
    failures = sum(1 for row in rows if bool(row.get("is_failure")))
    successes = sum(1 for row in rows if not bool(row.get("is_failure")))
    latest_at = str(rows[0].get("created_at", "") or "") if rows else ""
    provider_mix: dict[str, int] = {}
    for row in rows:
        key = str(row.get("payment_provider", "") or "unknown").strip().lower() or "unknown"
        provider_mix[key] = int(provider_mix.get(key, 0)) + 1
    return {
        "ok": True,
        "summary": {
            "total_events": len(rows),
            "failure_events": failures,
            "success_events": successes,
            "latest_event_at": latest_at,
            "provider_mix": provider_mix,
        },
        "items": rows,
    }


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


@app.get("/v1/admin/mobile/beta-acceptance")
def admin_mobile_beta_acceptance(
    request: Request,
    max_testers: int = 5,
    min_required: int = 3,
) -> dict[str, Any]:
    _require_admin(request)
    report = _beta_acceptance_cohort_report(
        max_testers=max_testers,
        min_required=min_required,
    )
    return {"ok": True, "report": report}


@app.get("/v1/admin/mobile/beta-cohort")
def admin_mobile_beta_cohort(
    request: Request,
    cohort_key: str = "kuwait_beta",
    target_min: int = 10,
    target_max: int = 15,
    max_rows: int = 50,
) -> dict[str, Any]:
    _require_admin(request)
    report = _beta_cohort_progress_report(
        cohort_key=cohort_key,
        target_min=target_min,
        target_max=target_max,
        max_rows=max_rows,
    )
    return {"ok": True, "report": report}


@app.post("/v1/admin/mobile/beta-cohort/enroll")
def admin_mobile_beta_cohort_enroll(payload: BetaCohortEnrollRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    admin = _require_admin(request)

    user_id = str(payload.user_id or "").strip()
    email = str(payload.email or "").strip().lower()
    user_repo = _db_user_repository()
    user = user_repo.get_user_by_id(user_id) if user_id else None
    if user is None and email:
        user = user_repo.get_user_by_email(email)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found for beta cohort enrollment")

    resolved_user_id = str(getattr(user, "id", "") or "").strip()
    if not resolved_user_id:
        raise HTTPException(status_code=400, detail="Unable to resolve user id for cohort enrollment")

    member = _db_beta_progress_repository().upsert_cohort_member(
        user_id=resolved_user_id,
        cohort_key=str(payload.cohort_key or "kuwait_beta"),
        country_code=str(payload.country_code or "KW"),
        status=str(payload.status or "active"),
        source=str(payload.source or "admin_manual"),
        notes=str(payload.notes or ""),
    )
    report = _beta_cohort_progress_report(
        cohort_key=str(member.get("cohort_key", "kuwait_beta") or "kuwait_beta"),
    )
    _event(
        "info",
        "admin_beta_cohort_enrolled",
        actor=str(admin.get("user_id", "") or ""),
        user_id=resolved_user_id,
        cohort_key=str(member.get("cohort_key", "") or ""),
        status=str(member.get("status", "") or ""),
    )
    return {
        "ok": True,
        "member": member,
        "report": report,
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


# ── Update Manager routes ──────────────────────────────────────────────────────

@app.get("/v1/admin/versions")
def admin_list_versions(request: Request) -> dict[str, Any]:
    _require_admin(request)
    app_versions = _db_update_repository().list_app_versions(limit=100)
    firmware_versions = _db_update_repository().list_firmware_versions(limit=100)
    return {"ok": True, "app_versions": app_versions, "firmware_versions": firmware_versions}


@app.post("/v1/admin/versions/app")
def admin_publish_app_version(payload: PublishAppVersionRequest, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    result = _db_update_repository().create_app_version(
        platform=payload.platform,
        version_string=payload.version_string,
        build_number=payload.build_number,
        changelog=payload.changelog,
        is_required=payload.is_required,
        rollout_percent=payload.rollout_percent,
        min_supported_version=payload.min_supported_version or None,
        store_url_ios=payload.store_url_ios or None,
        store_url_android=payload.store_url_android or None,
        published_by=str(admin.get("email", "") or admin.get("user_id", "")),
    )
    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=role,
        action="publish_app_version",
        resource="app_versions",
        details={"version": payload.version_string, "platform": payload.platform},
    )
    return {"ok": True, "version": result}


@app.post("/v1/admin/versions/firmware")
def admin_publish_firmware_version(payload: PublishFirmwareVersionRequest, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    result = _db_update_repository().create_firmware_version(
        version_string=payload.version_string,
        changelog=payload.changelog,
        download_url=payload.download_url,
        is_required=payload.is_required,
        rollout_percent=payload.rollout_percent,
        target_device_ids=payload.target_device_ids,
        published_by=str(admin.get("email", "") or admin.get("user_id", "")),
    )
    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=role,
        action="publish_firmware_version",
        resource="firmware_versions",
        details={"version": payload.version_string},
    )
    return {"ok": True, "version": result}


@app.patch("/v1/admin/versions/{version_id}")
def admin_patch_version(version_id: str, payload: PatchVersionRequest, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    fields: dict[str, Any] = {}
    if payload.rollout_percent is not None:
        fields["rollout_percent"] = max(0, min(100, int(payload.rollout_percent)))
    if payload.is_required is not None:
        fields["is_required"] = bool(payload.is_required)
    if payload.is_active is not None:
        fields["is_active"] = bool(payload.is_active)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = _db_update_repository().update_app_version(version_id, **fields)
    if result is None:
        result = _db_update_repository().update_firmware_version(version_id, **fields)
    if result is None:
        raise HTTPException(status_code=404, detail="Version not found")
    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=role,
        action="patch_version",
        resource=f"version:{version_id}",
        details=fields,
    )
    return {"ok": True, "version": result}


# ── Feature Flag routes ────────────────────────────────────────────────────────

@app.get("/v1/admin/feature-flags")
def admin_list_feature_flags(request: Request) -> dict[str, Any]:
    _require_admin(request)
    flags = _db_feature_flag_repository().list_flags()
    return {"ok": True, "flags": flags}


@app.post("/v1/admin/feature-flags")
def admin_upsert_feature_flag(payload: UpsertFeatureFlagRequest, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    result = _db_feature_flag_repository().upsert_flag(
        flag_key=payload.flag_key,
        display_name=payload.display_name,
        description=payload.description,
        enabled_globally=payload.enabled_globally,
        enabled_for_plans=payload.enabled_for_plans,
        rollout_percent=payload.rollout_percent,
        updated_by=str(admin.get("email", "") or admin.get("user_id", "")),
    )
    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=role,
        action="upsert_feature_flag",
        resource=f"flag:{payload.flag_key}",
        details={"enabled_globally": payload.enabled_globally, "rollout_percent": payload.rollout_percent},
    )
    return {"ok": True, "flag": result}


@app.patch("/v1/admin/feature-flags/{flag_key}")
def admin_patch_feature_flag(flag_key: str, payload: PatchFeatureFlagRequest, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    existing = _db_feature_flag_repository().get_flag(flag_key)
    if existing is None:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    result = _db_feature_flag_repository().upsert_flag(
        flag_key=flag_key,
        display_name=existing["display_name"],
        description=existing["description"],
        enabled_globally=payload.enabled_globally if payload.enabled_globally is not None else existing["enabled_globally"],
        enabled_for_plans=payload.enabled_for_plans if payload.enabled_for_plans is not None else existing["enabled_for_plans"],
        rollout_percent=payload.rollout_percent if payload.rollout_percent is not None else existing["rollout_percent"],
        updated_by=str(admin.get("email", "") or admin.get("user_id", "")),
    )
    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=role,
        action="patch_feature_flag",
        resource=f"flag:{flag_key}",
        details={k: v for k, v in payload.model_dump().items() if v is not None},
    )
    return {"ok": True, "flag": result}


# ── User feature override routes ───────────────────────────────────────────────

@app.get("/v1/admin/users/{user_id}/features")
def admin_get_user_features(user_id: str, request: Request) -> dict[str, Any]:
    _require_admin(request)
    flags = _db_feature_flag_repository().list_flags()
    overrides = {o["flag_key"]: o for o in _db_feature_flag_repository().list_user_overrides(user_id)}
    merged = []
    for f in flags:
        key = f["flag_key"]
        override = overrides.get(key)
        merged.append({**f, "override": override})
    return {"ok": True, "user_id": user_id, "flags": merged}


@app.post("/v1/admin/users/{user_id}/features")
def admin_set_user_feature(user_id: str, payload: SetUserFeatureOverrideRequest, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    result = _db_feature_flag_repository().set_user_override(
        user_id=user_id,
        flag_key=payload.flag_key,
        override_value=payload.override_value,
        reason=payload.reason,
        set_by=str(admin.get("email", "") or admin.get("user_id", "")),
    )
    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=role,
        action="set_user_feature_override",
        resource=f"user:{user_id}:flag:{payload.flag_key}",
        details={"override_value": payload.override_value, "reason": payload.reason},
    )
    return {"ok": True, "override": result}


@app.delete("/v1/admin/users/{user_id}/features/{flag_key}")
def admin_delete_user_feature(user_id: str, flag_key: str, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    deleted = _db_feature_flag_repository().delete_user_override(user_id=user_id, flag_key=flag_key)
    return {"ok": True, "deleted": deleted}


# ── Admin user management routes ───────────────────────────────────────────────

@app.get("/v1/admin/users")
def admin_list_users(
    request: Request,
    search: str = "",
    status: str = "",
    page: int = 1,
    limit: int = 25,
) -> dict[str, Any]:
    _require_admin(request)
    safe_limit = max(1, min(int(limit or 25), 100))
    safe_page = max(1, int(page or 1))
    all_users = store.list_all_users()
    filtered = []
    search_lower = str(search or "").strip().lower()
    status_lower = str(status or "").strip().lower()
    for u in all_users:
        if not isinstance(u, dict):
            continue
        if search_lower:
            haystack = (str(u.get("email", "")) + " " + str(u.get("name", "") or u.get("full_name", ""))).lower()
            if search_lower not in haystack:
                continue
        if status_lower:
            if str(u.get("subscription_status", "free") or "free").lower() != status_lower:
                continue
        filtered.append(u)
    total = len(filtered)
    start = (safe_page - 1) * safe_limit
    page_items = filtered[start: start + safe_limit]
    items = []
    for u in page_items:
        uid = str(u.get("user_id", "") or u.get("id", "") or "")
        items.append({
            "user_id": uid,
            "email": str(u.get("email", "") or ""),
            "name": str(u.get("name", "") or u.get("full_name", "") or ""),
            "subscription_status": str(u.get("subscription_status", "free") or "free"),
            "created_at": str(u.get("created_at", "") or ""),
            "trial_end_date": str(u.get("trial_end_date", "") or ""),
        })
    return {
        "ok": True,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
        "pages": max(1, math.ceil(total / safe_limit)),
        "items": items,
    }


@app.get("/v1/admin/users/{user_id}/detail")
def admin_get_user_detail(user_id: str, request: Request) -> dict[str, Any]:
    _require_admin(request)
    u = store.get_user(user_id)
    if not isinstance(u, dict):
        raise HTTPException(status_code=404, detail="User not found")
    overrides = _db_feature_flag_repository().list_user_overrides(user_id)
    return {
        "ok": True,
        "user": {
            "user_id": str(u.get("user_id", "") or u.get("id", "")),
            "email": str(u.get("email", "") or ""),
            "name": str(u.get("name", "") or u.get("full_name", "") or ""),
            "subscription_status": str(u.get("subscription_status", "free") or "free"),
            "trial_start_date": str(u.get("trial_start_date", "") or ""),
            "trial_end_date": str(u.get("trial_end_date", "") or ""),
            "created_at": str(u.get("created_at", "") or ""),
            "locale": str(u.get("locale", "en") or "en"),
            "timezone": str(u.get("timezone", "") or ""),
        },
        "feature_overrides": overrides,
    }


@app.patch("/v1/admin/users/{user_id}")
def admin_patch_user(user_id: str, payload: PatchAdminUserRequest, request: Request) -> dict[str, Any]:
    admin = _require_admin(request)
    role = str(admin.get("role", "viewer") or "viewer")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="editor or owner role required")
    u = store.get_user(user_id)
    if not isinstance(u, dict):
        raise HTTPException(status_code=404, detail="User not found")
    changes: dict[str, Any] = {}
    if payload.subscription_status is not None:
        valid_statuses = {"free", "trial", "active", "cancelled", "past_due"}
        s = str(payload.subscription_status).strip().lower()
        if s not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        changes["subscription_status"] = s
    if payload.trial_end_date is not None:
        changes["trial_end_date"] = str(payload.trial_end_date).strip()
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    store.update_user(user_id, **changes)
    store.add_admin_audit_log(
        actor_user_id=str(admin.get("user_id", "")),
        actor_role=role,
        action="patch_user",
        resource=f"user:{user_id}",
        details=changes,
    )
    return {"ok": True, "user_id": user_id, "changes": changes}


# ── Device/Client version-check routes ────────────────────────────────────────

@app.get("/v1/mobile/version-check")
def mobile_version_check(request: Request, platform: str = "android") -> dict[str, Any]:
    user = _mobile_user(request)
    safe_platform = str(platform or "android").strip().lower()
    active = _db_update_repository().get_active_app_version(safe_platform)
    if active is None:
        return {"ok": True, "update_available": False}
    uid = str(user.get("user_id", "") or "")
    rollout = int(active.get("rollout_percent", 100) or 100)
    if rollout < 100 and uid:
        bucket = int(hashlib.md5(f"{uid}app_update".encode()).hexdigest(), 16) % 100
        if bucket >= rollout:
            return {"ok": True, "update_available": False}
    store_url = active.get("store_url_ios") if safe_platform == "ios" else active.get("store_url_android")
    return {
        "ok": True,
        "update_available": True,
        "version": active["version_string"],
        "build_number": active["build_number"],
        "changelog": active["changelog"],
        "is_required": active["is_required"],
        "store_url": store_url or "",
    }


@app.get("/v1/device/firmware-check")
def device_firmware_check(
    request: Request,
    device_id: str = "",
    current_version: str = "",
) -> dict[str, Any]:
    safe_device_id = str(device_id or "").strip()
    safe_current = str(current_version or "").strip()
    active = _db_update_repository().get_active_firmware_version(device_id=safe_device_id)
    if active is None:
        return {"ok": True, "update_available": False}
    if safe_current and safe_current == active["version_string"]:
        return {"ok": True, "update_available": False, "current_version": safe_current}
    rollout = int(active.get("rollout_percent", 100) or 100)
    if rollout < 100 and safe_device_id:
        bucket = int(hashlib.md5(f"{safe_device_id}fw".encode()).hexdigest(), 16) % 100
        if bucket >= rollout:
            return {"ok": True, "update_available": False}
    return {
        "ok": True,
        "update_available": True,
        "version": active["version_string"],
        "download_url": active["download_url"],
        "changelog": active["changelog"],
        "is_required": active["is_required"],
    }


@app.post("/v1/ai/chat")
async def ai_chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    import asyncio
    _enforce_same_origin(request)
    actor = _authenticated_actor(request)
    if not actor:
        _bump("chat_denied")
        _event("warning", "chat_denied_unauthenticated")
        raise HTTPException(status_code=401, detail="Login required")
    _bump("chat_requests")

    message = (payload.message or "").strip()
    if not message:
        return {"reply": "Please type a message so I can help."}

    reply, _ = await asyncio.to_thread(_generate_actor_reply, actor, message)
    return {"reply": reply}


@app.get("/v1/ai/chat/stream")
async def ai_chat_stream(message: str, request: Request):
    """Stream AI chat reply as Server-Sent Events.

    Clients connect with EventSource and receive individual token chunks
    as ``data:`` events, followed by a terminal ``event: done`` frame.

    Query params:
      message  – the user's text (required, 1-4096 chars)

    SSE event types emitted:
      (default)  – one text chunk
      error      – something went wrong; data field contains the error message
      done       – stream finished; data field contains the full accumulated reply
    """
    import asyncio
    import json as _json

    from sse_starlette.sse import EventSourceResponse

    _enforce_same_origin(request)
    actor = _authenticated_actor(request)
    if not actor:
        _bump("chat_denied")
        _event("warning", "chat_denied_unauthenticated_stream")
        raise HTTPException(status_code=401, detail="Login required")

    message = (message or "").strip()[:4096]
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    _bump("chat_stream_requests")

    actor_key = _user_profile_key(actor) or str(
        actor.get("user_id", "") or actor.get("admin_id", "") or actor.get("email", "") or "session"
    ).strip().lower()

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    settings_defaults = _normalize_user_settings(
        {"response_style": "balanced", "engagement_level": "high", "wind_down_minutes": 45, "partner_mode_enabled": False}
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

    async def _event_generator():
        collected: list[str] = []
        try:
            chat_engine = _chat_engine_for_user(actor_key)

            def _run_stream():
                return list(chat_engine.generate_response_stream(
                    user_text=message,
                    personality=personality,
                    realtime_context="",
                    user_context=user_context,
                    emotion_state=emotion_state,
                    cognitive_load_mode=cognitive_load_mode,
                    max_response_tokens=160,
                ))

            # generate_response_stream is a sync generator — run in thread pool
            chunks = await asyncio.to_thread(_run_stream)
            for chunk in chunks:
                if await request.is_disconnected():
                    return
                collected.append(chunk)
                yield {"data": _json.dumps({"chunk": chunk})}

        except Exception as exc:
            _event("warning", "chat_stream_failure", user_id=str(actor.get("user_id", "")), error=str(exc)[:180])
            fallback = _chat_local_fallback(message)
            collected = [fallback]
            yield {"event": "error", "data": _json.dumps({"chunk": fallback})}

        full_reply = "".join(collected).strip()
        if full_reply:
            try:
                memory_store.record_turn(user_text=message, assistant_text=full_reply)
            except Exception:
                pass

        yield {"event": "done", "data": _json.dumps({"reply": full_reply})}

    return EventSourceResponse(_event_generator())


# ── WebSocket endpoints ────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Persistent bidirectional chat over WebSocket.

    Protocol (all frames are JSON):

    Client → server:
      {"message": "hello"}          – send a chat message
      {"type": "ping"}              – keepalive ping

    Server → client:
      {"type": "connected"}         – sent immediately on accept
      {"type": "chunk", "chunk": "…"}   – one token batch while streaming
      {"type": "done", "reply": "…"}    – full reply, stream finished
      {"type": "error", "detail": "…"}  – recoverable error (connection stays open)
      {"type": "pong"}              – response to ping

    A single connection can handle multiple sequential messages.
    """
    import asyncio
    import json as _json

    token = websocket.query_params.get("token", "")
    actor = _mobile_user_from_access_token(token) if token else None

    if not actor:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    await websocket.send_json({"type": "connected"})

    actor_key = _user_profile_key(actor) or str(
        actor.get("user_id", "") or actor.get("admin_id", "") or actor.get("email", "") or "session"
    ).strip().lower()
    memory_store = _memory_store_for_user(actor_key)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = _json.loads(raw)
            except Exception:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON frame"})
                continue

            if frame.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            message = str(frame.get("message", "")).strip()[:4096]
            if not message:
                await websocket.send_json({"type": "error", "detail": "message is required"})
                continue

            profile = _safe_profile()
            if not isinstance(profile, dict):
                profile = {}
            settings_defaults = _normalize_user_settings(
                {"response_style": "balanced", "engagement_level": "high", "wind_down_minutes": 45, "partner_mode_enabled": False}
            )
            settings_payload = _profile_user_settings(profile, actor, defaults=settings_defaults)
            profile_prefs = _chat_profile_prefs_for_user(profile, actor)
            routine = _chat_scoped_routine_for_user(profile, actor)
            controls = _chat_scoped_controls_for_user(profile, actor)
            personality = _chat_personality_from_settings(settings_payload)
            emotion_state = detect_emotion_state(message)
            cognitive_load_mode = _chat_cognitive_load_mode(settings_payload)
            memory_line = memory_store.memory_prompt_line(message)
            user_context = _chat_user_context(
                user=actor,
                settings_payload=settings_payload,
                profile_prefs=profile_prefs,
                routine=routine,
                controls=controls,
                memory_line=memory_line,
            )

            collected: list[str] = []
            try:
                chat_engine = _chat_engine_for_user(actor_key)

                def _run_stream():
                    return list(chat_engine.generate_response_stream(
                        user_text=message,
                        personality=personality,
                        realtime_context="",
                        user_context=user_context,
                        emotion_state=emotion_state,
                        cognitive_load_mode=cognitive_load_mode,
                        max_response_tokens=160,
                    ))

                chunks = await asyncio.to_thread(_run_stream)
                for chunk in chunks:
                    collected.append(chunk)
                    await websocket.send_json({"type": "chunk", "chunk": chunk})

            except Exception as exc:
                _event("warning", "ws_chat_stream_failure", user_id=str(actor.get("user_id", "")), error=str(exc)[:180])
                fallback = _chat_local_fallback(message)
                collected = [fallback]
                await websocket.send_json({"type": "error", "detail": fallback})

            full_reply = "".join(collected).strip()
            await websocket.send_json({"type": "done", "reply": full_reply})

            if full_reply:
                try:
                    memory_store.record_turn(user_text=message, assistant_text=full_reply)
                except Exception:
                    pass

    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket):
    """Audio-in → transcript + streaming AI reply over WebSocket.

    Protocol:

    Client → server:
      {"type": "config", "sample_rate": 16000}   – optional, sent before audio
      <binary frame>                              – raw PCM-16 audio bytes
      {"type": "stop"}                            – signals end of audio input

    Server → client:
      {"type": "connected"}                       – on accept
      {"type": "transcript", "text": "…"}         – STT result
      {"type": "chunk", "chunk": "…"}             – AI reply token
      {"type": "done", "reply": "…"}              – full AI reply, stream finished
      {"type": "error", "detail": "…"}            – STT or AI failure (connection stays open)

    After "done" the client may send more audio for a new turn.
    """
    import asyncio
    import io
    import json as _json
    import struct
    import tempfile
    import wave

    token = websocket.query_params.get("token", "")
    actor = _mobile_user_from_access_token(token) if token else None

    if not actor:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    await websocket.send_json({"type": "connected"})

    actor_key = _user_profile_key(actor) or str(
        actor.get("user_id", "") or actor.get("admin_id", "") or actor.get("email", "") or "session"
    ).strip().lower()
    memory_store = _memory_store_for_user(actor_key)

    sample_rate = 16000
    audio_buf: list[bytes] = []

    try:
        while True:
            frame = await websocket.receive()

            # Binary frame → audio chunk
            if frame.get("bytes") is not None:
                audio_buf.append(frame["bytes"])
                continue

            # Text frame → control message
            try:
                msg = _json.loads(frame.get("text", "{}"))
            except Exception:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON frame"})
                continue

            if msg.get("type") == "config":
                try:
                    sample_rate = int(msg.get("sample_rate", 16000))
                except Exception:
                    pass
                continue

            if msg.get("type") != "stop":
                await websocket.send_json({"type": "error", "detail": f"Unknown frame type: {msg.get('type')}"})
                continue

            # "stop" received — transcribe collected audio
            if not audio_buf:
                await websocket.send_json({"type": "error", "detail": "No audio received"})
                audio_buf = []
                continue

            raw_pcm = b"".join(audio_buf)
            audio_buf = []

            # Write PCM to a temp WAV file for the STT manager
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                with wave.open(tmp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(sample_rate)
                    wf.writeframes(raw_pcm)

            try:
                from ai.stt_manager import STTManager
                stt = STTManager()

                def _do_transcribe():
                    return stt.transcribe_file_with_confidence(tmp_path)

                transcript, confidence = await asyncio.to_thread(_do_transcribe)
            except Exception as exc:
                await websocket.send_json({"type": "error", "detail": f"STT failed: {exc}"})
                continue
            finally:
                import os as _os
                try:
                    _os.unlink(tmp_path)
                except Exception:
                    pass

            transcript = transcript.strip()
            if not transcript:
                await websocket.send_json({"type": "error", "detail": "Could not transcribe audio"})
                continue

            await websocket.send_json({"type": "transcript", "text": transcript})

            # Generate and stream AI reply
            profile = _safe_profile()
            if not isinstance(profile, dict):
                profile = {}
            settings_defaults = _normalize_user_settings(
                {"response_style": "balanced", "engagement_level": "high", "wind_down_minutes": 45, "partner_mode_enabled": False}
            )
            settings_payload = _profile_user_settings(profile, actor, defaults=settings_defaults)
            profile_prefs = _chat_profile_prefs_for_user(profile, actor)
            routine = _chat_scoped_routine_for_user(profile, actor)
            controls = _chat_scoped_controls_for_user(profile, actor)
            personality = _chat_personality_from_settings(settings_payload)
            emotion_state = detect_emotion_state(transcript)
            cognitive_load_mode = _chat_cognitive_load_mode(settings_payload)
            memory_line = memory_store.memory_prompt_line(transcript)
            user_context = _chat_user_context(
                user=actor,
                settings_payload=settings_payload,
                profile_prefs=profile_prefs,
                routine=routine,
                controls=controls,
                memory_line=memory_line,
            )

            collected: list[str] = []
            try:
                chat_engine = _chat_engine_for_user(actor_key)

                def _run_stream():
                    return list(chat_engine.generate_response_stream(
                        user_text=transcript,
                        personality=personality,
                        realtime_context="",
                        user_context=user_context,
                        emotion_state=emotion_state,
                        cognitive_load_mode=cognitive_load_mode,
                        max_response_tokens=160,
                    ))

                chunks = await asyncio.to_thread(_run_stream)
                for chunk in chunks:
                    collected.append(chunk)
                    await websocket.send_json({"type": "chunk", "chunk": chunk})

            except Exception as exc:
                _event("warning", "ws_voice_stream_failure", user_id=str(actor.get("user_id", "")), error=str(exc)[:180])
                fallback = _chat_local_fallback(transcript)
                collected = [fallback]
                await websocket.send_json({"type": "error", "detail": fallback})

            full_reply = "".join(collected).strip()
            await websocket.send_json({"type": "done", "reply": full_reply})

            if full_reply:
                try:
                    memory_store.record_turn(user_text=transcript, assistant_text=full_reply)
                except Exception:
                    pass

    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


class GarminSyncRequest(BaseModel):
    target_date: str = Field(default="", max_length=10)  # YYYY-MM-DD; empty = today


@app.post("/v1/garmin/sync")
async def garmin_sync(payload: GarminSyncRequest, request: Request) -> dict[str, Any]:
    """Pull today's (or *target_date*'s) health data from Garmin Connect.

    Credentials are read from GARMIN_EMAIL / GARMIN_PASSWORD env vars.
    The data is ingested into the user's fitness_tracker profile section.
    """
    import asyncio

    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    target_date = str(payload.target_date or "").strip() or None

    try:
        from integrations.fitness_tracker_api import FitnessTrackerAPI
        tracker = FitnessTrackerAPI()

        def _do_sync():
            return tracker.fetch_from_garmin(profile, target_date)

        result = await asyncio.to_thread(_do_sync)
    except Exception as exc:
        _event("warning", "garmin_sync_error", user_id=user_id, error=str(exc)[:200])
        raise HTTPException(status_code=502, detail=f"Garmin sync failed: {exc}")

    _event(
        "info", "garmin_synced",
        user_id=user_id,
        date=result.get("date", ""),
        ingested=result.get("ingested", False),
    )
    return result


@app.get("/v1/garmin/status")
def garmin_status(request: Request) -> dict[str, Any]:
    """Return the current Garmin / fitness tracker status for the user."""
    _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    try:
        from integrations.fitness_tracker_api import FitnessTrackerAPI
        from integrations.garmin_client import build_client_from_settings
        tracker = FitnessTrackerAPI()
        status = tracker.get_status(profile)
        client = build_client_from_settings()
        status["garmin_configured"] = bool(client._email)
        status["garmin_available"] = client.available
    except Exception as exc:
        return {"error": str(exc)}

    return status


@app.get("/v1/report/weekly/pdf")
async def weekly_report_pdf(
    request: Request,
    renderer: str = "reportlab",
) -> Response:
    """Generate the weekly health report and return it as a downloadable PDF.

    renderer: "reportlab" (default, ReportLab A4) or "weasyprint" (HTML/CSS renderer).
    """
    import asyncio
    import tempfile

    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "")
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    use_weasyprint = str(renderer).strip().lower() == "weasyprint"

    try:
        from health.weekly_health_report import WeeklyHealthReport

        def _build_pdf() -> bytes:
            reporter = WeeklyHealthReport()
            report = reporter.generate(profile)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
            if use_weasyprint:
                reporter.to_html_pdf(report, tmp_path)
            else:
                reporter.to_pdf(report, tmp_path)
            import os as _os
            data = open(tmp_path, "rb").read()
            _os.unlink(tmp_path)
            return data

        pdf_bytes = await asyncio.to_thread(_build_pdf)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        _event("warning", "weekly_pdf_error", user_id=user_id, error=str(exc)[:200])
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    from datetime import date as _date
    filename = f"danah_weekly_report_{_date.today().isoformat()}.pdf"
    _event("info", "weekly_pdf_generated", user_id=user_id, renderer=renderer)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/v1/report/weekly/pdf/url")
async def weekly_report_pdf_url(
    request: Request,
    renderer: str = "reportlab",
    expires_in: int = 3600,
) -> dict[str, Any]:
    """Generate the weekly health report PDF, upload it to S3, and return a presigned URL.

    renderer: "reportlab" (default) or "weasyprint"
    expires_in: presigned URL lifetime in seconds (default 3600 = 1 hour)
    Requires AWS_S3_BUCKET to be configured in settings.
    """
    import asyncio
    import tempfile
    from datetime import date as _date

    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "")
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    try:
        from Storage.s3_client import build_s3_client_from_settings
        s3 = build_s3_client_from_settings()
        if s3 is None:
            raise HTTPException(status_code=503, detail="S3 not configured — set AWS_S3_BUCKET")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"S3 init failed: {exc}")

    use_weasyprint = str(renderer).strip().lower() == "weasyprint"

    try:
        from health.weekly_health_report import WeeklyHealthReport

        def _build_and_upload() -> str:
            reporter = WeeklyHealthReport()
            report = reporter.generate(profile)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
            if use_weasyprint:
                reporter.to_html_pdf(report, tmp_path)
            else:
                reporter.to_pdf(report, tmp_path)
            import os as _os
            pdf_bytes = open(tmp_path, "rb").read()
            _os.unlink(tmp_path)
            date_str = _date.today().isoformat()
            key = f"{settings.aws_s3_reports_prefix}weekly/{user_id or 'anon'}/{date_str}.pdf"
            s3.upload_bytes(key, pdf_bytes, content_type="application/pdf")
            return s3.presigned_url(key, expires_in=max(60, min(86400, int(expires_in))))

        presigned = await asyncio.to_thread(_build_and_upload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        _event("warning", "weekly_pdf_url_error", user_id=user_id, error=str(exc)[:200])
        raise HTTPException(status_code=500, detail=f"Report upload failed: {exc}")

    _event("info", "weekly_pdf_uploaded_s3", user_id=user_id)
    return {"url": presigned, "expires_in": expires_in}


@app.get("/v1/report/weekly/html")
async def weekly_report_html(request: Request) -> Response:
    """Return the weekly health report as a styled HTML document for preview."""
    import asyncio

    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "")
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    try:
        from health.weekly_health_report import WeeklyHealthReport

        def _build_html() -> str:
            reporter = WeeklyHealthReport()
            report = reporter.generate(profile)
            return reporter.to_html(report)

        html_content = await asyncio.to_thread(_build_html)
    except Exception as exc:
        _event("warning", "weekly_html_error", user_id=user_id, error=str(exc)[:200])
        raise HTTPException(status_code=500, detail=f"HTML report generation failed: {exc}")

    _event("info", "weekly_html_generated", user_id=user_id)
    return Response(content=html_content, media_type="text/html; charset=utf-8")


class FitbitSyncRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=2048)
    refresh_token: str = Field(default="", max_length=2048)
    target_date: str = Field(default="", max_length=10)  # YYYY-MM-DD; empty = today


@app.get("/v1/fitbit/auth-url")
def fitbit_auth_url(request: Request) -> dict[str, Any]:
    """Return the Fitbit OAuth2 authorization URL for the mobile app to open."""
    _require_user(request)
    try:
        from integrations.fitbit_client import build_auth_url
        url = build_auth_url(
            client_id=settings.fitbit_client_id,
            redirect_uri=settings.fitbit_redirect_uri,
        )
        return {"auth_url": url, "configured": bool(settings.fitbit_client_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/fitbit/callback")
async def fitbit_callback(code: str, request: Request) -> dict[str, Any]:
    """OAuth2 callback — exchange authorization code for access + refresh tokens.

    The mobile app (or browser) is redirected here by Fitbit after user consent.
    Returns tokens the mobile app should store and later send to /v1/fitbit/sync.
    """
    import asyncio

    if not code:
        raise HTTPException(status_code=400, detail="code is required")

    try:
        from integrations.fitbit_client import exchange_code

        def _exchange():
            return exchange_code(
                client_id=settings.fitbit_client_id,
                client_secret=settings.fitbit_client_secret,
                code=code,
                redirect_uri=settings.fitbit_redirect_uri,
            )

        tokens = await asyncio.to_thread(_exchange)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if "error" in tokens:
        raise HTTPException(status_code=401, detail=tokens["error"])

    return {
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_in": tokens.get("expires_in", 0),
        "fitbit_user_id": tokens.get("user_id", ""),
    }


@app.post("/v1/fitbit/sync")
async def fitbit_sync(payload: FitbitSyncRequest, request: Request) -> dict[str, Any]:
    """Pull health data from Fitbit and ingest it into the user's profile.

    The mobile app forwards the OAuth2 tokens obtained via /v1/fitbit/auth-url.
    """
    import asyncio

    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "")
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    target_date = str(payload.target_date or "").strip() or None

    try:
        from integrations.fitness_tracker_api import FitnessTrackerAPI
        tracker = FitnessTrackerAPI()

        def _do_sync():
            return tracker.fetch_from_fitbit(
                profile=profile,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                target_date=target_date,
            )

        result = await asyncio.to_thread(_do_sync)
    except Exception as exc:
        _event("warning", "fitbit_sync_error", user_id=user_id, error=str(exc)[:200])
        raise HTTPException(status_code=502, detail=f"Fitbit sync failed: {exc}")

    _event(
        "info", "fitbit_synced",
        user_id=user_id,
        date=result.get("date", ""),
        ingested=result.get("ingested", False),
    )
    return result


class GoogleCalendarSyncRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=2048)
    refresh_token: str = Field(default="", max_length=2048)
    days_ahead: int = Field(default=7, ge=1, le=30)
    max_results: int = Field(default=50, ge=1, le=250)


@app.post("/v1/calendar/google/sync")
async def calendar_google_sync(payload: GoogleCalendarSyncRequest, request: Request) -> dict[str, Any]:
    """Pull events from the authenticated user's Google Calendar and sync into their profile.

    The mobile app forwards the Google OAuth2 tokens obtained during sign-in.
    Requires a logged-in user (Bearer token or session cookie).
    """
    import asyncio

    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "")

    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    try:
        from integrations.calendar_sync import CalendarSync
        cal = CalendarSync()

        def _do_sync():
            return cal.fetch_from_google(
                profile=profile,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                days_ahead=payload.days_ahead,
                max_results=payload.max_results,
            )

        result = await asyncio.to_thread(_do_sync)
    except Exception as exc:
        _event("warning", "google_calendar_sync_error", user_id=user_id, error=str(exc)[:200])
        raise HTTPException(status_code=502, detail=f"Google Calendar sync failed: {exc}")

    _event("info", "google_calendar_synced", user_id=user_id, events_count=result.get("events_count", 0))
    return result


@app.get("/v1/calendar/schedule")
async def calendar_schedule(request: Request, days_ahead: int = 1) -> dict[str, Any]:
    """Return the user's upcoming schedule from the local calendar cache."""
    import asyncio

    user = _require_user(request)
    profile = _safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    try:
        from integrations.calendar_sync import CalendarSync
        cal = CalendarSync()
        if days_ahead <= 1:
            result = await asyncio.to_thread(cal.get_tomorrow_schedule, profile)
        else:
            result = await asyncio.to_thread(cal.get_morning_brief, profile)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@app.post("/v1/command")
def v1_command(payload: CommandRequest, request: Request) -> dict[str, Any]:
    _enforce_same_origin(request)
    actor = _authenticated_actor(request)
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
