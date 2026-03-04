from __future__ import annotations

from datetime import datetime
from typing import Any

from automations.base import Automation
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


def _is_in_quiet_window(ctx: dict[str, Any]) -> bool:
    if bool(ctx.get("quiet_mode_active", False)):
        return True
    quiet_window = str(ctx.get("quiet_window", "") or "").strip()
    if not quiet_window or "-" not in quiet_window:
        return False
    now_local = ctx.get("now_local")
    if not isinstance(now_local, datetime):
        return False
    try:
        left, right = [part.strip() for part in quiet_window.split("-", 1)]
        sh, sm = _parse_hhmm(left, (0, 0))
        eh, em = _parse_hhmm(right, (0, 0))
        return _in_window(now_local, sh, sm, eh, em)
    except Exception:
        return False


def build_default_automations() -> list[Automation]:
    def sleep_trigger(ctx: dict[str, Any]) -> bool:
        now_local = ctx.get("now_local")
        if not isinstance(now_local, datetime):
            return False
        if _is_in_quiet_window(ctx):
            return False
        return _in_window(now_local, 23, 0, 6, 0) and (not bool(ctx.get("sleep_mode_active", False)))

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
        if _is_in_quiet_window(ctx):
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
        if _is_in_quiet_window(ctx):
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
        if _is_in_quiet_window(ctx):
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

    return [
        Automation(
            name="sleep_time_suggestion",
            trigger=sleep_trigger,
            action=sleep_action,
            cooldown_minutes=120,
            window_key=sleep_window_key,
        ),
        Automation(
            name="work_and_plan_10pm",
            trigger=work_plan_trigger,
            action=work_plan_action,
            cooldown_minutes=1440,
            window_key=work_plan_window_key,
        ),
        Automation(
            name="morning_wake_scene",
            trigger=morning_wake_trigger,
            action=morning_wake_action,
            cooldown_minutes=120,
            window_key=morning_wake_window_key,
        ),
        Automation(
            name="fajr_gentle_light",
            trigger=fajr_trigger,
            action=fajr_action,
            cooldown_minutes=1440,
            window_key=fajr_window_key,
        ),
    ]
