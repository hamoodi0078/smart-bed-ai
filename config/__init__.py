"""Configuration module — runtime settings + environment-based config classes."""

from __future__ import annotations

import os

# Determine environment
ENV = os.getenv("ENVIRONMENT", "development").lower()

# Import the appropriate env-class config
if ENV == "production":
    from .production import ProductionConfig as Config
elif ENV == "staging":
    from .staging import StagingConfig as Config
elif ENV == "testing":
    from .testing import TestingConfig as Config
else:
    from .development import DevelopmentConfig as Config

config = Config()

# Pydantic-settings based operational settings (imported by the rest of the app)
from .settings import (  # noqa: E402
    Settings,
    settings,
    enforce_sensitive_data_path_guard,
    RUNTIME_DATA_DIR,
    SUBSCRIPTION_DB_PATH,
    USER_PROFILE_PATH,
    LONG_TERM_MEMORY_PATH,
)

__all__ = [
    "config",
    "Config",
    "ENV",
    "Settings",
    "settings",
    "enforce_sensitive_data_path_guard",
    "RUNTIME_DATA_DIR",
    "SUBSCRIPTION_DB_PATH",
    "USER_PROFILE_PATH",
    "LONG_TERM_MEMORY_PATH",
]
