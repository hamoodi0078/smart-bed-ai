"""
reflection.py: Daily Reflection Conversational Flow
"""

import datetime
from typing import Optional, Dict, Any
from core.types import CommandResult, Effect

REFLECTION_STEPS = ("ASKED", "FOLLOWUP")

class ReflectionState:
    def __init__(self, active: bool = False, step: Optional[str] = None, started_at_utc: Optional[str] = None):
        self.active = active
        self.step = step
        self.started_at_utc = started_at_utc

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(
            active=d.get("active", False),
            step=d.get("step"),
            started_at_utc=d.get("started_at_utc")
        )

    def to_dict(self):
        return {
            "active": self.active,
            "step": self.step,
            "started_at_utc": self.started_at_utc
        }

    def clear(self):
        self.active = False
        self.step = None
        self.started_at_utc = None

# Reflection intent keywords
REFLECTION_KEYWORDS = [
    "daily reflection", "daily summary", "how was my day", "end of the day"
]

def detect_reflection_intent(text: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in REFLECTION_KEYWORDS)

# Short reflection starter message
REFLECTION_START_MSG = (
    "Let's reflect on your day. What went well? Anything you're grateful for? Any challenge?"
    " Take a moment to check in with yourself."
)

# Positive/negative followup templates
POSITIVE_MSG = (
    "That's wonderful! Gratitude is powerful. Let's plan to repeat what worked. Wishing you restful sleep."
)
NEGATIVE_MSG = (
    "It's okay to have tough days. Pick one small thing to improve tomorrow. Remember, every step counts. May you find ease and blessing."
)

# State machine logic


def start_reflection_cmd(state: ReflectionState) -> CommandResult:
    state.active = True
    state.step = "ASKED"
    state.started_at_utc = datetime.datetime.utcnow().isoformat()
    return CommandResult(
        text=REFLECTION_START_MSG,
        effects=(
            Effect(kind="update_reflection_state", payload=state.to_dict()),
        ),
        followup_state={}
    )


def handle_reflection_reply_cmd(state: ReflectionState, user_reply: str) -> CommandResult:
    # Simple sentiment check (can be replaced with better NLP)
    negative_words = ["waste", "bad", "tired", "nothing", "fail", "miss", "sad", "angry"]
    is_negative = any(w in user_reply.lower() for w in negative_words)
    state.clear()
    msg = NEGATIVE_MSG if is_negative else POSITIVE_MSG
    return CommandResult(
        text=msg,
        effects=(
            Effect(kind="update_reflection_state", payload=state.to_dict()),
        ),
        followup_state={}
    )

# Timeout clearing

def check_reflection_timeout(state: ReflectionState, timeout_minutes: int = 10) -> bool:
    if not state.active or not state.started_at_utc:
        return False
    started = datetime.datetime.fromisoformat(state.started_at_utc)
    now = datetime.datetime.utcnow()
    delta = now - started
    if delta.total_seconds() > timeout_minutes * 60:
        state.clear()
        return True
    return False
