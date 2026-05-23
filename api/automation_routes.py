"""API routes for all new automation features (Phases 1-10).

Provides REST endpoints for backup, health monitoring, analytics, sleep analysis,
wake optimization, sleep debt, nap detection, prayer automation, Ramadan mode,
Tahajjud, pressure intelligence, presence, bathroom automation, guest detection,
stress detection, hydration, weekly report, circadian, weather, activity prediction,
geofencing, calendar sync, automation learning, partner mode, compromise scenes,
staggered wake, trial automation, re-engagement, achievements, personality evolution,
dream journal, and fitness tracker integration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.dependencies import (
    get_achievement_engine,
    get_activity_predictor,
    get_analytics_engine,
    get_auto_guest_detection,
    get_backup_manager,
    get_calendar_sync,
    get_circadian_engine,
    get_compromise_engine,
    get_dream_journal,
    get_fitness_tracker,
    get_geofence_manager,
    get_health_monitor,
    get_hydration_tracker,
    get_nap_optimizer,
    get_partner_engine,
    get_personality_evolution,
    get_prayer_automation,
    get_presence_engine,
    get_pressure_intelligence,
    get_ramadan_mode,
    get_reengagement_campaigns,
    get_sleep_analyzer,
    get_sleep_debt_tracker,
    get_staggered_wake,
    get_stress_detector,
    get_tahajjud_manager,
    get_trial_automation,
    get_user_profile,
    get_wake_optimizer,
    get_weather_adaptive,
    get_weekly_health_report,
    get_automation_learning,
)

logger = logging.getLogger("api.automation_routes")

router = APIRouter(prefix="/v1/automation", tags=["automation"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class PressureReading(BaseModel):
    left: float = 0.0
    right: float = 0.0


class DreamEntry(BaseModel):
    text: str
    vivid: bool = False
    lucid: bool = False


class CalendarEvents(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)


class LocationUpdate(BaseModel):
    latitude: float
    longitude: float


class AutomationResponse(BaseModel):
    automation_id: str
    response: str  # accepted, declined, snoozed, never


class BiometricData(BaseModel):
    heart_rate: float | None = None
    hrv: float | None = None
    spo2: float | None = None
    temperature: float | None = None
    steps: int | None = None
    calories: int | None = None


class HydrationLog(BaseModel):
    ml: int = 0


class QuranPages(BaseModel):
    pages: int


class CoupleChallenge(BaseModel):
    name: str
    description: str = ""
    target_days: int = 7


class ActivityRecord(BaseModel):
    activity: str
    duration_minutes: float = 0


class SleepRecord(BaseModel):
    partner: str
    hours: float
    score: int


def _utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


# ===================================================================
# PHASE 1: Core Infrastructure
# ===================================================================

@router.post("/backup/run")
async def run_backup(
    backup_type: str = "daily",
    mgr = Depends(get_backup_manager),
):
    """Run a backup of the specified type."""
    return mgr.run_backup(backup_type)


@router.get("/backup/list")
async def list_backups(
    backup_type: str = "",
    mgr = Depends(get_backup_manager),
):
    """List available backups."""
    return mgr.list_backups(backup_type)


@router.post("/backup/validate")
async def validate_backup(
    backup_path: str,
    mgr = Depends(get_backup_manager),
):
    """Validate a backup file."""
    return mgr.validate_backup(backup_path)


@router.get("/health")
async def health_check(mon = Depends(get_health_monitor)):
    """Get health summary for automation services."""
    return mon.get_health_summary()


@router.get("/health/details")
async def health_details(mon = Depends(get_health_monitor)):
    """Get detailed health check results."""
    return mon.run_all_checks()


@router.get("/health/recovery-log")
async def health_recovery_log(mon = Depends(get_health_monitor)):
    """Get health recovery log."""
    return mon.get_recovery_log()


@router.post("/analytics/track")
async def track_event(request: Request, event_type: str, user_id: str = ""):
    eng = _get_service(request, "analytics_engine")
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return eng.track(event_type, user_id=user_id, metadata=body)


@router.get("/analytics/events")
async def get_events(request: Request, event_type: str = "", days: int = 7, limit: int = 100):
    eng = _get_service(request, "analytics_engine")
    from datetime import timedelta
    since = _utcnow() - timedelta(days=max(1, days))
    return eng.get_events(event_type=event_type, since=since, limit=limit)


@router.get("/analytics/engagement")
async def get_engagement(request: Request, user_id: str = "", days: int = 7):
    eng = _get_service(request, "analytics_engine")
    return eng.calculate_engagement_score(user_id, days)


@router.get("/analytics/features")
async def get_feature_adoption(request: Request, user_id: str = "", days: int = 30):
    eng = _get_service(request, "analytics_engine")
    return eng.feature_adoption(user_id, days)


@router.get("/analytics/charts/sleep-trend")
async def chart_sleep_trend(request: Request, user_id: str = "", days: int = 30):
    """Plotly figure JSON for sleep hours + score over the last N days."""
    eng = _get_service(request, "analytics_engine")
    trend = eng.sleep_trend(user_id, days)
    from reports.chart_generator import sleep_trend_chart
    return sleep_trend_chart(trend)


@router.get("/analytics/charts/daily-activity")
async def chart_daily_activity(request: Request, user_id: str = "", days: int = 30):
    """Plotly figure JSON for daily event counts over the last N days."""
    eng = _get_service(request, "analytics_engine")
    daily = eng.daily_active_events(user_id=user_id, days=days)
    from reports.chart_generator import daily_activity_chart
    return daily_activity_chart(daily)


@router.get("/analytics/charts/automation-effectiveness")
async def chart_automation_effectiveness(request: Request, user_id: str = "", days: int = 30):
    """Plotly figure JSON for automation acceptance vs decline donut chart."""
    eng = _get_service(request, "analytics_engine")
    data = eng.automation_effectiveness(user_id, days)
    from reports.chart_generator import automation_effectiveness_chart
    return automation_effectiveness_chart(data)


@router.get("/analytics/charts/feature-adoption")
async def chart_feature_adoption(request: Request, user_id: str = "", days: int = 30):
    """Plotly figure JSON for per-feature usage horizontal bar chart."""
    eng = _get_service(request, "analytics_engine")
    data = eng.feature_adoption(user_id, days)
    from reports.chart_generator import feature_adoption_chart
    return feature_adoption_chart(data)


# ===================================================================
# PHASE 2: Sleep Intelligence
# ===================================================================

@router.get("/sleep/patterns")
async def sleep_patterns(request: Request):
    analyzer = _get_service(request, "sleep_analyzer")
    profile = _get_profile(request)
    return analyzer.analyze_patterns(profile)


@router.get("/sleep/predict-bedtime")
async def predict_bedtime(request: Request, target_wake: str = ""):
    analyzer = _get_service(request, "sleep_analyzer")
    profile = _get_profile(request)
    return analyzer.predict_bedtime(profile, target_wake)


@router.get("/sleep/drift")
async def bedtime_drift(request: Request, days: int = 7):
    analyzer = _get_service(request, "sleep_analyzer")
    profile = _get_profile(request)
    return analyzer.detect_bedtime_drift(profile, days)


@router.get("/sleep/wake-status")
async def wake_status(request: Request):
    optimizer = _get_service(request, "wake_optimizer")
    return optimizer.get_status()


@router.get("/sleep/wake-sequence")
async def wake_sequence(request: Request):
    optimizer = _get_service(request, "wake_optimizer")
    status = optimizer.get_status()
    alarm = status.get("alarm_time")
    if not alarm:
        return {"sequence": [], "message": "No alarm set."}
    from datetime import datetime as dt
    alarm_dt = dt.fromisoformat(alarm)
    return {"sequence": optimizer.get_wake_sequence(alarm_dt)}


@router.get("/sleep/quality-estimate")
async def sleep_quality_estimate(request: Request):
    optimizer = _get_service(request, "wake_optimizer")
    return optimizer.get_sleep_quality_estimate()


@router.get("/sleep/debt")
async def sleep_debt(request: Request, days: int = 7):
    tracker = _get_service(request, "sleep_debt_tracker")
    profile = _get_profile(request)
    return tracker.calculate_debt(profile, days)


@router.get("/sleep/debt/recovery-plan")
async def debt_recovery_plan(request: Request):
    tracker = _get_service(request, "sleep_debt_tracker")
    profile = _get_profile(request)
    return tracker.get_recovery_plan(profile)


@router.get("/sleep/debt/weekend")
async def weekend_compensation(request: Request):
    tracker = _get_service(request, "sleep_debt_tracker")
    profile = _get_profile(request)
    return tracker.get_weekend_compensation(profile)


@router.get("/sleep/smart-insight")
async def smart_sleep_insight(request: Request):
    """Single AI-generated headline combining bedtime prediction, drift, and debt."""
    analyzer = _get_service(request, "sleep_analyzer")
    tracker = _get_service(request, "sleep_debt_tracker")
    profile = _get_profile(request)

    try:
        patterns = analyzer.analyze_patterns(profile)
        drift = analyzer.detect_bedtime_drift(profile, days=7)
        debt = tracker.calculate_debt(profile, days=7)
        predicted = analyzer.predict_bedtime(profile, target_wake="")
    except Exception:
        patterns, drift, debt, predicted = {}, {}, {}, {}

    drift_mins = int(drift.get("drift_minutes") or 0)
    debt_h = float(debt.get("debt_hours") or 0)
    consistency = float(patterns.get("consistency_score") or 0)
    recommended = predicted.get("recommended_bedtime") or "10:30 PM"

    if debt_h >= 2.0:
        headline = f"You have {debt_h:.1f}h sleep debt. Tonight, aim for {recommended}."
    elif abs(drift_mins) > 30:
        direction = "later" if drift_mins > 0 else "earlier"
        headline = f"Your bedtime has drifted {abs(drift_mins)} min {direction} this week."
    elif consistency >= 0.8:
        headline = "Excellent sleep consistency this week. Your rhythm is healthy."
    else:
        headline = f"Target bedtime: {recommended} for your best sleep tonight."

    return {
        "headline": headline,
        "consistency_score": consistency,
        "debt_hours": debt_h,
        "recommended_bedtime": recommended,
        "drift_minutes": drift_mins,
    }


@router.get("/sleep/nap/suggest")
async def nap_suggestion(request: Request):
    nap = _get_service(request, "nap_optimizer")
    profile = _get_profile(request)
    return nap.suggest_nap(profile)


@router.get("/sleep/nap/stats")
async def nap_stats(request: Request, days: int = 30):
    nap = _get_service(request, "nap_optimizer")
    profile = _get_profile(request)
    return nap.get_nap_stats(profile, days)


# ===================================================================
# PHASE 3: Islamic Mode
# ===================================================================

@router.get("/islamic/prayer/status")
async def prayer_status(request: Request):
    pa = _get_service(request, "prayer_automation")
    profile = _get_profile(request)
    return pa.get_prayer_status(profile)


@router.post("/islamic/prayer/acknowledge")
async def acknowledge_prayer(request: Request, prayer_name: str):
    pa = _get_service(request, "prayer_automation")
    profile = _get_profile(request)
    return pa.acknowledge_prayer(profile, prayer_name)


@router.post("/islamic/prayer-mat/activate")
async def activate_prayer_mat(request: Request):
    pa = _get_service(request, "prayer_automation")
    profile = _get_profile(request)
    return pa.activate_prayer_mat_mode(profile)


@router.post("/islamic/prayer-mat/deactivate")
async def deactivate_prayer_mat(request: Request):
    pa = _get_service(request, "prayer_automation")
    return pa.deactivate_prayer_mat_mode()


@router.get("/islamic/tahajjud/status")
async def tahajjud_status(request: Request):
    tm = _get_service(request, "tahajjud_manager")
    profile = _get_profile(request)
    return tm.get_stats(profile)


@router.get("/islamic/tahajjud/last-third")
async def tahajjud_last_third(request: Request):
    tm = _get_service(request, "tahajjud_manager")
    return tm.calculate_last_third()


@router.post("/islamic/tahajjud/prayed")
async def tahajjud_prayed(request: Request):
    tm = _get_service(request, "tahajjud_manager")
    profile = _get_profile(request)
    return tm.record_tahajjud_prayed(profile)


@router.post("/islamic/tahajjud/skipped")
async def tahajjud_skipped(request: Request):
    tm = _get_service(request, "tahajjud_manager")
    profile = _get_profile(request)
    return tm.record_tahajjud_skipped(profile)


@router.get("/islamic/ramadan/progress")
async def ramadan_progress(request: Request):
    rm = _get_service(request, "ramadan_mode")
    profile = _get_profile(request)
    return rm.get_ramadan_progress(profile)


@router.post("/islamic/ramadan/quran")
async def log_quran_pages(request: Request, body: QuranPages):
    rm = _get_service(request, "ramadan_mode")
    profile = _get_profile(request)
    return rm.log_quran_pages(profile, body.pages)


# ===================================================================
# PHASE 4: Presence & Context
# ===================================================================

@router.post("/pressure/record")
async def record_pressure(request: Request, body: PressureReading):
    pi = _get_service(request, "pressure_intelligence")
    pi.record(body.left, body.right)
    return pi.get_occupancy_dict()


@router.get("/pressure/occupancy")
async def get_occupancy(request: Request):
    pi = _get_service(request, "pressure_intelligence")
    return pi.get_occupancy_dict()


@router.get("/pressure/events")
async def pressure_events(request: Request, limit: int = 20):
    pi = _get_service(request, "pressure_intelligence")
    return pi.get_recent_events(limit)


@router.get("/pressure/restlessness")
async def restlessness(request: Request, minutes: int = 60):
    pi = _get_service(request, "pressure_intelligence")
    return pi.get_restlessness_score(minutes)


@router.get("/presence/context")
async def presence_context(request: Request):
    pe = _get_service(request, "presence_engine")
    return pe.get_context()


@router.get("/presence/automation-context")
async def presence_automation_ctx(request: Request):
    pe = _get_service(request, "presence_engine")
    return pe.get_automation_context()


@router.get("/guest/detection/status")
async def guest_detection_status(request: Request):
    gd = _get_service(request, "auto_guest_detection")
    profile = _get_profile(request)
    return gd.get_status(profile)


# ===================================================================
# PHASE 5: Health & Wellness
# ===================================================================

@router.get("/health/stress")
async def stress_status(request: Request):
    sd = _get_service(request, "stress_detector")
    profile = _get_profile(request)
    pi = request.app.state.__dict__.get("pressure_intelligence")
    restlessness = 0.0
    if pi:
        r = pi.get_restlessness_score(60)
        restlessness = float(r.get("score", 0))
    return sd.evaluate(profile, restlessness_per_hour=restlessness)


@router.get("/health/stress/stats")
async def stress_stats(request: Request, days: int = 30):
    sd = _get_service(request, "stress_detector")
    profile = _get_profile(request)
    return sd.get_stats(profile, days)


@router.post("/health/hydration/log")
async def log_hydration(request: Request, body: HydrationLog):
    ht = _get_service(request, "hydration_tracker")
    profile = _get_profile(request)
    return ht.log_intake(profile, body.ml)


@router.get("/health/hydration/today")
async def hydration_today(request: Request):
    ht = _get_service(request, "hydration_tracker")
    profile = _get_profile(request)
    return ht.get_today(profile)


@router.get("/health/hydration/stats")
async def hydration_stats(request: Request, days: int = 30):
    ht = _get_service(request, "hydration_tracker")
    profile = _get_profile(request)
    return ht.get_stats(profile, days)


@router.get("/health/weekly-report")
async def weekly_report(request: Request):
    wr = _get_service(request, "weekly_health_report")
    profile = _get_profile(request)
    return wr.generate(profile)


# ===================================================================
# PHASE 6: Scenes & Lighting
# ===================================================================

@router.get("/scenes/circadian")
async def circadian_settings(request: Request):
    ce = _get_service(request, "circadian_engine")
    return ce.get_interpolated_settings()


@router.get("/scenes/circadian/schedule")
async def circadian_schedule(request: Request):
    ce = _get_service(request, "circadian_engine")
    return ce.get_full_schedule()


@router.get("/scenes/circadian/blue-light")
async def blue_light_status(request: Request):
    ce = _get_service(request, "circadian_engine")
    profile = _get_profile(request)
    return ce.get_blue_light_status(profile)


@router.get("/scenes/weather")
async def weather_adjustments(request: Request):
    wa = _get_service(request, "weather_adaptive")
    profile = _get_profile(request)
    return wa.get_adjustments(profile)


@router.get("/scenes/activity/predict")
async def predict_activity(request: Request):
    ap = _get_service(request, "activity_predictor")
    profile = _get_profile(request)
    return ap.predict(profile)


@router.post("/scenes/activity/record")
async def record_activity(request: Request, body: ActivityRecord):
    ap = _get_service(request, "activity_predictor")
    profile = _get_profile(request)
    return ap.record_activity(profile, body.activity, duration_minutes=body.duration_minutes)


@router.get("/scenes/activity/patterns")
async def activity_patterns(request: Request):
    ap = _get_service(request, "activity_predictor")
    profile = _get_profile(request)
    return ap.get_patterns(profile)


# ===================================================================
# PHASE 7: Mobile Integration
# ===================================================================

@router.post("/mobile/location")
async def update_location(request: Request, body: LocationUpdate):
    gf = _get_service(request, "geofence_manager")
    profile = _get_profile(request)
    return gf.update_location(profile, body.latitude, body.longitude)


@router.get("/mobile/geofence/status")
async def geofence_status(request: Request):
    gf = _get_service(request, "geofence_manager")
    profile = _get_profile(request)
    return gf.get_status(profile)


@router.post("/mobile/calendar/sync")
async def sync_calendar(request: Request, body: CalendarEvents):
    cs = _get_service(request, "calendar_sync")
    profile = _get_profile(request)
    return cs.sync_events(profile, body.events)


@router.get("/mobile/calendar/tomorrow")
async def calendar_tomorrow(request: Request):
    cs = _get_service(request, "calendar_sync")
    profile = _get_profile(request)
    return cs.get_tomorrow_schedule(profile)


@router.get("/mobile/calendar/morning-brief")
async def morning_brief(request: Request):
    cs = _get_service(request, "calendar_sync")
    profile = _get_profile(request)
    return cs.get_morning_brief(profile)


@router.post("/mobile/automation-response")
async def automation_response(request: Request, body: AutomationResponse):
    le = _get_service(request, "automation_learning")
    profile = _get_profile(request)
    return le.record_response(profile, body.automation_id, body.response)


@router.get("/mobile/automation-report")
async def automation_report(request: Request):
    le = _get_service(request, "automation_learning")
    profile = _get_profile(request)
    return le.get_automation_report(profile)


@router.get("/mobile/automation-insights")
async def automation_insights(request: Request):
    le = _get_service(request, "automation_learning")
    profile = _get_profile(request)
    return le.get_monthly_insights(profile)


# ===================================================================
# PHASE 8: Partner Mode
# ===================================================================

@router.get("/partner/status")
async def partner_status(request: Request):
    pe = _get_service(request, "partner_engine")
    profile = _get_profile(request)
    pi = request.app.state.__dict__.get("pressure_intelligence")
    if pi:
        occ = pi.get_occupancy_dict()
        return pe.identify_from_pressure(profile, occ.get("left_occupied", False), occ.get("right_occupied", False))
    return {"partner_mode": False, "reason": "No pressure data."}


@router.get("/partner/comparison")
async def partner_comparison(request: Request, days: int = 7):
    pe = _get_service(request, "partner_engine")
    profile = _get_profile(request)
    return pe.get_comparison(profile, days)


@router.post("/partner/sleep")
async def record_partner_sleep(request: Request, body: SleepRecord):
    pe = _get_service(request, "partner_engine")
    profile = _get_profile(request)
    return pe.record_sleep(profile, body.partner, body.hours, body.score)


@router.get("/partner/achievements")
async def couple_achievements(request: Request):
    pe = _get_service(request, "partner_engine")
    profile = _get_profile(request)
    return pe.get_couple_achievements(profile)


@router.post("/partner/challenge")
async def add_challenge(request: Request, body: CoupleChallenge):
    pe = _get_service(request, "partner_engine")
    profile = _get_profile(request)
    return pe.add_couple_challenge(profile, body.model_dump())


@router.get("/partner/compromise")
async def get_compromise(request: Request):
    ce = _get_service(request, "compromise_engine")
    profile = _get_profile(request)
    pi = request.app.state.__dict__.get("pressure_intelligence")
    both = pi.is_partner_present() if pi else False
    return ce.resolve_scene(profile, both)


@router.get("/partner/wake-schedule")
async def wake_schedule(request: Request):
    sw = _get_service(request, "staggered_wake")
    profile = _get_profile(request)
    return sw.compute_wake_schedule(profile)


# ===================================================================
# PHASE 9: Subscription & Engagement
# ===================================================================

@router.get("/subscription/trial/status")
async def trial_status(request: Request):
    ta = _get_service(request, "trial_automation")
    profile = _get_profile(request)
    return ta.get_trial_status(profile)


@router.post("/subscription/trial/start")
async def start_trial(request: Request):
    ta = _get_service(request, "trial_automation")
    profile = _get_profile(request)
    return ta.start_trial(profile)


@router.get("/subscription/churn-risk")
async def churn_risk(request: Request):
    rc = _get_service(request, "reengagement_campaigns")
    profile = _get_profile(request)
    return rc.detect_churn_risk(profile)


@router.get("/achievements")
async def achievements_list(request: Request):
    ae = _get_service(request, "achievement_engine")
    profile = _get_profile(request)
    return ae.get_all_progress(profile)


@router.get("/achievements/stats")
async def achievements_stats(request: Request):
    ae = _get_service(request, "achievement_engine")
    profile = _get_profile(request)
    return ae.get_stats(profile)


@router.post("/achievements/evaluate")
async def evaluate_achievements(request: Request):
    ae = _get_service(request, "achievement_engine")
    profile = _get_profile(request)
    return ae.evaluate_all(profile)


# ===================================================================
# PHASE 10: Advanced Features
# ===================================================================

@router.get("/personality/stage")
async def personality_stage(request: Request):
    pe = _get_service(request, "personality_evolution")
    profile = _get_profile(request)
    return pe.get_current_stage(profile)


@router.get("/personality/greeting")
async def personality_greeting(request: Request):
    pe = _get_service(request, "personality_evolution")
    profile = _get_profile(request)
    return {"greeting": pe.get_greeting(profile)}


@router.get("/personality/tone")
async def personality_tone(request: Request):
    pe = _get_service(request, "personality_evolution")
    profile = _get_profile(request)
    return pe.get_tone_instructions(profile)


@router.get("/personality/stats")
async def personality_stats(request: Request):
    pe = _get_service(request, "personality_evolution")
    profile = _get_profile(request)
    return pe.get_relationship_stats(profile)


@router.post("/dreams/record")
async def record_dream(request: Request, body: DreamEntry):
    dj = _get_service(request, "dream_journal")
    profile = _get_profile(request)
    return dj.record_dream(profile, body.text, vivid=body.vivid, lucid=body.lucid)


@router.get("/dreams/prompt")
async def dream_prompt(request: Request):
    dj = _get_service(request, "dream_journal")
    profile = _get_profile(request)
    return dj.get_morning_prompt(profile)


@router.get("/dreams/patterns")
async def dream_patterns(request: Request, days: int = 30):
    dj = _get_service(request, "dream_journal")
    profile = _get_profile(request)
    return dj.get_patterns(profile, days)


@router.get("/dreams/sleep-correlation")
async def dream_sleep_correlation(request: Request, days: int = 30):
    dj = _get_service(request, "dream_journal")
    profile = _get_profile(request)
    return dj.correlate_with_sleep(profile, days)


@router.post("/fitness/connect")
async def connect_fitness(request: Request, device_type: str):
    ft = _get_service(request, "fitness_tracker")
    profile = _get_profile(request)
    return ft.connect_device(profile, device_type)


@router.post("/fitness/disconnect")
async def disconnect_fitness(request: Request):
    ft = _get_service(request, "fitness_tracker")
    profile = _get_profile(request)
    return ft.disconnect_device(profile)


@router.post("/fitness/data")
async def ingest_biometric(request: Request, body: BiometricData):
    ft = _get_service(request, "fitness_tracker")
    profile = _get_profile(request)
    return ft.ingest_biometric_data(profile, body.model_dump())


@router.get("/fitness/enhancement")
async def fitness_enhancement(request: Request):
    ft = _get_service(request, "fitness_tracker")
    profile = _get_profile(request)
    return ft.get_sleep_enhancement(profile)


@router.get("/fitness/status")
async def fitness_status(request: Request):
    ft = _get_service(request, "fitness_tracker")
    profile = _get_profile(request)
    return ft.get_status(profile)


@router.get("/fitness/devices")
async def list_fitness_devices(request: Request):
    ft = _get_service(request, "fitness_tracker")
    return ft.get_supported_devices()
