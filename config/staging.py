"""Staging environment configuration."""
from __future__ import annotations

from .base import BaseConfig


class StagingConfig(BaseConfig):
    """Configuration for staging environment."""

    DEBUG = False
    LOG_LEVEL = "INFO"

    # Staging uses production-like settings
    DB_POOL_SIZE = 15
    DB_MAX_OVERFLOW = 30

    # Moderate rate limits
    RATE_LIMIT_PER_MINUTE = 100

    # All features enabled for testing
    ENABLE_METRICS = True
    ENABLE_HEALTH_CHECKS = True
    ENABLE_SWAGGER = True
