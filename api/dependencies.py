"""FastAPI dependencies for dependency injection."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request

from core.service_registry import ServiceRegistry

try:
    from database import (
        AsyncDatabaseConnection,
        AsyncEventRepository,
        AsyncSleepSessionRepository,
        AsyncUserRepository,
    )
    _ASYNC_DB_AVAILABLE = True
except ImportError as _async_db_import_error:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Async database layer unavailable — routes that depend on it will fail at runtime. "
        "Import error: %s",
        _async_db_import_error,
    )
    _ASYNC_DB_AVAILABLE = False


def get_service_registry(request: Request) -> ServiceRegistry:
    """Get the service registry from app state.

    Args:
        request: FastAPI request object

    Returns:
        ServiceRegistry instance
    """
    return request.app.state.services


def get_user_profile(request: Request) -> dict[str, Any]:
    """Get the current user profile from app state.

    Args:
        request: FastAPI request object

    Returns:
        User profile dictionary
    """
    return getattr(request.app.state, "user_profile", {})


def get_trace_id(request: Request) -> str:
    """Get the trace ID for the current request.

    Args:
        request: FastAPI request object

    Returns:
        Trace ID string
    """
    return getattr(request.state, "trace_id", "")


# Service-specific dependencies
def get_backup_manager(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get BackupManager service."""
    return registry.get("backup_manager")


def get_health_monitor(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get HealthMonitor service."""
    return registry.get("health_monitor")


def get_analytics_engine(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get AnalyticsEngine service."""
    return registry.get("analytics_engine")


def get_sleep_analyzer(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get SleepAnalyzer service."""
    return registry.get("sleep_analyzer")


def get_wake_optimizer(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get WakeOptimizer service."""
    return registry.get("wake_optimizer")


def get_sleep_debt_tracker(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get SleepDebtTracker service."""
    return registry.get("sleep_debt_tracker")


def get_nap_optimizer(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get NapOptimizer service."""
    return registry.get("nap_optimizer")


def get_prayer_automation(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get PrayerAutomation service."""
    return registry.get("prayer_automation")


def get_tahajjud_manager(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get TahajjudManager service."""
    return registry.get("tahajjud_manager")


def get_ramadan_mode(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get RamadanMode service."""
    return registry.get("ramadan_mode")


def get_pressure_intelligence(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get PressureIntelligence service."""
    return registry.get("pressure_intelligence")


def get_presence_engine(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get PresenceEngine service."""
    return registry.get("presence_engine")


def get_auto_guest_detection(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get AutoGuestDetection service."""
    return registry.get("auto_guest_detection")


def get_stress_detector(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get StressDetector service."""
    return registry.get("stress_detector")


def get_hydration_tracker(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get HydrationTracker service."""
    return registry.get("hydration_tracker")


def get_weekly_health_report(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get WeeklyHealthReport service."""
    return registry.get("weekly_health_report")


def get_circadian_engine(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get CircadianEngine service."""
    return registry.get("circadian_engine")


def get_weather_adaptive(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get WeatherAdaptive service."""
    return registry.get("weather_adaptive")


def get_activity_predictor(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get ActivityPredictor service."""
    return registry.get("activity_predictor")


def get_geofence_manager(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get GeofenceManager service."""
    return registry.get("geofence_manager")


def get_calendar_sync(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get CalendarSync service."""
    return registry.get("calendar_sync")


def get_automation_learning(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get AutomationLearning service."""
    return registry.get("automation_learning")


def get_partner_engine(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get PartnerEngine service."""
    return registry.get("partner_engine")


def get_compromise_engine(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get CompromiseEngine service."""
    return registry.get("compromise_engine")


def get_staggered_wake(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get StaggeredWake service."""
    return registry.get("staggered_wake")


def get_trial_automation(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get TrialAutomation service."""
    return registry.get("trial_automation")


def get_reengagement_campaigns(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get ReengagementCampaigns service."""
    return registry.get("reengagement_campaigns")


def get_achievement_engine(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get AchievementEngine service."""
    return registry.get("achievement_engine")


def get_personality_evolution(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get PersonalityEvolution service."""
    return registry.get("personality_evolution")


def get_dream_journal(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get DreamJournal service."""
    return registry.get("dream_journal")


def get_fitness_tracker(registry: ServiceRegistry = Depends(get_service_registry)):
    """Get FitnessTracker service."""
    return registry.get("fitness_tracker")


# ---------------------------------------------------------------------------
# Async DB dependencies (asyncpg-backed)
# ---------------------------------------------------------------------------

async def get_async_db(request: Request) -> "AsyncDatabaseConnection":
    """Get the async PostgreSQL connection pool from app state."""
    return request.app.state.async_db


async def get_async_user_repo(
    db: "AsyncDatabaseConnection" = Depends(get_async_db),
) -> "AsyncUserRepository":
    """Get an async User repository backed by asyncpg."""
    return AsyncUserRepository(db)


async def get_async_sleep_repo(
    db: "AsyncDatabaseConnection" = Depends(get_async_db),
) -> "AsyncSleepSessionRepository":
    """Get an async SleepSession repository backed by asyncpg."""
    return AsyncSleepSessionRepository(db)


async def get_async_event_repo(
    db: "AsyncDatabaseConnection" = Depends(get_async_db),
) -> "AsyncEventRepository":
    """Get an async Event repository backed by asyncpg."""
    return AsyncEventRepository(db)


async def get_pgvector_index(request: Request) -> "Any":
    """Get the PgVectorMemoryIndex from app state (None if pgvector unavailable)."""
    return getattr(request.app.state, "pgvector_index", None)


async def get_arq(request: Request) -> "Any":
    """Get the arq job queue pool from app state (None if Redis unavailable)."""
    return getattr(request.app.state, "arq", None)


async def get_fcm_sender(request: Request) -> "Any":
    """Get the FcmSender from app state (None if Firebase unconfigured)."""
    return getattr(request.app.state, "fcm_sender", None)


# ---------------------------------------------------------------------------
# Authentication dependencies
# ---------------------------------------------------------------------------

async def get_db_session(request: Request):
    """Get async database session from app state."""
    if hasattr(request.app.state, "db_session_factory"):
        async with request.app.state.db_session_factory() as session:
            yield session
    else:
        raise RuntimeError("Database session factory not available")


# Re-export auth middleware dependencies
from auth.middleware import (
    get_current_user,
    get_current_user_optional,
    require_role,
)

__all__ = [
    "get_service_registry",
    "get_user_profile",
    "get_trace_id",
    "get_async_db",
    "get_async_user_repo",
    "get_async_sleep_repo",
    "get_async_event_repo",
    "get_db_session",
    "get_current_user",
    "get_current_user_optional",
    "require_role",
]
