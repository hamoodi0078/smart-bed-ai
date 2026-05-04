"""Scene and environment constants."""

from __future__ import annotations


class SceneDefaults:
    """Default scene configuration values."""

    DEFAULT_BRIGHTNESS: float = 0.65
    MIN_BRIGHTNESS: float = 0.0
    MAX_BRIGHTNESS: float = 1.0
    SLEEP_BRIGHTNESS: float = 0.2
    WAKE_BRIGHTNESS: float = 0.35
    DEFAULT_COLOR: str = "warm_white"
    DEFAULT_ANIMATION: str = "breathing"


class SleepScoring:
    """Sleep scoring thresholds."""

    HIGH_READINESS: int = 80
    MEDIUM_READINESS: int = 60
    DEFAULT_READINESS: int = 70
    CONSISTENCY_BONUS: int = 5
    CONSISTENCY_PENALTY: int = -5
    GOOD_BEDTIME_BONUS: int = 10
    LATE_BEDTIME_PENALTY: int = -10
    MIN_SESSIONS_FOR_BONUS: int = 3
    MIN_SCORE: int = 0
    MAX_SCORE: int = 100


class TimeWindows:
    """Time-of-day window boundaries (24h format)."""

    EVENING_START: int = 20
    LATE_EVENING_START: int = 22
    NIGHT_START: int = 23
    EARLY_MORNING_END: int = 4
    MORNING_END: int = 9
    GOOD_BEDTIME_START: int = 21
    GOOD_BEDTIME_END: int = 23
