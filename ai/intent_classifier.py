import re


PERSONALITIES = ("therapist", "coach", "guide")
COMMON_COLORS = (
    "red",
    "green",
    "blue",
    "yellow",
    "purple",
    "white",
    "cyan",
    "orange",
    "pink",
)

_IMPLICIT_INTENT_PATTERNS = (
    {
        "intent": "set_scene",
        "confidence": 0.86,
        "patterns": (
            r"\bit'?s getting (a bit )?bright\b",
            r"\btoo bright\b",
            r"\bmy eyes (are )?tired from the light\b",
            r"\blights? (are )?harsh\b",
        ),
        "slots": {
            "scene_key": "calm_recovery",
            "brightness": 0.2,
            "color": "warmwhite",
            "animation": "breathing",
            "proactive_offer": "evening_routine",
        },
        "partner_line": "I'll dim the lights for you. Shall we start your evening routine?",
    },
    {
        "intent": "set_scene",
        "confidence": 0.82,
        "patterns": (
            r"\bcan'?t settle down\b",
            r"\bneed to unwind\b",
            r"\bmy mind is racing\b",
        ),
        "slots": {
            "scene_key": "calm_recovery",
            "brightness": 0.2,
            "color": "warmwhite",
            "animation": "breathing",
            "proactive_offer": "wind_down",
        },
        "partner_line": "Let's soften the room first. Want me to start a short wind-down too?",
    },
    {
        "intent": "play_music",
        "confidence": 0.8,
        "patterns": (
            r"\bit'?s too quiet in here\b",
            r"\bthis room feels silent\b",
            r"\bi need something in the background\b",
        ),
        "slots": {"query": "ambient"},
        "partner_line": "I'll start soft background audio. Want calm ambient or rain sounds?",
    },
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def detect_implicit_intent(text: str) -> dict:
    """Infer likely control intent from conversational phrasing.

    Returns a resolver-like payload with optional partner follow-up line.
    """
    normalized = _normalize(text)
    if not normalized:
        return {}

    for item in _IMPLICIT_INTENT_PATTERNS:
        for pattern in item.get("patterns", ()):
            if re.search(pattern, normalized):
                return {
                    "intent": item.get("intent", ""),
                    "slots": dict(item.get("slots", {})),
                    "confidence": float(item.get("confidence", 0.0)),
                    "partner_line": str(item.get("partner_line", "")).strip(),
                    "source": "implicit_intent",
                }

    return {}


def detect_led_command(text: str):
    t = _normalize(text)

    if "brighter" in t:
        return ("brightness_up", None)

    if "dimmer" in t or "darker" in t:
        return ("brightness_down", None)

    if "light" not in t and "lights" not in t and "color" not in t:
        return (None, None)

    hex_match = re.search(r"#([0-9a-fA-F]{6})", text)
    if hex_match:
        return ("set_color", f"#{hex_match.group(1)}")

    rgb_match = re.search(
        r"rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)",
        text,
        flags=re.IGNORECASE,
    )
    if rgb_match:
        return (
            "set_color",
            f"rgb({rgb_match.group(1)},{rgb_match.group(2)},{rgb_match.group(3)})",
        )

    for color in COMMON_COLORS:
        if color in t:
            return ("set_color", color)

    return (None, None)


def detect_personality_switch(text: str):
    t = _normalize(text)

    switch_verb = re.search(r"\b(switch|change|set|use|turn|go)\b", t)
    if not switch_verb:
        return None

    for personality in PERSONALITIES:
        direct_switch = re.search(
            rf"\b(switch|change|set|use|turn|go)\b[\w\s]*\b(to|into)?\s*\b{personality}\b(\s+(mode|personality))?\b",
            t,
        )
        if direct_switch:
            return personality

    return None
