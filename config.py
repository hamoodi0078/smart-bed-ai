"""
GPT routing .env setup:
- Enable direct OpenAI route:
  USE_OPENAI_DIRECT=1
  OPENAI_API_KEY=your_openai_api_key
  OPENAI_CHAT_MODEL=gpt-4o-mini
  OPENAI_BASE_URL=https://api.openai.com/v1

- Optional backend proxy route (entitlement-gated cloud_chat):
  USE_BACKEND_AI_PROXY=1
  APP_BACKEND_BASE_URL=http://127.0.0.1:8001
  BED_DEVICE_ID=your_device_id
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path


def _load_local_env_file():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            parsed_value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, parsed_value)
    except Exception:
        return


_load_local_env_file()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


BASE_DIR = Path(__file__).resolve().parent


def _env_path(name: str, default_path: Path) -> Path:
    raw = str(os.getenv(name, "") or "").strip()
    candidate = Path(raw) if raw else default_path
    candidate = candidate.expanduser()
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate.resolve()


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


RUNTIME_DATA_DIR = _env_path("RUNTIME_DATA_DIR", BASE_DIR / "runtime_data")
SUBSCRIPTION_DB_PATH = _env_path("SUBSCRIPTION_DB_PATH", RUNTIME_DATA_DIR / "subscription_db.json")
USER_PROFILE_PATH = _env_path("USER_PROFILE_PATH", RUNTIME_DATA_DIR / "user_profile.json")
LONG_TERM_MEMORY_PATH = _env_path("LONG_TERM_MEMORY_PATH", RUNTIME_DATA_DIR / "long_term_memory.json")


def _assert_safe_sensitive_json_path(label: str, path: Path) -> None:
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


def enforce_sensitive_data_path_guard() -> None:
    _assert_safe_sensitive_json_path("SUBSCRIPTION_DB_PATH", SUBSCRIPTION_DB_PATH)
    _assert_safe_sensitive_json_path("USER_PROFILE_PATH", USER_PROFILE_PATH)


enforce_sensitive_data_path_guard()


@dataclass
class Settings:
    web_allowed_origins_raw: str = os.getenv("WEB_ALLOWED_ORIGINS", "http://127.0.0.1:8001,http://localhost:8001")
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    deepgram_tts_api_key: str = os.getenv("DEEPGRAM_TTS_API_KEY", os.getenv("TTS_API_KEY", os.getenv("DEEPGRAM_API_KEY", "")))
    deepgram_voice_agent_model: str = os.getenv("DEEPGRAM_VOICE_AGENT_MODEL", "voice-agent-conversational")
    deepgram_voice_agent_url: str = os.getenv("DEEPGRAM_VOICE_AGENT_URL", "https://agent.deepgram.com/v1/agent/converse")
    stt_model: str = os.getenv("DEEPGRAM_STT_MODEL", "nova-2")
    stt_mode: str = os.getenv("STT_MODE", "api")
    stt_require_api_stream: bool = os.getenv("STT_REQUIRE_API_STREAM", "0") == "1"
    stt_local_model_size: str = os.getenv("STT_LOCAL_MODEL_SIZE", "small")
    stt_local_device: str = os.getenv("STT_LOCAL_DEVICE", "cpu")
    stt_local_compute_type: str = os.getenv("STT_LOCAL_COMPUTE_TYPE", "int8")
    tts_model: str = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-thalia-en")
    tts_voice: str = os.getenv("DEEPGRAM_TTS_VOICE", "aura-2-thalia-en")
    tts_voice_therapist: str = os.getenv("DEEPGRAM_TTS_VOICE_THERAPIST", "aura-2-thalia-en")
    tts_voice_coach: str = os.getenv("DEEPGRAM_TTS_VOICE_COACH", "aura-2-orion-en")
    tts_voice_guide: str = os.getenv("DEEPGRAM_TTS_VOICE_GUIDE", "aura-2-asteria-en")
    ai_timeout_seconds: int = int(os.getenv("AI_TIMEOUT_SECONDS", "20"))
    chat_quick_timeout_seconds: int = int(os.getenv("CHAT_QUICK_TIMEOUT_SECONDS", "4"))
    chat_total_timeout_seconds: int = int(os.getenv("CHAT_TOTAL_TIMEOUT_SECONDS", "10"))
    chat_max_response_tokens: int = int(os.getenv("CHAT_MAX_RESPONSE_TOKENS", "120"))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
    language_hint: str = os.getenv("SMART_BED_LANGUAGE", "auto")
    use_api_first: bool = os.getenv("SMART_BED_API_FIRST", "1") == "1"
    local_music_dir: str = os.getenv("LOCAL_MUSIC_DIR", "local_music")
    wake_word_mode: str = os.getenv("WAKE_WORD_MODE", "keyboard")
    wake_word_phrase: str = os.getenv("WAKE_WORD_PHRASE", "hey smart bed")
    wake_word_enforce_local: bool = os.getenv("WAKE_WORD_ENFORCE_LOCAL", "1") == "1"
    wake_word_mic_index: int = _env_int("WAKE_WORD_MIC_INDEX", -1)
    wake_word_voice_timeout_seconds: int = _env_int("WAKE_WORD_TIMEOUT_SECONDS", 3)
    wake_word_phrase_limit_seconds: int = _env_int("WAKE_WORD_PHRASE_LIMIT_SECONDS", 3)
    wake_word_barge_in_timeout_seconds: int = _env_int("WAKE_WORD_BARGE_IN_TIMEOUT_SECONDS", 1)
    wake_word_barge_in_phrase_limit_seconds: int = _env_int("WAKE_WORD_BARGE_IN_PHRASE_LIMIT_SECONDS", 1)
    quiet_hours_default_window: str = os.getenv("QUIET_HOURS_DEFAULT_WINDOW", "22:00-07:00")
    quiet_hours_override_max_minutes: int = _env_int("QUIET_HOURS_OVERRIDE_MAX_MINUTES", 120)
    voice_circuit_failure_threshold: int = _env_int("VOICE_CIRCUIT_FAILURE_THRESHOLD", 3)
    voice_circuit_backoff_base_seconds: float = _env_float("VOICE_CIRCUIT_BACKOFF_BASE_SECONDS", 3.0)
    voice_circuit_backoff_max_seconds: float = _env_float("VOICE_CIRCUIT_BACKOFF_MAX_SECONDS", 60.0)
    voice_circuit_reset_signal_path: str = str(
        _env_path("VOICE_CIRCUIT_RESET_SIGNAL_PATH", RUNTIME_DATA_DIR / "voice_circuit_reset_signal.json")
    )
    enable_sensor_bridge: bool = os.getenv("ENABLE_SENSOR_BRIDGE", "1") == "1"
    sensor_pressure_enabled: bool = os.getenv("SENSOR_PRESSURE_ENABLED", "0") == "1"
    sensor_motion_enabled: bool = os.getenv("SENSOR_MOTION_ENABLED", "0") == "1"
    aec_min_confidence_when_playing: float = float(os.getenv("AEC_MIN_CONFIDENCE_WHEN_PLAYING", "0.72"))
    spotify_access_token: str = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
    spotify_device_id: str = os.getenv("SPOTIFY_DEVICE_ID", "")
    spotify_default_playlist_uri: str = os.getenv("SPOTIFY_DEFAULT_PLAYLIST_URI", "")
    spotify_client_id: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    spotify_client_secret: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    spotify_scopes: str = os.getenv(
        "SPOTIFY_SCOPES",
        "user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-email user-read-private",
    )
    spotify_redirect_uri: str = os.getenv(
        "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/spotify/callback"
    )
    app_base_url: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    app_backend_base_url: str = os.getenv("APP_BACKEND_BASE_URL", "http://127.0.0.1:8000")
    bed_device_id: str = os.getenv("BED_DEVICE_ID", "")
    bed_firmware_version: str = os.getenv("BED_FIRMWARE_VERSION", "1.0.0")
    use_backend_ai_proxy: bool = os.getenv("USE_BACKEND_AI_PROXY", "1") == "1"
    use_openai_direct: bool = os.getenv("USE_OPENAI_DIRECT", "0") == "1"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    user_strip_pin: int = int(os.getenv("USER_STRIP_PIN", "18"))
    state_strip_pin: int = int(os.getenv("STATE_STRIP_PIN", "13"))
    user_strip_led_count: int = int(os.getenv("USER_STRIP_LED_COUNT", "120"))
    state_strip_led_count: int = int(os.getenv("STATE_STRIP_LED_COUNT", "60"))
    runtime_data_dir: str = str(RUNTIME_DATA_DIR)


settings = Settings()
