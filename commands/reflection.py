from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Callable

REFLECTION_STEP_ASKED = "ASKED"

_TRIGGER_PHRASES = (
    "daily reflection",
    "daily summary",
    "end of day",
    "end of the day",
    "how was my day",
)

_NEGATIVE_PHRASES = (
    "wasted time",
    "bad day",
)

_NEGATIVE_TOKENS = {
    "no",
    "waste",
    "wasted",
    "bad",
    "failed",
    "fail",
    "nothing",
}

_POSITIVE_PHRASES = ("did well",)

_POSITIVE_TOKENS = {
    "yes",
    "good",
    "well",
    "better",
    "alhamdulillah",
}

_START_MESSAGE = (
    "Alhamdulillah for today. Quick reflection: what went well, what needs work, and one plan for tomorrow? "
    "Then leave the rest to tawakkul and get some rest."
)

_NEGATIVE_MESSAGE = (
    "I hear you. Be kind to yourself, but be firm: pick one small task for tomorrow (20 focused minutes is enough). "
    "Allahumma yassir wa la tu'assir."
)

_POSITIVE_MESSAGE = (
    "Alhamdulillah, that is good progress. Keep gratitude, and repeat tomorrow's plan with one clear priority. "
    "Rest with tawakkul."
)


def _normalize_text(value: str) -> str:
    lowered = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9\s']+", " ", lowered)
    return " ".join(cleaned.split())


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    if not normalized_text:
        return False
    return f" {phrase} " in f" {normalized_text} "


def _active_reflection_state() -> dict:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "active": True,
        "step": REFLECTION_STEP_ASKED,
        "started_at_utc": timestamp,
    }


def _cleared_reflection_state(previous_state: dict | None = None) -> dict:
    state = {
        "active": False,
        "step": "",
        "started_at_utc": "",
    }
    if isinstance(previous_state, dict) and previous_state.get("context"):
        state["context"] = previous_state.get("context")
    return state


def _normalize_reflection_state(raw_state: dict | None) -> dict:
    if not isinstance(raw_state, dict):
        return _cleared_reflection_state()

    active = bool(raw_state.get("active", False))
    step = str(raw_state.get("step", "") or "").strip().upper() if active else ""
    if step != REFLECTION_STEP_ASKED:
        step = ""
    started_at_utc = str(raw_state.get("started_at_utc", "") or "").strip() if active else ""

    state = {
        "active": active,
        "step": step,
        "started_at_utc": started_at_utc,
    }
    context = raw_state.get("context")
    if context is not None:
        state["context"] = context
    return state


def detect_reflection_intent(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(_contains_phrase(normalized, phrase) for phrase in _TRIGGER_PHRASES)


def _is_negative_reply(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False

    if any(_contains_phrase(normalized, phrase) for phrase in _NEGATIVE_PHRASES):
        return True

    tokens = set(normalized.split())
    return bool(tokens.intersection(_NEGATIVE_TOKENS))


def _is_positive_reply(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False

    if any(_contains_phrase(normalized, phrase) for phrase in _POSITIVE_PHRASES):
        return True

    tokens = set(normalized.split())
    return bool(tokens.intersection(_POSITIVE_TOKENS))


def _is_reflection_timed_out(
    state: dict,
    timeout_hours: int,
    now_provider: Callable[[], datetime],
) -> bool:
    if not bool(state.get("active", False)):
        return False

    started_at = str(state.get("started_at_utc", "") or "").strip()
    if not started_at:
        return False

    normalized_started_at = started_at.replace("Z", "+00:00")
    try:
        started_dt = datetime.fromisoformat(normalized_started_at)
    except ValueError:
        return True

    now = now_provider()
    if started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return (now - started_dt) > timedelta(hours=max(1, int(timeout_hours)))


def process_reflection_turn(
    user_text: str,
    profile: dict,
    timeout_hours: int = 12,
    now_provider: Callable[[], datetime] | None = None,
) -> tuple[str, bool, bool]:
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    existing_state = profile.get("reflection", {}) if isinstance(profile, dict) else {}
    state = _normalize_reflection_state(existing_state)
    state_changed = state != existing_state

    if _is_reflection_timed_out(state, timeout_hours=timeout_hours, now_provider=now_provider):
        profile["reflection"] = _cleared_reflection_state(state)
        return "", False, True

    if (
        bool(state.get("active", False))
        and str(state.get("step", "")).upper() == REFLECTION_STEP_ASKED
    ):
        response = _NEGATIVE_MESSAGE if _is_negative_reply(user_text) else _POSITIVE_MESSAGE
        profile["reflection"] = _cleared_reflection_state(state)
        return response, True, True

    if detect_reflection_intent(user_text):
        profile["reflection"] = _active_reflection_state()
        return _START_MESSAGE, True, True

    if state_changed:
        profile["reflection"] = state
    return "", False, state_changed
