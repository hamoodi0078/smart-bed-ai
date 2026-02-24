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
