import re
from collections.abc import Callable
from datetime import datetime

from core.types import CommandResult, Effect


def handle_reminder_intent_result(
    text: str,
    reminders_summary: str,
    now_provider: Callable[[], datetime] = datetime.now,
) -> CommandResult:
    """Build a pure reminder command result with declarative effects.

    The command logic does not mutate runtime state directly. Instead, it
    emits store/say effects for the runtime dispatcher to apply.
    """
    raw_text = str(text or "").strip()
    lowered = raw_text.lower()
    if lowered in ("show my reminders", "list reminders"):
        return CommandResult(
            text=reminders_summary,
            effects=(Effect(kind="say", payload={"text": reminders_summary}),),
            followup_state={"intent": "list_reminders"},
        )

    task_text = ""
    time_text = ""
    pattern = ""
    repeat_flag = ("every night" in lowered) or bool(re.search(r"\bevery\b", lowered))

    if "remind me to" in lowered:
        pattern = "remind"
        marker = "remind me to"
        start = lowered.find(marker) + len(marker)
        tail_raw = raw_text[start:].strip()
        tail_lower = lowered[start:].strip()
        at_index = tail_lower.rfind(" at ")
        if at_index >= 0:
            task_text = tail_raw[:at_index].strip(" .,!?")
            time_text = tail_raw[at_index + 4 :].strip(" .,!?")
        else:
            task_text = tail_raw.strip(" .,!?")
    elif "remind me" in lowered:
        pattern = "remind"
        marker = "remind me"
        start = lowered.find(marker) + len(marker)
        tail_raw = raw_text[start:].strip()
        tail_lower = lowered[start:].strip()
        if tail_lower.startswith("to "):
            tail_raw = tail_raw[3:].strip()
            tail_lower = tail_lower[3:].strip()
        at_index = tail_lower.rfind(" at ")
        if at_index >= 0:
            task_text = tail_raw[:at_index].strip(" .,!?")
            time_text = tail_raw[at_index + 4 :].strip(" .,!?")
        else:
            task_text = tail_raw.strip(" .,!?")
    elif "wake me up" in lowered:
        pattern = "wake"
        task_text = "wake up"
        marker = "wake me up"
        start = lowered.find(marker) + len(marker)
        tail_raw = raw_text[start:].strip()
        tail_lower = lowered[start:].strip()
        if tail_lower.startswith("at "):
            time_text = tail_raw[3:].strip(" .,!?")
        elif " at " in tail_lower:
            at_index = tail_lower.rfind(" at ")
            time_text = tail_raw[at_index + 4 :].strip(" .,!?")
        elif tail_raw:
            time_text = tail_raw.strip(" .,!?")

    if task_text or time_text:
        reminder = {
            "raw_text": raw_text,
            "pattern": pattern or "reminder",
            "task": task_text,
            "time": time_text,
            "created_at": now_provider(),
            "completed": False,
            "repeat": repeat_flag,
            "nudge_sent": False,
        }
        effects: list[Effect] = [
            Effect(kind="store", payload={"op": "append_planned_reminder", "reminder": reminder}),
        ]

        if time_text:
            effects.append(
                Effect(
                    kind="store",
                    payload={
                        "op": "set_reminder_nudge_state",
                        "state": {
                            "active": True,
                            "task": task_text,
                            "nudge_sent": False,
                            "nudge_time": now_provider(),
                        },
                    },
                )
            )

        if task_text and time_text:
            task_for_reply = re.sub(r"\bmy project\b", "your project", task_text, flags=re.IGNORECASE)
            lowered_time = time_text.lower()
            time_context = ""
            if ("pm" in lowered_time) and ("tonight" not in lowered_time):
                time_context = " tonight"
            elif ("am" in lowered_time) and ("tomorrow" not in lowered_time):
                time_context = " tomorrow"
            reply = f"Okay, I will remind you to {task_for_reply}{time_context} at {time_text}."
        elif task_text:
            reply = (
                f"Okay, I will remember you want to {task_text}. "
                "In the future, I will also use a time if you say one."
            )
        else:
            reply = (
                f"Okay, I will note your reminder time as {time_text}. "
                "Actual reminder scheduling will be implemented later."
            )

        effects.append(Effect(kind="say", payload={"text": reply}))
        return CommandResult(
            text=reply,
            effects=tuple(effects),
            followup_state={
                "intent": "set_reminder",
                "task": task_text,
                "time": time_text,
                "pattern": pattern or "reminder",
            },
        )

    fallback = "I did not catch the time or task. Please say: remind me to <task> at <time>."
    return CommandResult(
        text=fallback,
        effects=(Effect(kind="say", payload={"text": fallback}),),
        followup_state={"intent": "reminder_parse_failed"},
    )


def handle_reminder_intent(
    text: str,
    planned_reminders: list[dict[str, object]],
    reminder_nudge_state: dict[str, object],
    format_planned_reminders: Callable[[], str],
    now_provider: Callable[[], datetime] = datetime.now,
    log: Callable[[str], None] = print,
) -> str:
    """Handle reminder commands and mutate reminder state in-place.

    Contract: appends a reminder when task/time can be parsed and updates
    reminder_nudge_state when a reminder time is present.
    """
    result = handle_reminder_intent_result(
        text,
        reminders_summary=format_planned_reminders(),
        now_provider=now_provider,
    )

    for effect in result.effects:
        if effect.kind != "store":
            continue
        op = str(effect.payload.get("op", "") or "").strip().lower()
        if op == "append_planned_reminder":
            reminder = effect.payload.get("reminder", {})
            if isinstance(reminder, dict):
                planned_reminders.append(reminder)
        elif op == "set_reminder_nudge_state":
            state = effect.payload.get("state", {})
            if isinstance(state, dict):
                reminder_nudge_state.update(state)

    return result.text
