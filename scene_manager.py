"""Scene management helpers for scene payload creation and scene clarification follow-ups."""

from __future__ import annotations

import re

def normalize_for_intent(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-z0-9#(),\s'\u0600-\u06ff]+", " ", (text or "").lower()),
    ).strip()

def has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)

def _scene_payload_from_key(scene_key: str, slots: dict) -> dict:
    key = str(scene_key or "").strip().lower()
    if key == "calm_recovery":
        return {
            "key": "calm_recovery",
            "animation": slots.get("animation", "breathing"),
            "color": slots.get("color", "warmwhite"),
            "brightness": float(slots.get("brightness", 0.2)),
            "line": "Environment scene: calm recovery.",
        }
    if key == "balanced_default":
        return {
            "key": "balanced_default",
            "animation": slots.get("animation", "solid"),
            "color": slots.get("color", "white"),
            "brightness": float(slots.get("brightness", 0.4)),
            "line": "Environment scene: balanced default.",
        }
    return {
        "key": key or "balanced_default",
        "animation": slots.get("animation", "solid"),
        "color": slots.get("color", "white"),
        "brightness": float(slots.get("brightness", 0.35)),
        "line": "Environment scene updated.",
    }

def _resolve_scene_clarification_followup(user_text: str) -> dict | None:
    normalized = normalize_for_intent(user_text)
    if not normalized:
        return None

    prefers_normal = any(
        phrase in normalized
        for phrase in (
            "keep normal",
            "normal brightness",
            "normal",
            "default",
            "regular",
            "as is",
            "same brightness",
            "full brightness",
            "keep bright",
        )
    )
    prefers_calm = any(
        phrase in normalized
        for phrase in (
            "calm",
            "dim",
            "dimmer",
            "soft",
            "warm",
            "cozy",
            "هاد",
            "خف",
            "هادئ",
        )
    )

    if prefers_normal and not prefers_calm:
        return {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}}

    if prefers_calm:
        brightness = 0.18 if any(k in normalized for k in ("very", "much", "جدا")) else 0.24
        return {
            "intent": "set_scene",
            "slots": {
                "scene_key": "calm_recovery",
                "brightness": brightness,
                "color": "warmwhite",
                "animation": "breathing",
            },
        }
    return None

def _is_scene_clarification_candidate(user_text: str) -> bool:
    normalized = normalize_for_intent(user_text)
    if not normalized:
        return False
    return has_any(
        normalized,
        (
            "light",
            "lights",
            "brightness",
            "bright",
            "dim",
            "calm",
            "normal",
            "scene",
            "color",
            "strip",
            "اضاءة",
            "إضاءة",
            "سطوع",
            "هاد",
            "خف",
            "عادي",
        ),
    )

