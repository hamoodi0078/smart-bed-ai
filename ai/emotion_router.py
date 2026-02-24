from typing import Dict


EMOTION_KEYWORDS = {
    "distressed": (
        "overwhelmed",
        "anxious",
        "panic",
        "stressed",
        "i can't handle",
        "i am not okay",
        "burned out",
    ),
    "low_energy": (
        "tired",
        "exhausted",
        "no energy",
        "sleepy",
        "drained",
        "fatigue",
    ),
    "motivated": (
        "let's do this",
        "motivated",
        "ready",
        "excited",
        "i can do it",
    ),
    "dream_positive": (
        "beautiful dream",
        "peaceful dream",
        "happy dream",
        "wonderful",
    ),
    "dream_negative": (
        "nightmare",
        "scary dream",
        "bad dream",
        "terrifying",
    ),
}


def detect_emotion_state(user_text: str) -> str:
    lower = (user_text or "").lower()
    for state, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return state
    return "neutral"


def emotion_response_hint(emotion_state: str) -> str:
    hints: Dict[str, str] = {
        "distressed": "User appears distressed. Use calm pacing, validate first, then one small step.",
        "low_energy": "User appears low-energy. Keep response short and reduce cognitive load.",
        "motivated": "User appears motivated. Keep momentum with concrete next action and commitment.",
        "dream_positive": "Dream tone is positive. Reflect warmly and keep response gentle.",
        "dream_negative": "Dream tone is negative. Prioritize reassurance and emotional safety.",
        "neutral": "Use standard professional style.",
    }
    return hints.get(emotion_state, hints["neutral"])


def detect_dream_emotion(dream_text: str) -> str:
    lower = (dream_text or "").lower()
    if any(k in lower for k in ("nightmare", "terrifying", "scary", "panic")):
        return "dream_negative"
    if any(k in lower for k in ("beautiful", "peaceful", "happy", "calm", "joy")):
        return "dream_positive"

    base = detect_emotion_state(dream_text)
    if base in ("distressed", "low_energy"):
        return "dream_negative"
    if base == "motivated":
        return "dream_positive"
    return "neutral"


def emotion_tts_profile(emotion_state: str) -> dict:
    """Map emotional state to voice prosody controls for calming/energizing mirroring."""
    state = str(emotion_state or "neutral").strip().lower()
    profiles: Dict[str, dict] = {
        "distressed": {
            "profile_override": "whisper",
            "pace_multiplier": 0.88,
            "stability": "steady",
            "pitch_style": "lower",
        },
        "anxious": {
            "profile_override": "whisper",
            "pace_multiplier": 0.9,
            "stability": "steady",
            "pitch_style": "lower",
        },
        "sad": {
            "profile_override": "soft",
            "pace_multiplier": 0.92,
            "stability": "gentle",
            "pitch_style": "lower",
        },
        "low_energy": {
            "profile_override": "soft",
            "pace_multiplier": 0.94,
            "stability": "gentle",
            "pitch_style": "warm",
        },
        "motivated": {
            "profile_override": "default",
            "pace_multiplier": 1.04,
            "stability": "confident",
            "pitch_style": "brighter",
        },
        "excited": {
            "profile_override": "default",
            "pace_multiplier": 1.06,
            "stability": "expressive",
            "pitch_style": "brighter",
        },
        "dream_negative": {
            "profile_override": "whisper",
            "pace_multiplier": 0.9,
            "stability": "steady",
            "pitch_style": "lower",
        },
        "dream_positive": {
            "profile_override": "default",
            "pace_multiplier": 1.02,
            "stability": "warm",
            "pitch_style": "warm",
        },
        "neutral": {
            "profile_override": "default",
            "pace_multiplier": 1.0,
            "stability": "balanced",
            "pitch_style": "neutral",
        },
    }
    return dict(profiles.get(state, profiles["neutral"]))
