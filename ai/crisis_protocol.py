"""Crisis / fast-support protocol for Dana AI.

When a user shows signs of acute distress Dana switches to a structured
grounding exercise that can be delivered in ~90 seconds.  The protocol is
designed around evidence-based grounding techniques (5-4-3-2-1 sensory,
box-breathing, and safe-action commitment).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from loguru import logger


FAST_PROTOCOL_TRIGGERS: tuple[str, ...] = (
    "panic",
    "spiraling",
    "can't breathe",
    "cant breathe",
    "meltdown",
    "freaking out",
    "losing control",
    "anxiety attack",
    "heart racing",
    "i'm scared",
    "im scared",
    "help me now",
    "emergency",
)

ARABIC_TRIGGERS: tuple[str, ...] = (
    "ما أقدر أتنفس",
    "خايف",
    "ساعدني",
    "أزمة",
    "هلع",
)

COMMAND_PHRASES: frozenset[str] = frozenset({
    "start crisis protocol",
    "panic mode",
    "fast support mode",
    "crisis mode",
    "grounding exercise",
})


@dataclass
class CrisisEvent:
    """Record of a crisis protocol activation (for analytics / follow-up)."""
    user_id: str = ""
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trigger_phrase: str = ""
    safety_level: str = "none"
    protocol_completed: bool = False


def should_run_fast_protocol(user_text: str, safety_level: str = "none") -> bool:
    """Return True if Dana should immediately enter crisis-support mode."""
    text = (user_text or "").lower()
    if safety_level in ("high", "moderate"):
        return True
    if any(k in text for k in FAST_PROTOCOL_TRIGGERS):
        return True
    if any(k in (user_text or "") for k in ARABIC_TRIGGERS):
        return True
    return False


def detect_trigger_phrase(user_text: str) -> str | None:
    """Return the first matching trigger phrase, or None."""
    text = (user_text or "").lower()
    for phrase in FAST_PROTOCOL_TRIGGERS:
        if phrase in text:
            return phrase
    for phrase in ARABIC_TRIGGERS:
        if phrase in (user_text or ""):
            return phrase
    return None


def build_fast_protocol_message(locale: str = "en") -> str:
    """Return the structured grounding script in the requested locale."""
    if locale.startswith("ar"):
        return (
            "وضع الدعم السريع: سنفعل هذا معاً في ٩٠ ثانية. "
            "الخطوة ١: ضع قدميك على الأرض وسمّ شيئاً واحداً تراه. "
            "الخطوة ٢: استنشق لمدة ٤ ثوانٍ، ازفر لمدة ٦ ثوانٍ، كرر ٥ مرات. "
            "الخطوة ٣: قل إجراءً آمناً واحداً: اشرب ماء، اجلس، أو أرسل رسالة لشخص تثق به."
        )
    return (
        "Fast support mode: we will do this together in 90 seconds. "
        "Step 1: put both feet on the floor and name one object you can see. "
        "Step 2: inhale for 4 seconds, exhale for 6 seconds, repeat 5 times. "
        "Step 3: say one safe next action: drink water, sit down, or text a trusted person now."
    )


def build_followup_message(locale: str = "en") -> str:
    """A gentler follow-up message sent after the grounding exercise."""
    if locale.startswith("ar"):
        return "كيف تشعر الآن؟ لا داعي للعجلة. أنا هنا معك."
    return "How are you feeling now? No rush. I'm right here with you."


def command_match(text: str) -> bool:
    """Return True if *text* is an explicit crisis-command phrase."""
    lower = (text or "").lower().strip()
    return lower in COMMAND_PHRASES


def log_crisis_event(event: CrisisEvent) -> None:
    """Persist a crisis activation event for follow-up and analytics."""
    logger.warning(
        "Crisis protocol activated: user={} trigger='{}' safety={}",
        event.user_id or "unknown",
        event.trigger_phrase,
        event.safety_level,
    )
