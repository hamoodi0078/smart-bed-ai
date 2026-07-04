from __future__ import annotations

from datetime import datetime
from typing import Any

from automations.base import (
    AUTOMATION_CRITICALITY_CRITICAL,
    AUTOMATION_CRITICALITY_NON_CRITICAL,
    Automation,
)
from core.types import Effect


def _minutes(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _in_window(now_local: datetime, start_h: int, start_m: int, end_h: int, end_m: int) -> bool:
    current = _minutes(now_local)
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _parse_hhmm(value: str, default: tuple[int, int]) -> tuple[int, int]:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return default
    try:
        h_str, m_str = text.split(":", 1)
        h = max(0, min(23, int(h_str)))
        m = max(0, min(59, int(m_str)))
        return h, m
    except Exception:
        return default


def build_default_automations() -> list[Automation]:
    def sleep_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return _in_window(now_local, 23, 0, 6, 0) and (
            not bool(ctx.get("sleep_mode_active", False))
        )

    def sleep_action(ctx: dict[str, Any]) -> list[Effect]:
        text = (
            "Before sleep, be grateful for this day, review your work and plan for tomorrow, "
            "then sleep now to protect Fajr."
        )
        return [Effect(kind="say", payload={"text": text})]

    def sleep_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:sleep_suggestion"

    def work_plan_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        if not _in_window(now_local, 21, 50, 22, 10):
            return False
        return not bool(ctx.get("has_pending_work_planning_reminder_today", False))

    def work_plan_action(ctx: dict[str, Any]) -> list[Effect]:
        text = (
            "It is around 10 pm. This is your small daily habit: do your work and planning "
            "for tomorrow, then you can rest in peace in sha Allah."
        )
        return [Effect(kind="say", payload={"text": text})]

    def work_plan_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:work_plan_2200"

    def morning_wake_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return _in_window(now_local, 6, 0, 7, 0) and bool(ctx.get("sleep_mode_active", False))

    def morning_wake_action(ctx: dict[str, Any]) -> list[Effect]:
        text = "Bismillah. Start your day with discipline and shukr, and move with focus from the first hour."
        return [
            Effect(kind="led", payload={"op": "wake_up_scene"}),
            Effect(kind="store", payload={"op": "set_sleep_mode", "value": False}),
            Effect(kind="say", payload={"text": text}),
        ]

    def morning_wake_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:morning_wake"

    def fajr_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        if not bool(ctx.get("sleep_mode_active", False)):
            return False

        fajr_h, fajr_m = _parse_hhmm(str(ctx.get("fajr_light_time", "") or ""), (4, 50))
        start_mins = fajr_h * 60 + fajr_m - 10
        end_mins = fajr_h * 60 + fajr_m + 20
        start_h, start_min = divmod(start_mins % (24 * 60), 60)
        end_h, end_min = divmod(end_mins % (24 * 60), 60)
        return _in_window(now_local, start_h, start_min, end_h, end_min)

    def fajr_action(ctx: dict[str, Any]) -> list[Effect]:
        text = "Fajr time is near. Wake gently, make wudu, and ask Allah to guide your day."
        return [
            Effect(kind="led", payload={"op": "fajr_gentle_light_scene"}),
            Effect(kind="say", payload={"text": text}),
        ]

    def fajr_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:fajr_gentle"

    # --- NEW: Bedtime drift alert ---
    def bedtime_drift_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return _in_window(now_local, 23, 30, 1, 30) and (
            not bool(ctx.get("sleep_mode_active", False))
        )

    def bedtime_drift_action(ctx: dict[str, Any]) -> list[Effect]:
        text = "You're up later than usual. Ready for your wind-down routine?"
        return [Effect(kind="say", payload={"text": text})]

    def bedtime_drift_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:bedtime_drift"

    # --- NEW: Hydration pre-bed reminder ---
    def hydration_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return _in_window(now_local, 20, 0, 21, 0)

    def hydration_action(ctx: dict[str, Any]) -> list[Effect]:
        text = (
            "Last chance for water before bed. Stay hydrated but avoid drinking too close to sleep."
        )
        return [Effect(kind="say", payload={"text": text})]

    def hydration_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:hydration_prebed"

    # --- NEW: Circadian phase transition ---
    def circadian_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return _in_window(now_local, 19, 0, 21, 0) and bool(ctx.get("circadian_enabled", True))

    def circadian_action(ctx: dict[str, Any]) -> list[Effect]:
        return [Effect(kind="led", payload={"op": "circadian_evening_transition"})]

    def circadian_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:circadian_evening"

    # --- NEW: Stress check-in ---
    def stress_checkin_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return _in_window(now_local, 22, 0, 22, 30) and int(ctx.get("stress_score", 0)) >= 60

    def stress_checkin_action(ctx: dict[str, Any]) -> list[Effect]:
        text = "I notice some stress signals today. Would you like a quick breathing exercise before sleep?"
        return [
            Effect(kind="say", payload={"text": text}),
            Effect(kind="led", payload={"op": "calm_breathing_scene"}),
        ]

    def stress_checkin_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:stress_checkin"

    # --- NEW: Calendar evening brief ---
    def calendar_brief_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return _in_window(now_local, 22, 0, 22, 15) and bool(ctx.get("calendar_enabled", False))

    def calendar_brief_action(ctx: dict[str, Any]) -> list[Effect]:
        msg = str(ctx.get("calendar_tomorrow_message", "")) or "Check your calendar for tomorrow."
        return [Effect(kind="say", payload={"text": msg})]

    def calendar_brief_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:calendar_brief"

    # --- NEW: Nap suggestion (afternoon) ---
    def nap_suggest_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return (
            _in_window(now_local, 13, 0, 15, 0)
            and float(ctx.get("sleep_debt_hours", 0)) > 2.0
            and not bool(ctx.get("nap_already_today", False))
        )

    def nap_suggest_action(ctx: dict[str, Any]) -> list[Effect]:
        debt = float(ctx.get("sleep_debt_hours", 0))
        text = f"You have {debt:.1f}h sleep debt. A 20-minute power nap would help recovery."
        return [Effect(kind="say", payload={"text": text})]

    def nap_suggest_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:nap_suggest"

    # --- Weather: Hot Night Comfort ---
    def hot_night_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        temp = float(ctx.get("outdoor_temp_c", 0) or 0)
        return temp >= 32.0 and _in_window(now_local, 21, 0, 23, 59)

    def hot_night_action(ctx: dict[str, Any]) -> list[Effect]:
        temp = float(ctx.get("outdoor_temp_c", 32) or 32)
        return [
            Effect(kind="led", payload={"op": "cool_blue_scene"}),
            Effect(
                kind="say",
                payload={
                    "text": (
                        f"It's {temp:.0f}°C outside tonight. I've switched to cool blue lighting "
                        "to help you sleep comfortably."
                    )
                },
            ),
        ]

    def hot_night_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:hot_night"

    # --- Weather: Rainy Night Comfort ---
    def rainy_night_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        condition = str(ctx.get("weather_condition", "") or "").lower()
        return condition in {"rain", "drizzle", "thunderstorm"} and _in_window(
            now_local, 20, 0, 23, 59
        )

    def rainy_night_action(ctx: dict[str, Any]) -> list[Effect]:
        return [
            Effect(kind="led", payload={"op": "warm_cozy_scene"}),
            Effect(
                kind="say",
                payload={
                    "text": (
                        "It's raining tonight. I've activated warm cozy lighting "
                        "and cozy mode for the perfect sleep."
                    )
                },
            ),
        ]

    def rainy_night_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:rainy_night"

    # --- NEW: Weekly report auto-send (Sunday morning) ---
    def weekly_report_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        return now_local.weekday() == 6 and _in_window(now_local, 9, 0, 9, 30)

    def weekly_report_action(ctx: dict[str, Any]) -> list[Effect]:
        return [
            Effect(kind="report", payload={"op": "generate_weekly_health_report"}),
            Effect(
                kind="say", payload={"text": "Your weekly health report is ready. Check it out!"}
            ),
        ]

    def weekly_report_window_key(ctx: dict[str, Any]) -> str | None:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return None
        return f"{now_local.date().isoformat()}:weekly_report"

    return [
        Automation(
            name="sleep_time_suggestion",
            trigger=sleep_trigger,
            action=sleep_action,
            cooldown_minutes=120,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=sleep_window_key,
        ),
        Automation(
            name="work_and_plan_10pm",
            trigger=work_plan_trigger,
            action=work_plan_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=work_plan_window_key,
        ),
        Automation(
            name="morning_wake_scene",
            trigger=morning_wake_trigger,
            action=morning_wake_action,
            cooldown_minutes=120,
            criticality=AUTOMATION_CRITICALITY_CRITICAL,
            window_key=morning_wake_window_key,
        ),
        Automation(
            name="fajr_gentle_light",
            trigger=fajr_trigger,
            action=fajr_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_CRITICAL,
            window_key=fajr_window_key,
        ),
        Automation(
            name="bedtime_drift_alert",
            trigger=bedtime_drift_trigger,
            action=bedtime_drift_action,
            cooldown_minutes=120,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=bedtime_drift_window_key,
        ),
        Automation(
            name="hydration_prebed_reminder",
            trigger=hydration_trigger,
            action=hydration_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=hydration_window_key,
        ),
        Automation(
            name="circadian_evening_transition",
            trigger=circadian_trigger,
            action=circadian_action,
            cooldown_minutes=360,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=circadian_window_key,
        ),
        Automation(
            name="stress_evening_checkin",
            trigger=stress_checkin_trigger,
            action=stress_checkin_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=stress_checkin_window_key,
        ),
        Automation(
            name="calendar_evening_brief",
            trigger=calendar_brief_trigger,
            action=calendar_brief_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=calendar_brief_window_key,
        ),
        Automation(
            name="nap_suggestion",
            trigger=nap_suggest_trigger,
            action=nap_suggest_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=nap_suggest_window_key,
        ),
        Automation(
            name="weekly_health_report",
            trigger=weekly_report_trigger,
            action=weekly_report_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=weekly_report_window_key,
        ),
        Automation(
            name="hot_night_comfort",
            trigger=hot_night_trigger,
            action=hot_night_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=hot_night_window_key,
        ),
        Automation(
            name="rainy_night_comfort",
            trigger=rainy_night_trigger,
            action=rainy_night_action,
            cooldown_minutes=1440,
            criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
            window_key=rainy_night_window_key,
        ),
    ]
