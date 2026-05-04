"""Base configuration shared across all environments."""
from __future__ import annotations

import os
from pathlib import Path


class BaseConfig:
    """Base configuration with defaults."""

    # Application
    APP_NAME = "Danah Abu Halifa"
    APP_VERSION = "1.0.0"
    DEBUG = False
    TESTING = False

    # Paths
    BASE_DIR = Path(__file__).resolve().parent.parent
    RUNTIME_DATA_DIR = BASE_DIR / "runtime_data"

    # API
    API_PREFIX = "/v1"
    CORS_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]
    CORS_ALLOW_CREDENTIALS = True

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/manues.db")
    DB_POOL_SIZE = 10
    DB_MAX_OVERFLOW = 20
    DB_POOL_TIMEOUT = 30
    DB_POOL_RECYCLE = 3600

    # Rate Limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_PER_MINUTE = 60

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "json"  # json or text

    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    ALLOWED_HOSTS = ["*"]

    # External Services
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

    # Timeouts
    DEFAULT_TIMEOUT_SECONDS = 20
    AI_TIMEOUT_SECONDS = 30

    # Feature Flags
    ENABLE_METRICS = True
    ENABLE_HEALTH_CHECKS = True
    ENABLE_SWAGGER = True
