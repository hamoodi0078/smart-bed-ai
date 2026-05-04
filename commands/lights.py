"""Light command handler for Danah Smart Bed.

Handles voice/text light intents and dispatches to:
  1. The bed's own LED strip (existing behavior — always runs)
  2. Real smart home devices via integrations.smart_home (Hue, Kasa, Miio, etc.)
     — only if the device controller is configured and reachable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from core.types import CommandResult, Effect

logger = logging.getLogger("commands.lights")

# Smart home controller — lazy import so missing env vars don't crash startup
_smart_home_attempted = False
_smart_home_ctrl = None


def _get_smart_home():
    global _smart_home_attempted, _smart_home_ctrl
    if _smart_home_attempted:
        return _smart_home_ctrl
    _smart_home_attempted = True
    try:
        from integrations.smart_home import get_controller
        _smart_home_ctrl = get_controller()
    except Exception as exc:
        logger.debug("Smart home controller unavailable: %s", exc)
        _smart_home_ctrl = None
    return _smart_home_ctrl


# ---------------------------------------------------------------------------
# Color / brightness vocabularies (extended)
# ---------------------------------------------------------------------------

COLOR_MAP = {
    "red": "red",
    "blue": "blue",
    "green": "green",
    "yellow": "yellow",
    "purple": "purple",
    "white": "white",
    "warm": "warmwhite",
    "cool": "cyan",
    "orange": "orange",
    "pink": "pink",
    "cyan": "cyan",
    "teal": "cyan",
    "violet": "purple",
    "indigo": "purple",
    "amber": "orange",
    "gold": "yellow",
    "coral": "pink",
}

BRIGHTNESS_MAP = {
    "dimmer": 0.20,
    "dim": 0.20,
    "low": 0.25,
    "brighter": 0.80,
    "bright": 0.80,
    "high": 0.90,
    "full": 1.00,
    "medium": 0.50,
    "half": 0.50,
    "off": 0.00,
    "on": 0.70,
}

OFF_WORDS = {"off", "turn off", "lights off", "switch off", "shut off", "kill the lights", "kill lights"}
ON_WORDS = {"on", "turn on", "lights on", "switch on"}
BEDTIME_WORDS = {"bedtime", "sleep", "night", "sleep mode", "bed mode"}
SUNRISE_WORDS = {"sunrise", "wake up", "morning", "alarm", "rise and shine"}


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

def _parse_intent(text: str) -> dict[str, Any]:
    raw = str(text or "").strip().lower()
    normalized = " " + "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in raw) + " "

    # Special modes
    if any(w in raw for w in BEDTIME_WORDS):
        return {"mode": "bedtime"}
    if any(w in raw for w in SUNRISE_WORDS):
        return {"mode": "sunrise"}
    if any(w in raw for w in OFF_WORDS):
        return {"mode": "off"}
    if any(w in raw for w in ON_WORDS) and not any(c in raw for c in COLOR_MAP):
        return {"mode": "on"}

    color_word = None
    for candidate, mapped in COLOR_MAP.items():
        if f" {candidate} " in normalized:
            color_word = mapped
            break

    brightness_word = None
    brightness_val = None
    for candidate, val in BRIGHTNESS_MAP.items():
        if f" {candidate} " in normalized:
            brightness_word = candidate
            brightness_val = val
            break

    return {
        "mode": "set",
        "color": color_word,
        "brightness": brightness_val,
        "brightness_word": brightness_word,
    }


# ---------------------------------------------------------------------------
# Smart home dispatcher
# ---------------------------------------------------------------------------

def _dispatch_to_smart_home(intent: dict[str, Any]) -> None:
    ctrl = _get_smart_home()
    if ctrl is None:
        return

    mode = intent.get("mode")
    try:
        if mode == "bedtime":
            ctrl.bedtime_mode(brightness=0.12)
        elif mode == "off":
            ctrl.lights_out()
        elif mode == "sunrise":
            ctrl.sunrise_alarm()
        elif mode in ("on", "set"):
            color = intent.get("color") or ""
            brightness = intent.get("brightness") or 0.75
            ctrl.set_lights(color=color, brightness=brightness, on=True)
    except Exception as exc:
        logger.warning("Smart home dispatch failed for mode=%s: %s", mode, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def handle_light_intent_result(text: str) -> CommandResult:
    """Build a pure light command result with declarative LED effects."""
    intent = _parse_intent(text)
    mode = intent.get("mode")

    # Dispatch to real smart home devices (non-blocking attempt)
    _dispatch_to_smart_home(intent)

    # --- Build LED effects and reply for the bed's own strip ---

    if mode == "bedtime":
        effects = (
            Effect(kind="led", payload={"op": "set_user_brightness", "brightness": 0.10}),
            Effect(kind="led", payload={"op": "set_user_color", "color": "orange"}),
            Effect(kind="say", payload={"text": "Switching to bedtime mode. Lights dimmed warm and low."}),
        )
        return CommandResult(
            text="Switching to bedtime mode. Lights dimmed warm and low.",
            effects=effects,
            followup_state={"intent": "lights", "mode": "bedtime"},
        )

    if mode == "sunrise":
        effects = (
            Effect(kind="led", payload={"op": "set_user_brightness", "brightness": 0.30}),
            Effect(kind="led", payload={"op": "set_user_color", "color": "warmwhite"}),
            Effect(kind="say", payload={"text": "Starting gentle sunrise lighting. Good morning!"}),
        )
        return CommandResult(
            text="Starting gentle sunrise lighting. Good morning!",
            effects=effects,
            followup_state={"intent": "lights", "mode": "sunrise"},
        )

    if mode == "off":
        effects = (
            Effect(kind="led", payload={"op": "set_user_brightness", "brightness": 0.0}),
            Effect(kind="say", payload={"text": "Lights off."}),
        )
        return CommandResult(
            text="Lights off.",
            effects=effects,
            followup_state={"intent": "lights", "mode": "off"},
        )

    if mode == "on":
        effects = (
            Effect(kind="led", payload={"op": "set_user_brightness", "brightness": 0.75}),
            Effect(kind="say", payload={"text": "Lights on."}),
        )
        return CommandResult(
            text="Lights on.",
            effects=effects,
            followup_state={"intent": "lights", "mode": "on"},
        )

    # mode == "set" — color and/or brightness
    color_word = intent.get("color")
    brightness_val = intent.get("brightness")
    brightness_word = intent.get("brightness_word")

    if color_word is None and brightness_val is None:
        reply = "What color or brightness would you like for the lights?"
        return CommandResult(
            text=reply,
            effects=(Effect(kind="say", payload={"text": reply}),),
            followup_state={"intent": "lights_clarify"},
        )

    effects: list[Effect] = []
    if color_word:
        effects.append(Effect(kind="led", payload={"op": "set_user_color", "color": color_word}))
    if brightness_val is not None:
        effects.append(Effect(kind="led", payload={"op": "set_user_brightness", "brightness": brightness_val}))

    if color_word and brightness_word:
        level = "dim" if brightness_val and brightness_val <= 0.3 else ("full brightness" if brightness_val and brightness_val >= 0.9 else "bright")
        reply = f"Setting the lights to {level} {color_word}."
    elif color_word:
        reply = f"Setting the lights to {color_word}."
    elif brightness_val == 0.0:
        reply = "Lights off."
    elif brightness_word in ("dimmer", "dim", "low"):
        reply = "Making the lights dimmer."
    elif brightness_word == "full":
        reply = "Setting the lights to full brightness."
    else:
        reply = "Making the lights brighter."

    effects.append(Effect(kind="say", payload={"text": reply}))
    return CommandResult(
        text=reply,
        effects=tuple(effects),
        followup_state={
            "intent": "lights",
            "color": color_word or "",
            "brightness": brightness_word or "",
        },
    )


def handle_light_intent(
    text: str,
    set_user_led_color: Callable[[str], None],
    set_user_brightness: Callable[[float], None],
    log: Callable[[str], None] = print,
) -> str:
    """Handle light commands and apply effects to the bed LED strip."""
    result = handle_light_intent_result(text)

    for effect in result.effects:
        if effect.kind != "led":
            continue
        op = str(effect.payload.get("op", "") or "").strip().lower()
        if op == "set_user_color":
            color = str(effect.payload.get("color", "") or "").strip().lower()
            if color:
                try:
                    set_user_led_color(color)
                except Exception as exc:
                    logger.warning("LED color set failed: %s", exc)
        elif op == "set_user_brightness":
            brightness = effect.payload.get("brightness")
            if isinstance(brightness, (int, float)):
                try:
                    set_user_brightness(float(brightness))
                except Exception as exc:
                    logger.warning("LED brightness set failed: %s", exc)

    followup = result.followup_state if isinstance(result.followup_state, dict) else {}
    log_color = str(followup.get("color", "") or "none")
    log_brightness = str(followup.get("brightness", "") or "none")
    log(f"[INTENT][LIGHT] color={log_color} brightness={log_brightness} from text='{text}'")
    return result.text