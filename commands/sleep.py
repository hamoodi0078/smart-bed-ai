from collections.abc import Callable

from core.types import CommandResult, Effect


def handle_sleep_intent_result(text: str) -> CommandResult:
    """Build a pure sleep command result with declarative effects."""
    raw_text = str(text or "").strip()
    reply = "I have started sleep mode with a calm light scene."
    return CommandResult(
        text=reply,
        effects=(
            Effect(kind="store", payload={"op": "activate_sleep_scene"}),
            Effect(kind="say", payload={"text": reply}),
        ),
        followup_state={"intent": "sleep", "raw_text": raw_text},
    )


def handle_sleep_intent(
    text: str,
    activate_sleep_scene: Callable[[], str],
    log: Callable[[str], None] = print,
) -> str:
    """Handle sleep-mode command and keep historical response wording."""
    result = handle_sleep_intent_result(text)
    raw_text = str(text or "").strip()
    log(f"[INTENT][SLEEP] activating sleep scene for text='{raw_text}'")
    for effect in result.effects:
        if effect.kind != "store":
            continue
        op = str(effect.payload.get("op", "") or "").strip().lower()
        if op == "activate_sleep_scene":
            sleep_mode_line = activate_sleep_scene()
            if sleep_mode_line:
                log(f"[INTENT][SLEEP] {sleep_mode_line}")
    return result.text
