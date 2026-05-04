"""
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

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


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
        validation_alias=AliasChoices("DEEPGRAM_TTS_API_KEY", "TTS_API_KEY", "DEEPGRAM_API_KEY", "deepgram_tts_api_key"),
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
        validation_alias=AliasChoices("WAKE_WORD_TIMEOUT_SECONDS", "wake_word_voice_timeout_seconds"),
    )
    wake_word_phrase_limit_seconds: int = 3
    wake_word_barge_in_timeout_seconds: int = 1
    wake_word_barge_in_phrase_limit_seconds: int = 1

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
        # Resolve runtime_data_dir first
        if not self.runtime_data_dir:
            rdd = (BASE_DIR / "runtime_data").resolve()
        else:
            p = Path(self.runtime_data_dir).expanduser()
            rdd = (BASE_DIR / p if not p.is_absolute() else p).resolve()
        self.runtime_data_dir = str(rdd)

        # Fill derived paths only when not explicitly set via env
        if not self.subscription_db_path:
            self.subscription_db_path = str(rdd / "subscription_db.json")
        if not self.user_profile_path:
            self.user_profile_path = str(rdd / "user_profile.json")
        if not self.long_term_memory_path:
            self.long_term_memory_path = str(rdd / "long_term_memory.json")
        if not self.voice_circuit_reset_signal_path:
            self.voice_circuit_reset_signal_path = str(rdd / "voice_circuit_reset_signal.json")
        if not self.islamic_prayer_cache_path:
            self.islamic_prayer_cache_path = str(rdd / "prayer_times_cache.json")

        return self


settings = Settings()


def enforce_sensitive_data_path_guard() -> None:
    _assert_safe_sensitive_json_path("SUBSCRIPTION_DB_PATH", Path(settings.subscription_db_path))
    _assert_safe_sensitive_json_path("USER_PROFILE_PATH", Path(settings.user_profile_path))


enforce_sensitive_data_path_guard()

# ── Backward-compat module-level shims (other files import these directly) ──
RUNTIME_DATA_DIR = Path(settings.runtime_data_dir)
SUBSCRIPTION_DB_PATH = Path(settings.subscription_db_path)
USER_PROFILE_PATH = Path(settings.user_profile_path)
LONG_TERM_MEMORY_PATH = Path(settings.long_term_memory_path)