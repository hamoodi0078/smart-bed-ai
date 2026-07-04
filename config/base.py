"""Base configuration shared across all environments.

.. deprecated::
    The class-based config hierarchy (BaseConfig → DevelopmentConfig, etc.)
    is superseded by the Pydantic ``Settings`` singleton in
    ``config/settings.py``.  This file is kept only for backward
    compatibility — all values now delegate to ``settings``.
"""

from __future__ import annotations

import os
from pathlib import Path


# Lazy import to avoid circular dependency at module level.
def _settings():
    from config.settings import settings

    return settings


class BaseConfig:
    """Base configuration with defaults.

    Values are delegated to ``config.settings`` (Pydantic BaseSettings)
    wherever a matching field exists.  Environment-specific subclasses
    (DevelopmentConfig, ProductionConfig, …) may still override class
    attributes, but new code should use ``from config import settings``
    directly.
    """

    # Application
    APP_NAME = "Danah Abu Halifa"
    APP_VERSION = "2.0.0"
    DEBUG = False
    TESTING = False

    # Paths
    BASE_DIR = Path(__file__).resolve().parent.parent
    RUNTIME_DATA_DIR = BASE_DIR / "runtime_data"

    # API
    API_PREFIX = "/v1"
    CORS_ALLOW_CREDENTIALS = True

    # Rate Limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_PER_MINUTE = 60

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "json"  # json or text

    # Feature Flags
    ENABLE_METRICS = True
    ENABLE_HEALTH_CHECKS = True
    ENABLE_SWAGGER = True

    # ── Delegated properties ──────────────────────────────────────────
    # These read from the Pydantic settings singleton so values stay in sync.

    @property
    def CORS_ORIGINS(self):
        raw = _settings().web_allowed_origins_raw
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def DATABASE_URL(self):
        return os.getenv("DATABASE_URL", "sqlite:///./data/manues.db")

    @property
    def DB_POOL_SIZE(self):
        return _settings().db_pool_size

    @property
    def DB_MAX_OVERFLOW(self):
        return _settings().db_max_overflow

    @property
    def DB_POOL_TIMEOUT(self):
        return int(_settings().db_pool_timeout)

    @property
    def DB_POOL_RECYCLE(self):
        return _settings().db_pool_recycle

    @property
    def SECRET_KEY(self):
        return _settings().secret_key

    @property
    def DEEPGRAM_API_KEY(self):
        return _settings().deepgram_api_key

    @property
    def OPENAI_API_KEY(self):
        return _settings().openai_api_key

    @property
    def SPOTIFY_CLIENT_ID(self):
        return _settings().spotify_client_id

    @property
    def SPOTIFY_CLIENT_SECRET(self):
        return _settings().spotify_client_secret

    @property
    def AI_TIMEOUT_SECONDS(self):
        return _settings().ai_timeout_seconds

    ALLOWED_HOSTS = ["*"]
    DEFAULT_TIMEOUT_SECONDS = 20
