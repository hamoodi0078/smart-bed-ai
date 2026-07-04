"""Development environment configuration."""

from __future__ import annotations

from .base import BaseConfig


class DevelopmentConfig(BaseConfig):
    """Configuration for development environment."""

    DEBUG = True
    LOG_LEVEL = "DEBUG"

    # More verbose logging in development
    DB_POOL_SIZE = 5
    DB_MAX_OVERFLOW = 10

    # Relaxed rate limits for development
    RATE_LIMIT_PER_MINUTE = 200

    # Enable all features for testing
    ENABLE_METRICS = True
    ENABLE_HEALTH_CHECKS = True
    ENABLE_SWAGGER = True
