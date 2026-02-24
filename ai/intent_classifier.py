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


def detect_led_command(text: str):
    t = text.lower().strip()

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
    t = text.lower().strip()

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
