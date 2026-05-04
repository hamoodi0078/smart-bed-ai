"""Testing environment configuration."""
from __future__ import annotations

from .base import BaseConfig


class TestingConfig(BaseConfig):
    """Configuration for testing environment."""

    TESTING = True
    DEBUG = True
    LOG_LEVEL = "DEBUG"

    # In-memory database for tests
    DATABASE_URL = "sqlite:///:memory:"

    # Disable rate limiting in tests
    RATE_LIMIT_ENABLED = False

    # Fast timeouts for tests
    DEFAULT_TIMEOUT_SECONDS = 5
    AI_TIMEOUT_SECONDS = 5

    # All features enabled
    ENABLE_METRICS = True
    ENABLE_HEALTH_CHECKS = True
    ENABLE_SWAGGER = True
