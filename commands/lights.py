from collections.abc import Callable

from core.types import CommandResult, Effect


def handle_light_intent_result(text: str) -> CommandResult:
    """Build a pure light command result with declarative LED effects."""
    raw_text = str(text or "").strip()
    lowered = raw_text.lower()
    normalized = " " + "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in lowered) + " "

    color_word = None
    for candidate in ("red", "blue", "green", "yellow", "purple", "white", "warm", "cool"):
        if f" {candidate} " in normalized:
            color_word = candidate
            break

    brightness_word = None
    for candidate in ("dimmer", "dim", "brighter", "bright", "full"):
        if f" {candidate} " in normalized:
            brightness_word = candidate
            break

    color_map = {
        "red": "red",
        "blue": "blue",
        "green": "green",
        "yellow": "yellow",
        "purple": "purple",
        "white": "white",
        "warm": "orange",
        "cool": "cyan",
    }
    brightness_map = {
        "dimmer": 0.25,
        "dim": 0.25,
        "brighter": 0.80,
        "bright": 0.80,
        "full": 1.00,
    }

    if (color_word is None) and (brightness_word is None):
        reply = "What color or brightness would you like for the lights?"
        return CommandResult(
            text=reply,
            effects=(Effect(kind="say", payload={"text": reply}),),
            followup_state={"intent": "lights_clarify"},
        )

    effects: list[Effect] = []
    if color_word is not None:
        effects.append(
            Effect(
                kind="led",
                payload={"op": "set_user_color", "color": color_map[color_word]},
            )
        )

    if brightness_word is not None:
        effects.append(
            Effect(
                kind="led",
                payload={"op": "set_user_brightness", "brightness": brightness_map[brightness_word]},
            )
        )

    if color_word and brightness_word:
        scene_brightness = "dim" if brightness_word in ("dim", "dimmer") else (
            "full brightness" if brightness_word == "full" else "bright"
        )
        reply = f"Okay, I will set the lights to a {scene_brightness} {color_word} scene."
    elif color_word:
        reply = f"Okay, I will set the lights to {color_word}."
    else:
        reply = (
            "Okay, I will make the lights dimmer."
            if brightness_word in ("dim", "dimmer")
            else (
                "Okay, I will set the lights to full brightness."
                if brightness_word == "full"
                else "Okay, I will make the lights brighter."
            )
        )

    effects.append(Effect(kind="say", payload={"text": reply}))
    return CommandResult(
        text=reply,
        effects=tuple(effects),
        followup_state={"intent": "lights", "color": color_word or "", "brightness": brightness_word or ""},
    )


def handle_light_intent(
    text: str,
    set_user_led_color: Callable[[str], None],
    set_user_brightness: Callable[[float], None],
    log: Callable[[str], None] = print,
) -> str:
    """Handle light commands while preserving existing response behavior."""
    result = handle_light_intent_result(text)
    raw_text = str(text or "").strip()

    for effect in result.effects:
        if effect.kind != "led":
            continue
        op = str(effect.payload.get("op", "") or "").strip().lower()
        if op == "set_user_color":
            color = str(effect.payload.get("color", "") or "").strip().lower()
            if color:
                set_user_led_color(color)
        elif op == "set_user_brightness":
            brightness = effect.payload.get("brightness")
            if isinstance(brightness, (int, float)):
                set_user_brightness(float(brightness))

    followup = result.followup_state if isinstance(result.followup_state, dict) else {}
    log_color = str(followup.get("color", "") or "none")
    log_brightness = str(followup.get("brightness", "") or "none")
    log(f"[INTENT][LIGHT] color={log_color} brightness={log_brightness} from text='{raw_text}'")
    return result.text
