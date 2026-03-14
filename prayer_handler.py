"""Prayer and Islamic support helpers extracted from conversational flow and automation hooks."""

from __future__ import annotations

from led.led_control import LEDController

def normalize_followup_tone(value: str) -> str:
    tone = str(value or "soft").strip().lower().replace("-", " ").replace("_", " ")
    if tone in ("teen", "teen friendly", "teenfriendly", "gen z", "youth"):
        return "teen"
    if tone in ("islamic", "islamic supportive", "faith", "deen"):
        return "islamic"
    return "soft"

def is_islamic_reminder_request(lowered_user_text: str) -> bool:
    text = str(lowered_user_text or "").lower()
    return (
        ("islamic reminder" in text)
        or ("remind me about islam" in text)
        or ("deen reminder" in text)
        or ("allah" in text)
    )

def next_islamic_reminder(profile: dict) -> str:
    reminders = [
        "A gentle reminder: stay grateful and protect your prayers on time.",
        "A gentle reminder: be honest and keep your promises.",
        "A gentle reminder: seek beneficial knowledge and work hard with sincerity.",
    ]
    runtime_flags = profile.setdefault("runtime_flags", {})
    reminder_index = int(runtime_flags.get("islamic_reminder_index", 0))
    selected = reminders[reminder_index % len(reminders)]
    runtime_flags["islamic_reminder_index"] = reminder_index + 1
    return selected

def apply_fajr_gentle_light_scene(led: LEDController):
    led.set_user_animation("breathing")
    led.set_color_value("orange")
    led.set_user_brightness(0.12)
    led.set_state("sleep")
