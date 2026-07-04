"""Production environment configuration."""

from __future__ import annotations

import os

from .base import BaseConfig


class ProductionConfig(BaseConfig):
    """Configuration for production environment."""

    DEBUG = False
    LOG_LEVEL = "WARNING"

    # Production database settings
    DATABASE_URL = os.getenv("DATABASE_URL", "")  # Must be set in production
    DB_POOL_SIZE = 20
    DB_MAX_OVERFLOW = 40

    # Strict CORS in production
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

    # Tighter rate limits
    RATE_LIMIT_PER_MINUTE = 60

    # Security
    SECRET_KEY = os.getenv("SECRET_KEY")  # Must be set
    ALLOWED_HOSTS = (
        os.getenv("ALLOWED_HOSTS", "").split(",") if os.getenv("ALLOWED_HOSTS") else ["*"]
    )

    # Disable Swagger in production for security
    ENABLE_SWAGGER = os.getenv("ENABLE_SWAGGER", "0") == "1"

    # Longer timeouts for production load
    AI_TIMEOUT_SECONDS = 45
