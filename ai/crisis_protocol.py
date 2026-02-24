from typing import Tuple


FAST_PROTOCOL_TRIGGERS = (
    "panic",
    "spiraling",
    "can't breathe",
    "cant breathe",
    "meltdown",
    "freaking out",
    "losing control",
)


def should_run_fast_protocol(user_text: str, safety_level: str = "none") -> bool:
    text = (user_text or "").lower()
    if safety_level in ("high", "moderate"):
        return True
    return any(k in text for k in FAST_PROTOCOL_TRIGGERS)


def build_fast_protocol_message() -> str:
    return (
        "Fast support mode: we will do this together in 90 seconds. "
        "Step 1: put both feet on the floor and name one object you can see. "
        "Step 2: inhale for 4 seconds, exhale for 6 seconds, repeat 5 times. "
        "Step 3: say one safe next action: drink water, sit down, or text a trusted person now."
    )


def command_match(text: str) -> bool:
    lower = (text or "").lower().strip()
    return lower in ("start crisis protocol", "panic mode", "fast support mode")
