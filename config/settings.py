"""
Operational runtime settings, loaded from environment variables / .env file.

GPT routing .env setup:
- Enable direct OpenAI route:
  USE_OPENAI_DIRECT=1
  OPENAI_API_KEY=your_openai_api_key
  OPENAI_CHAT_MODEL=gpt-4o-mini
  OPENAI_BASE_URL=https://api.openai.com/v1

- Optional backend proxy route (entitlement-gated cloud_chat):
  USE_BACKEND_AI_PROXY=1
  APP_BACKEND_BASE_URL=http://127.0.0.1:8000
  BED_DEVICE_ID=your_device_id
"""

import logging
from pathlib import Path

import os

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # project root

# Load .env into os.environ as early as possible. pydantic-settings reads .env
# for the Settings object, but code that calls os.getenv() directly — notably
# database.connection.DatabaseConnection reading DATABASE_URL — would otherwise
# silently fall back to sqlite while the app "thinks" it is on Postgres. This
# single load keeps every consumer (app, alembic, scripts) on the same DB.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _assert_safe_sensitive_json_path(label: str, path: Path) -> None:
    import os

    override = os.getenv("ALLOW_INSECURE_REPO_DATA_PATHS", "0") == "1"
    resolved = path.resolve()
    repo_data_dir = (BASE_DIR / "data").resolve()
    repo_profile_path = (BASE_DIR / "user_profile.json").resolve()
    is_risky = _is_relative_to(resolved, repo_data_dir) or resolved == repo_profile_path
    if is_risky and not override:
        logging.getLogger("runtime_guard").warning(
            "Refusing unsafe JSON path for %s: %s (set ALLOW_INSECURE_REPO_DATA_PATHS=1 to override)",
            label,
            resolved,
        )
        raise RuntimeError(
            f"Unsafe JSON data path for {label}: {resolved}. "
            "Set ALLOW_INSECURE_REPO_DATA_PATHS=1 only if you explicitly accept this."
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ── Security ──────────────────────────────────────────────────────
    secret_key: str = Field(
        "change-me-in-production",
        validation_alias=AliasChoices("SECRET_KEY", "secret_key"),
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_secure(cls, v: str) -> str:
        _unsafe = {"change-me-in-production", "secret", "changeme", "development", ""}
        if v in _unsafe or len(v) < 32:
            raise ValueError(
                "SECRET_KEY is unsafe or too short (minimum 32 characters). "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" '
                "and set it as SECRET_KEY in your .env file."
            )
        return v

    # ── CORS ──────────────────────────────────────────────────────────
    web_allowed_origins_raw: str = Field(
        "http://127.0.0.1:8000,http://localhost:8000",
        validation_alias=AliasChoices("WEB_ALLOWED_ORIGINS", "web_allowed_origins_raw"),
    )
    web_allowed_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    # ── Deepgram ──────────────────────────────────────────────────────
    deepgram_api_key: str = ""
    deepgram_tts_api_key: str = Field(
        "",
        validation_alias=AliasChoices(
            "DEEPGRAM_TTS_API_KEY", "TTS_API_KEY", "DEEPGRAM_API_KEY", "deepgram_tts_api_key"
        ),
    )
    deepgram_voice_agent_model: str = "voice-agent-conversational"
    deepgram_voice_agent_url: str = "https://agent.deepgram.com/v1/agent/converse"

    # ── STT ───────────────────────────────────────────────────────────
    stt_model: str = Field(
        "nova-2",
        validation_alias=AliasChoices("DEEPGRAM_STT_MODEL", "stt_model"),
    )
    stt_mode: str = "api"
    stt_require_api_stream: bool = False
    stt_local_model_size: str = "small"
    stt_local_device: str = "cpu"
    stt_local_compute_type: str = "int8"

    # ── TTS ───────────────────────────────────────────────────────────
    tts_model: str = Field(
        "aura-2-thalia-en",
        validation_alias=AliasChoices("DEEPGRAM_TTS_MODEL", "tts_model"),
    )
    tts_voice: str = Field(
        "aura-2-thalia-en",
        validation_alias=AliasChoices("DEEPGRAM_TTS_VOICE", "tts_voice"),
    )
    tts_voice_therapist: str = Field(
        "aura-2-thalia-en",
        validation_alias=AliasChoices("DEEPGRAM_TTS_VOICE_THERAPIST", "tts_voice_therapist"),
    )
    tts_voice_coach: str = Field(
        "aura-2-orion-en",
        validation_alias=AliasChoices("DEEPGRAM_TTS_VOICE_COACH", "tts_voice_coach"),
    )
    tts_voice_guide: str = Field(
        "aura-2-asteria-en",
        validation_alias=AliasChoices("DEEPGRAM_TTS_VOICE_GUIDE", "tts_voice_guide"),
    )

    # ── Timeouts / limits ─────────────────────────────────────────────
    ai_timeout_seconds: int = 20
    chat_quick_timeout_seconds: int = 4
    chat_total_timeout_seconds: int = 10
    chat_max_response_tokens: int = 120
    cache_ttl_seconds: int = 86400

    # ── Language ──────────────────────────────────────────────────────
    language_hint: str = Field(
        "auto",
        validation_alias=AliasChoices("SMART_BED_LANGUAGE", "language_hint"),
    )
    use_api_first: bool = Field(
        True,
        validation_alias=AliasChoices("SMART_BED_API_FIRST", "use_api_first"),
    )

    # ── Audio / music ─────────────────────────────────────────────────
    local_music_dir: str = "local_music"

    # ── Wake word ─────────────────────────────────────────────────────
    wake_word_mode: str = "keyboard"
    wake_word_phrase: str = "hey smart bed"
    wake_word_enforce_local: bool = True
    wake_word_mic_index: int = -1
    wake_word_voice_timeout_seconds: int = Field(
        3,
        validation_alias=AliasChoices(
            "WAKE_WORD_TIMEOUT_SECONDS", "wake_word_voice_timeout_seconds"
        ),
    )
    wake_word_phrase_limit_seconds: int = 3
    wake_word_barge_in_timeout_seconds: int = 1
    wake_word_barge_in_phrase_limit_seconds: int = 1

    # ── Acoustic wake word (on-device keyword spotting, ai/acoustic_wake.py) ──
    # auto: use porcupine if configured, else openwakeword, else fall back to
    # the legacy record→STT→text-match wake loop. off: legacy loop only.
    wake_acoustic_backend: str = "auto"
    wake_acoustic_sensitivity: float = 0.6
    porcupine_access_key: str = ""  # console.picovoice.ai (free tier)
    porcupine_keyword_path: str = ""  # .ppn file for the wake phrase
    openwakeword_model_path: str = ""  # .onnx/.tflite trained wake model

    # ── TTS streaming playback (chunked PCM, first audio ≈ network TTFB) ──
    # Off by default; enable on the bed (TTS_STREAMING_PLAYBACK=1) after
    # verifying speaker output on the device.
    tts_streaming_playback: bool = False

    # ── Quiet hours ───────────────────────────────────────────────────
    quiet_hours_default_window: str = "22:00-07:00"
    quiet_hours_override_max_minutes: int = 120

    # ── Voice circuit breaker ─────────────────────────────────────────
    voice_circuit_failure_threshold: int = 3
    voice_circuit_backoff_base_seconds: float = 3.0
    voice_circuit_backoff_max_seconds: float = 60.0
    voice_circuit_reset_signal_path: str = ""  # filled by validator

    # ── Sensors ───────────────────────────────────────────────────────
    enable_sensor_bridge: bool = True
    sensor_pressure_enabled: bool = False
    sensor_motion_enabled: bool = False
    sensor_pressure_pin: int = -1
    sensor_motion_pin: int = -1
    sensor_pressure_pull_up: bool = True
    sensor_motion_pull_up: bool = False
    sensor_pressure_active_low: bool = True
    sensor_motion_active_low: bool = False
    sensor_poll_interval_seconds: float = 0.2
    sensor_temperature_enabled: bool = False
    sensor_temperature_pin: int = 4
    sensor_temperature_poll_interval_seconds: float = 5.0
    # MAX30102 heart-rate oximeter is REPLACED by the COLMI smart ring.
    # The fields below are kept as dead stubs so old .env files do not crash.
    sensor_heart_rate_enabled: bool = False

    # ── COLMI Smart Ring (BLE) ────────────────────────────────────────
    ring_enabled: bool = Field(
        False,
        validation_alias=AliasChoices("RING_ENABLED", "ring_enabled"),
    )
    ring_ble_address: str = Field(
        "",
        validation_alias=AliasChoices("RING_BLE_ADDRESS", "ring_ble_address"),
    )
    ring_model: str = Field(
        "colmi_r02",
        validation_alias=AliasChoices("RING_MODEL", "ring_model"),
    )
    ring_auto_connect: bool = Field(
        True,
        validation_alias=AliasChoices("RING_AUTO_CONNECT", "ring_auto_connect"),
    )
    ring_realtime_hr_enabled: bool = Field(
        True,
        validation_alias=AliasChoices("RING_REALTIME_HR_ENABLED", "ring_realtime_hr_enabled"),
    )
    ring_realtime_spo2_enabled: bool = Field(
        True,
        validation_alias=AliasChoices("RING_REALTIME_SPO2_ENABLED", "ring_realtime_spo2_enabled"),
    )
    ring_sync_interval_minutes: int = Field(
        30,
        validation_alias=AliasChoices("RING_SYNC_INTERVAL_MINUTES", "ring_sync_interval_minutes"),
    )
    ring_reconnect_max_retries: int = Field(
        10,
        validation_alias=AliasChoices("RING_RECONNECT_MAX_RETRIES", "ring_reconnect_max_retries"),
    )
    aec_min_confidence_when_playing: float = 0.72

    # ── Spotify ───────────────────────────────────────────────────────
    spotify_access_token: str = ""
    spotify_device_id: str = ""
    spotify_default_playlist_uri: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_scopes: str = (
        "user-read-playback-state user-modify-playback-state "
        "user-read-currently-playing user-read-email user-read-private"
    )
    spotify_redirect_uri: str = "http://127.0.0.1:8000/spotify/callback"

    # ── App URLs ──────────────────────────────────────────────────────
    app_base_url: str = "http://127.0.0.1:8000"
    app_backend_base_url: str = "http://127.0.0.1:8000"

    # ── PayPal ────────────────────────────────────────────────────────
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_api_base: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    paypal_brand_name: str = "Danah Smart Bed"
    paypal_currency_code: str = "USD"
    paypal_timeout_seconds: int = 20
    paypal_webhook_max_age_seconds: int = 600
    paypal_webhook_receipt_ttl_seconds: int = 86400
    paypal_standard_monthly_plan_id: str = ""
    paypal_standard_yearly_plan_id: str = ""
    paypal_pro_monthly_plan_id: str = ""
    paypal_pro_yearly_plan_id: str = ""

    # ── Device ────────────────────────────────────────────────────────
    bed_device_id: str = ""
    bed_firmware_version: str = "1.0.0"

    # ── AI routing ────────────────────────────────────────────────────
    use_backend_ai_proxy: bool = True
    use_openai_direct: bool = False
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # ── LED ───────────────────────────────────────────────────────────
    led_hw_enabled: bool = Field(
        False,
        validation_alias=AliasChoices("LED_HARDWARE_ENABLED", "led_hw_enabled"),
    )
    led_backend: str = "auto"
    led_frequency_hz: int = 800000
    led_user_dma_channel: int = 10
    led_state_dma_channel: int = 11
    led_invert_signal: bool = False
    led_max_brightness: int = 255
    led_animation_fps: float = 20.0
    user_strip_pin: int = 18
    state_strip_pin: int = 13
    user_strip_led_count: int = 120
    state_strip_led_count: int = 60

    # ── Paths (defaults filled by validator) ──────────────────────────
    runtime_data_dir: str = ""
    subscription_db_path: str = ""
    user_profile_path: str = ""
    long_term_memory_path: str = ""
    islamic_prayer_cache_path: str = ""
    database_url: str = Field(
        "",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )

    # ── Database pool ─────────────────────────────────────────────────
    # Sync pool (psycopg2 / SQLAlchemy QueuePool)
    db_pool_size: int = Field(
        10,
        validation_alias=AliasChoices("DB_POOL_SIZE", "db_pool_size"),
    )
    db_max_overflow: int = Field(
        20,
        validation_alias=AliasChoices("DB_MAX_OVERFLOW", "db_max_overflow"),
    )
    db_pool_timeout: float = Field(
        30.0,
        validation_alias=AliasChoices("DB_POOL_TIMEOUT", "db_pool_timeout"),
    )
    db_pool_recycle: int = Field(
        3600,
        validation_alias=AliasChoices("DB_POOL_RECYCLE", "db_pool_recycle"),
    )
    # Async pool (asyncpg)
    db_async_pool_min: int = Field(
        2,
        validation_alias=AliasChoices("DB_ASYNC_POOL_MIN", "db_async_pool_min"),
    )
    db_async_pool_max: int = Field(
        10,
        validation_alias=AliasChoices("DB_ASYNC_POOL_MAX", "db_async_pool_max"),
    )
    db_async_command_timeout: float = Field(
        30.0,
        validation_alias=AliasChoices("DB_ASYNC_COMMAND_TIMEOUT", "db_async_command_timeout"),
    )

    # ── Celery / Redis ────────────────────────────────────────────────
    celery_broker_url: str = Field(
        "redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_BROKER_URL", "REDIS_URL", "celery_broker_url"),
    )
    celery_result_backend: str = Field(
        "redis://localhost:6379/1",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND", "celery_result_backend"),
    )
    arq_redis_url: str = Field(
        "redis://localhost:6379/2",
        validation_alias=AliasChoices("ARQ_REDIS_URL", "arq_redis_url"),
    )

    # ── Fitbit ────────────────────────────────────────────────────────
    fitbit_client_id: str = Field(
        "",
        validation_alias=AliasChoices("FITBIT_CLIENT_ID", "fitbit_client_id"),
    )
    fitbit_client_secret: str = Field(
        "",
        validation_alias=AliasChoices("FITBIT_CLIENT_SECRET", "fitbit_client_secret"),
    )
    fitbit_redirect_uri: str = Field(
        "http://127.0.0.1:8000/v1/fitbit/callback",
        validation_alias=AliasChoices("FITBIT_REDIRECT_URI", "fitbit_redirect_uri"),
    )

    # ── Garmin Connect ────────────────────────────────────────────────
    garmin_email: str = Field(
        "",
        validation_alias=AliasChoices("GARMIN_EMAIL", "garmin_email"),
    )
    garmin_password: str = Field(
        "",
        validation_alias=AliasChoices("GARMIN_PASSWORD", "garmin_password"),
    )
    garmin_tokenstore_path: str = Field(
        "",
        validation_alias=AliasChoices("GARMIN_TOKENSTORE_PATH", "garmin_tokenstore_path"),
    )

    # ── Google Calendar ───────────────────────────────────────────────
    google_calendar_client_id: str = Field(
        "",
        validation_alias=AliasChoices("GOOGLE_CALENDAR_CLIENT_ID", "google_calendar_client_id"),
    )
    google_calendar_client_secret: str = Field(
        "",
        validation_alias=AliasChoices(
            "GOOGLE_CALENDAR_CLIENT_SECRET", "google_calendar_client_secret"
        ),
    )
    google_calendar_token_uri: str = "https://oauth2.googleapis.com/token"
    google_calendar_scopes: str = "https://www.googleapis.com/auth/calendar.readonly"

    # ── OpenWeatherMap ────────────────────────────────────────────────
    owm_api_key: str = Field(
        "",
        validation_alias=AliasChoices("OPENWEATHERMAP_API_KEY", "OWM_API_KEY", "owm_api_key"),
    )

    # ── Firebase / FCM ────────────────────────────────────────────────
    firebase_credentials_path: str = Field(
        "",
        validation_alias=AliasChoices("FIREBASE_CREDENTIALS_PATH", "firebase_credentials_path"),
    )
    firebase_credentials_json: str = Field(
        "",
        validation_alias=AliasChoices("FIREBASE_CREDENTIALS_JSON", "firebase_credentials_json"),
    )

    @field_validator("firebase_credentials_path", mode="before")
    @classmethod
    def clean_firebase_quotes(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip("'\"")
        return v

    # ── Sentry ────────────────────────────────────────────────────────
    sentry_dsn: str = Field(
        "",
        validation_alias=AliasChoices("SENTRY_DSN", "sentry_dsn"),
    )
    sentry_environment: str = Field(
        "production",
        validation_alias=AliasChoices("SENTRY_ENVIRONMENT", "sentry_environment"),
    )
    sentry_release: str = Field(
        "",
        validation_alias=AliasChoices("SENTRY_RELEASE", "sentry_release"),
    )
    sentry_traces_sample_rate: float = Field(
        0.1,
        validation_alias=AliasChoices("SENTRY_TRACES_SAMPLE_RATE", "sentry_traces_sample_rate"),
    )
    sentry_profiles_sample_rate: float = Field(
        0.1,
        validation_alias=AliasChoices("SENTRY_PROFILES_SAMPLE_RATE", "sentry_profiles_sample_rate"),
    )

    # ── AWS ───────────────────────────────────────────────────────────
    aws_region: str = Field(
        "us-east-1",
        validation_alias=AliasChoices("AWS_REGION", "aws_region"),
    )
    aws_access_key_id: str = Field(
        "",
        validation_alias=AliasChoices("AWS_ACCESS_KEY_ID", "aws_access_key_id"),
    )
    aws_secret_access_key: str = Field(
        "",
        validation_alias=AliasChoices("AWS_SECRET_ACCESS_KEY", "aws_secret_access_key"),
    )
    aws_s3_bucket: str = Field(
        "",
        validation_alias=AliasChoices("AWS_S3_BUCKET", "aws_s3_bucket"),
    )
    aws_s3_reports_prefix: str = Field(
        "reports/",
        validation_alias=AliasChoices("AWS_S3_REPORTS_PREFIX", "aws_s3_reports_prefix"),
    )
    aws_ses_from_email: str = Field(
        "",
        validation_alias=AliasChoices("AWS_SES_FROM_EMAIL", "aws_ses_from_email"),
    )
    aws_ses_from_name: str = Field(
        "Danah Smart Bed",
        validation_alias=AliasChoices("AWS_SES_FROM_NAME", "aws_ses_from_name"),
    )
    aws_s3_presigned_url_expiry_seconds: int = Field(
        3600,
        validation_alias=AliasChoices(
            "AWS_S3_PRESIGNED_URL_EXPIRY_SECONDS", "aws_s3_presigned_url_expiry_seconds"
        ),
    )

    # ── Islamic ───────────────────────────────────────────────────────
    islamic_prayer_city: str = "Kuwait City"
    islamic_prayer_country: str = "Kuwait"
    islamic_prayer_latitude: str = ""
    islamic_prayer_longitude: str = ""
    islamic_prayer_method: int = 8
    islamic_prayer_timeout_seconds: int = 12
    islamic_prayer_auto_location: bool = False

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        def _resolve(raw: str, default: Path) -> str:
            if not raw:
                return str(default.resolve())
            p = Path(raw).expanduser()
            return str((BASE_DIR / p if not p.is_absolute() else p).resolve())

        rdd = Path(_resolve(self.runtime_data_dir, BASE_DIR / "runtime_data"))
        self.runtime_data_dir = str(rdd)
        self.subscription_db_path = _resolve(
            self.subscription_db_path, rdd / "subscription_db.json"
        )
        self.user_profile_path = _resolve(self.user_profile_path, rdd / "user_profile.json")
        self.long_term_memory_path = _resolve(
            self.long_term_memory_path, rdd / "long_term_memory.json"
        )
        self.voice_circuit_reset_signal_path = _resolve(
            self.voice_circuit_reset_signal_path, rdd / "voice_circuit_reset_signal.json"
        )
        self.islamic_prayer_cache_path = _resolve(
            self.islamic_prayer_cache_path, rdd / "prayer_times_cache.json"
        )

        return self


settings = Settings()


def enforce_sensitive_data_path_guard() -> None:
    _assert_safe_sensitive_json_path("SUBSCRIPTION_DB_PATH", Path(settings.subscription_db_path))
    _assert_safe_sensitive_json_path("USER_PROFILE_PATH", Path(settings.user_profile_path))


def validate_production_secrets() -> list[str]:
    """Check all required secrets are configured for production.

    Returns a list of warning messages (empty = all good).
    Call this from the app lifespan or CLI startup command.
    """
    is_production = os.getenv("DANAH_ENV", "development").lower() == "production"
    warnings: list[str] = []

    _unsafe_key = {"change-me-in-production", "secret", "changeme", "development", ""}

    if settings.secret_key in _unsafe_key:
        warnings.append("SECRET_KEY is not set or uses the insecure default")
    if not settings.deepgram_api_key and is_production:
        warnings.append("DEEPGRAM_API_KEY not set — voice features unavailable")
    if not settings.paypal_client_id and is_production:
        warnings.append("PAYPAL_CLIENT_ID not set — billing unavailable")
    if not settings.aws_ses_from_email and is_production:
        warnings.append("AWS_SES_FROM_EMAIL not set — email notifications unavailable")

    return warnings


enforce_sensitive_data_path_guard()

# Backward-compat module-level shims
RUNTIME_DATA_DIR = Path(settings.runtime_data_dir)
SUBSCRIPTION_DB_PATH = Path(settings.subscription_db_path)
USER_PROFILE_PATH = Path(settings.user_profile_path)
LONG_TERM_MEMORY_PATH = Path(settings.long_term_memory_path)
