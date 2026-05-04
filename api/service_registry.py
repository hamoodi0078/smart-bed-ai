"""Service registry for initializing all automation services on app startup.

Call `initialize_services(app)` from the FastAPI lifespan to set up
all Phase 1-10 services on `app.state`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from config import RUNTIME_DATA_DIR, USER_PROFILE_PATH
from Storage.io import locked_read_json

logger = logging.getLogger("api.service_registry")


def initialize_services(app: FastAPI) -> None:
    """Initialize all automation services and attach to app.state."""

    # Load user profile
    try:
        profile = locked_read_json(USER_PROFILE_PATH) or {}
    except Exception:
        profile = {}
    app.state.user_profile = profile

    # Phase 1: Core Infrastructure
    try:
        from core.backup_manager import BackupManager
        app.state.backup_manager = BackupManager(
            source_dir=Path("."),
            backup_root=RUNTIME_DATA_DIR / "backups",
        )
    except Exception as e:
        logger.warning("BackupManager init failed: %s", e)

    try:
        from core.health_monitor import HealthMonitor
        app.state.health_monitor = HealthMonitor(runtime_data_dir=RUNTIME_DATA_DIR)
    except Exception as e:
        logger.warning("HealthMonitor init failed: %s", e)

    try:
        from core.analytics_engine import AnalyticsEngine
        app.state.analytics_engine = AnalyticsEngine(
            storage_path=RUNTIME_DATA_DIR / "analytics_events.json"
        )
    except Exception as e:
        logger.warning("AnalyticsEngine init failed: %s", e)

    # Phase 2: Sleep Intelligence
    try:
        from sleep_tracking.sleep_analyzer import SleepAnalyzer
        app.state.sleep_analyzer = SleepAnalyzer()
    except Exception as e:
        logger.warning("SleepAnalyzer init failed: %s", e)

    try:
        from sleep_tracking.wake_optimizer import WakeOptimizer
        app.state.wake_optimizer = WakeOptimizer()
    except Exception as e:
        logger.warning("WakeOptimizer init failed: %s", e)

    try:
        from sleep_tracking.sleep_debt_tracker import SleepDebtTracker
        app.state.sleep_debt_tracker = SleepDebtTracker()
    except Exception as e:
        logger.warning("SleepDebtTracker init failed: %s", e)

    try:
        from sleep_tracking.nap_optimizer import NapOptimizer
        app.state.nap_optimizer = NapOptimizer()
    except Exception as e:
        logger.warning("NapOptimizer init failed: %s", e)

    # Phase 3: Islamic Mode
    try:
        from islamic_mode.prayer_automation import PrayerAutomation
        app.state.prayer_automation = PrayerAutomation()
    except Exception as e:
        logger.warning("PrayerAutomation init failed: %s", e)

    try:
        from islamic_mode.tahajjud_manager import TahajjudManager
        app.state.tahajjud_manager = TahajjudManager()
    except Exception as e:
        logger.warning("TahajjudManager init failed: %s", e)

    try:
        from islamic_mode.ramadan_mode import RamadanMode
        app.state.ramadan_mode = RamadanMode()
    except Exception as e:
        logger.warning("RamadanMode init failed: %s", e)

    # Phase 4: Presence & Context
    try:
        from hardware.pressure_intelligence import PressureIntelligence
        app.state.pressure_intelligence = PressureIntelligence()
    except Exception as e:
        logger.warning("PressureIntelligence init failed: %s", e)

    try:
        from core.presence_engine import PresenceEngine
        app.state.presence_engine = PresenceEngine()
    except Exception as e:
        logger.warning("PresenceEngine init failed: %s", e)

    try:
        from automations.bathroom_automation import BathroomAutomation
        app.state.bathroom_automation = BathroomAutomation()
    except Exception as e:
        logger.warning("BathroomAutomation init failed: %s", e)

    try:
        from guest_mode.auto_guest_detection import AutoGuestDetection
        app.state.auto_guest_detection = AutoGuestDetection()
    except Exception as e:
        logger.warning("AutoGuestDetection init failed: %s", e)

    # Phase 5: Health & Wellness
    try:
        from health.stress_detector import StressDetector
        app.state.stress_detector = StressDetector()
    except Exception as e:
        logger.warning("StressDetector init failed: %s", e)

    try:
        from health.hydration_tracker import HydrationTracker
        app.state.hydration_tracker = HydrationTracker()
    except Exception as e:
        logger.warning("HydrationTracker init failed: %s", e)

    try:
        from health.weekly_health_report import WeeklyHealthReport
        app.state.weekly_health_report = WeeklyHealthReport()
    except Exception as e:
        logger.warning("WeeklyHealthReport init failed: %s", e)

    # Phase 6: Scenes & Lighting
    try:
        from scenes.circadian_engine import CircadianEngine
        app.state.circadian_engine = CircadianEngine()
    except Exception as e:
        logger.warning("CircadianEngine init failed: %s", e)

    try:
        from scenes.weather_adaptive import WeatherAdaptive
        app.state.weather_adaptive = WeatherAdaptive()
    except Exception as e:
        logger.warning("WeatherAdaptive init failed: %s", e)

    try:
        from ai.activity_predictor import ActivityPredictor
        app.state.activity_predictor = ActivityPredictor()
    except Exception as e:
        logger.warning("ActivityPredictor init failed: %s", e)

    # Phase 7: Mobile Integration
    try:
        from integrations.geofence_manager import GeofenceManager
        app.state.geofence_manager = GeofenceManager()
    except Exception as e:
        logger.warning("GeofenceManager init failed: %s", e)

    try:
        from integrations.calendar_sync import CalendarSync
        app.state.calendar_sync = CalendarSync()
    except Exception as e:
        logger.warning("CalendarSync init failed: %s", e)

    try:
        from ai.automation_learning_engine import AutomationLearningEngine
        app.state.automation_learning = AutomationLearningEngine()
    except Exception as e:
        logger.warning("AutomationLearningEngine init failed: %s", e)

    # Phase 8: Partner Mode
    try:
        from core.partner_engine import PartnerEngine
        app.state.partner_engine = PartnerEngine()
    except Exception as e:
        logger.warning("PartnerEngine init failed: %s", e)

    try:
        from partner.compromise_engine import CompromiseEngine
        app.state.compromise_engine = CompromiseEngine()
    except Exception as e:
        logger.warning("CompromiseEngine init failed: %s", e)

    try:
        from partner.staggered_wake import StaggeredWake
        app.state.staggered_wake = StaggeredWake()
    except Exception as e:
        logger.warning("StaggeredWake init failed: %s", e)

    # Phase 9: Subscription & Engagement
    try:
        from subscriptions.trial_automation import TrialAutomation
        app.state.trial_automation = TrialAutomation()
    except Exception as e:
        logger.warning("TrialAutomation init failed: %s", e)

    try:
        from notifications.reengagement_campaigns import ReengagementCampaigns
        app.state.reengagement_campaigns = ReengagementCampaigns()
    except Exception as e:
        logger.warning("ReengagementCampaigns init failed: %s", e)

    try:
        from gamification.achievement_engine import AchievementEngine
        app.state.achievement_engine = AchievementEngine()
    except Exception as e:
        logger.warning("AchievementEngine init failed: %s", e)

    # Phase 10: Advanced Features
    try:
        from ai.personality_evolution import PersonalityEvolution
        app.state.personality_evolution = PersonalityEvolution()
    except Exception as e:
        logger.warning("PersonalityEvolution init failed: %s", e)

    try:
        from ai.dream_journal_enhanced import DreamJournalEnhanced
        app.state.dream_journal = DreamJournalEnhanced()
    except Exception as e:
        logger.warning("DreamJournalEnhanced init failed: %s", e)

    try:
        from integrations.fitness_tracker_api import FitnessTrackerAPI
        app.state.fitness_tracker = FitnessTrackerAPI()
    except Exception as e:
        logger.warning("FitnessTrackerAPI init failed: %s", e)

    logger.info("All automation services initialized successfully.")
