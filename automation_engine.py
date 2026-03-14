"""Automation runtime utilities for triggers, reminders, scheduler formatting, and cooldown handling."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from automations.defaults import build_default_automations
from automations.registry import AutomationRegistry
from config import RUNTIME_DATA_DIR, settings
from core.structured_logging import emit_json_log
from Storage.user_profile import load_profile, save_profile
from time_utils import utcnow

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

logger = logging.getLogger(__name__)
planned_reminders: list[dict[str, object]] = []
reminder_nudge_state = {
    "active": False,
    "task": "",
    "nudge_sent": False,
    "nudge_time": None,
}

sleep_mode_active = False
AUTOMATION_STATE_PATH = RUNTIME_DATA_DIR / "automations_state.json"
automation_registry = AutomationRegistry(state_path=AUTOMATION_STATE_PATH)
automation_reply_handler = None
automation_runtime_hooks: dict[str, object] = {}
automation_profile_ref: dict | None = None

def _parse_datetime_like(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None
    return None

def _has_pending_work_planning_reminder_today(now: datetime) -> bool:
    today = now.date()
    for item in planned_reminders:
        if bool(item.get("completed", False)):
            continue
        task = str(item.get("task", "") or "").strip().lower()
        if not task:
            continue
        if ("work" not in task) and ("plan" not in task) and ("planning" not in task):
            continue
        created_at = _parse_datetime_like(item.get("created_at"))
        if created_at is None:
            continue
        if created_at.date() == today:
            return True
    return False

def init_automations():
    if automation_registry.list():
        return
    for automation in build_default_automations():
        automation_registry.register(automation)

def run_automations():
    global sleep_mode_active
    profile = automation_profile_ref if isinstance(automation_profile_ref, dict) else {}
    disk_profile = load_profile()
    if isinstance(disk_profile, dict):
        disk_prefs = disk_profile.get("preferences", {}) if isinstance(disk_profile.get("preferences", {}), dict) else {}
        profile_prefs = profile.setdefault("preferences", {})
        for key in ("quiet_window", "quiet_mode_active", "quiet_hours_override_until_utc", "timezone"):
            if key in disk_prefs:
                profile_prefs[key] = disk_prefs.get(key)
    prefs = profile.get("preferences", {}) if isinstance(profile, dict) else {}
    timezone_name = str(prefs.get("timezone", "UTC") or "UTC").strip() or "UTC"
    now_utc = utcnow()

    try:
        now_local = now_utc.astimezone(ZoneInfo(timezone_name))
    except Exception:
        timezone_name = "UTC"
        now_local = now_utc

    ctx = {
        "now_utc": now_utc,
        "trace_id": "automation_runtime",
        "timezone": timezone_name,
        "sleep_mode_active": bool(sleep_mode_active),
        "quiet_window": str(
            prefs.get("quiet_window", settings.quiet_hours_default_window) or settings.quiet_hours_default_window
        ),
        "quiet_mode_active": bool(prefs.get("quiet_mode_active", False)),
        "quiet_hours_override_until_utc": str(prefs.get("quiet_hours_override_until_utc", "") or ""),
        "has_pending_work_planning_reminder_today": _has_pending_work_planning_reminder_today(now_local),
        "fajr_light_time": str(prefs.get("fajr_light_time", "04:50") or "04:50"),
    }

    for effect in automation_registry.run_automations(ctx):
        kind = str(effect.kind or "").strip().lower()
        payload = effect.payload if isinstance(effect.payload, dict) else {}

        if kind == "say":
            reply = str(payload.get("text", "") or "").strip()
            if not reply:
                continue
            emit_json_log(
                logger,
                level="info",
                event_type="automation_triggered",
                trace_id="automation_runtime",
                metadata={
                    "automation_effect_kind": "say",
                    "reply_chars": len(reply),
                },
            )
            try:
                if callable(automation_reply_handler):
                    automation_reply_handler(reply)
            except Exception as exc:
                emit_json_log(
                    logger,
                    level="error",
                    event_type="automation_reply_handler_failed",
                    trace_id="automation_runtime",
                    metadata={
                        "error_type": type(exc).__name__,
                    },
                )
            continue

        if kind == "led":
            op = str(payload.get("op", "") or "").strip().lower()
            hook = automation_runtime_hooks.get(op)
            if callable(hook):
                hook()
            continue

        if kind != "store":
            continue

        op = str(payload.get("op", "") or "").strip().lower()
        if op == "set_sleep_mode":
            sleep_mode_active = bool(payload.get("value", sleep_mode_active))
            if isinstance(profile, dict):
                profile.setdefault("runtime_flags", {})["sleep_mode"] = sleep_mode_active
                save_profile(profile)

def format_planned_reminders() -> str:
    if not planned_reminders:
        return "You have no reminders yet."

    lines: list[str] = []
    for idx, item in enumerate(planned_reminders, start=1):
        task = str(item.get("task", "") or "").strip()
        reminder_time = str(item.get("time", "") or "").strip()
        if task and reminder_time:
            lines.append(f"{idx}) {task} at {reminder_time}")
        elif task:
            lines.append(f"{idx}) {task}")
        elif reminder_time:
            lines.append(f"{idx}) at {reminder_time}")
        else:
            lines.append(f"{idx}) reminder")
    return f"You have {len(planned_reminders)} reminders:\n" + "\n".join(lines)

def mark_reminder_completed(task_keyword: str) -> bool:
    keyword = str(task_keyword or "").strip().lower()
    if not keyword:
        return False

    found = False
    for item in planned_reminders:
        task = str(item.get("task", "") or "").strip()
        if keyword in task.lower() and not bool(item.get("completed", False)):
            item["completed"] = True
            item["nudge_sent"] = True
            found = True
            print(f"[REMINDER] Marked completed: task='{task}'.")
    if found:
        reminder_nudge_state["active"] = False
        reminder_nudge_state["task"] = ""
        reminder_nudge_state["nudge_sent"] = False
        reminder_nudge_state["nudge_time"] = None
    return found

def check_reminder_nudge() -> str | None:
    if not bool(reminder_nudge_state.get("active", False)):
        return None
    if bool(reminder_nudge_state.get("nudge_sent", False)):
        return None

    task_text = str(reminder_nudge_state.get("task", "") or "").strip()
    raw_nudge_time = reminder_nudge_state.get("nudge_time")
    if raw_nudge_time is None:
        return None

    try:
        if isinstance(raw_nudge_time, datetime):
            nudge_time = raw_nudge_time
        else:
            nudge_time = datetime.fromisoformat(str(raw_nudge_time))
    except Exception:
        return None

    try:
        if datetime.now() - nudge_time < timedelta(minutes=10):
            return None
    except Exception:
        return None

    reminder_nudge_state["nudge_sent"] = True
    for item in reversed(planned_reminders):
        if bool(item.get("completed", False)):
            continue
        task = str(item.get("task", "") or "").strip()
        if task and task_text and task.lower() == task_text.lower():
            item["nudge_sent"] = True
            break

    task_for_reply = task_text or "follow your planned reminder"
    return f"Just a gentle reminder: you planned to {task_for_reply} now. You can do it!"

def format_repeat_days(repeat_days_csv: str) -> str:
    if not repeat_days_csv:
        return "one-time"

    days = []
    for part in repeat_days_csv.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part)
            if 0 <= idx <= 6:
                days.append(WEEKDAY_NAMES[idx])
    if not days:
        return "one-time"
    return "every " + ",".join(days)

