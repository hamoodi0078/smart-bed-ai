import re
from typing import Any, Dict

from ai.intent_classifier import detect_implicit_intent


TRANSLITERATION_MAP = {
    "wndwn": "wind down",
    "windown": "wind down",
    "winedown": "wind down",
    "hadi": "calm",
    "hady": "calm",
    "hada": "calm",
    "nawm": "sleep",
    "sukut": "quiet",
    "sokoot": "quiet",
    "moosica": "music",
    "musiqa": "music",
    "dont talk much": "keep it simple",
    "don't talk much": "keep it simple",
}


def normalize_mixed_text(text: str) -> str:
    raw = (text or "").lower()
    raw = raw.replace("؟", "?").replace("،", " ").replace("؛", " ").replace("\u0640", "")
    raw = re.sub(r"[^a-z0-9\u0600-\u06ff\s#%'-]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    normalized = f" {raw} "
    for bad, good in TRANSLITERATION_MAP.items():
        normalized = normalized.replace(f" {bad} ", f" {good} ")
    return re.sub(r"\s+", " ", normalized).strip()


def _result(intent: str = "", slots: Dict[str, Any] | None = None, confidence: float = 0.0, clarify: str = "") -> dict:
    slots = slots or {}
    return {
        "intent": intent,
        "slots": slots,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "requires_confirmation": bool(clarify),
        "clarify_question": clarify,
    }


def resolve_action(user_text: str, profile: dict, context: dict | None = None) -> dict:
    text = normalize_mixed_text(user_text)
    context = context or {}

    if not text:
        return _result()

    implicit = detect_implicit_intent(user_text)
    if implicit:
        slots = dict(implicit.get("slots", {}))
        partner_line = str(implicit.get("partner_line", "")).strip()
        if partner_line:
            slots["partner_line"] = partner_line
        return _result(
            intent=str(implicit.get("intent", "")).strip().lower(),
            slots=slots,
            confidence=float(implicit.get("confidence", 0.0) or 0.0),
        )

    if any(k in text for k in ("undo that", "revert last action", "undo last action")):
        return _result("undo_last_action", confidence=0.98)

    sleep_scope = any(k in text for k in ("sleep", "wind down", "winddown", "tired", "calm", "relax", "نوم", "تهد", "هاد"))
    lights_scope = any(k in text for k in ("light", "lights", "scene", "dim", "brightness", "اضاء", "ضوء", "لون"))
    music_scope = any(k in text for k in ("music", "ambient", "song", "spotify", "audio", "موسيقى", "اغنية", "أغنية"))

    if sleep_scope and ("wind down" in text or "help me sleep" in text or "optimize" in text or "sleep now" in text):
        return _result("start_wind_down", slots={"minutes": 45}, confidence=0.9)

    if (sleep_scope and lights_scope and music_scope) or (
        lights_scope and music_scope and any(k in text for k in ("soft", "softer", "calm", "ambient", "low"))
    ):
        return _result("start_wind_down", slots={"minutes": 45}, confidence=0.86)

    if lights_scope and any(k in text for k in ("soft", "softer", "dim", "warm", "calm", "هاد", "خف")):
        brightness = 0.18 if ("very" in text or "much" in text or "جدا" in text) else 0.24
        return _result(
            "set_scene",
            slots={
                "scene_key": "calm_recovery",
                "brightness": brightness,
                "color": "warmwhite",
                "animation": "breathing",
                "proactive_offer": "evening_routine",
                "partner_line": "I'll dim the lights for you. Shall we start your evening routine?",
            },
            confidence=0.83,
        )

    if music_scope and any(k in text for k in ("play", "start", "on", "شغل", "تشغيل")):
        query = "ambient" if any(k in text for k in ("ambient", "calm", "sleep", "هاد", "نوم")) else ""
        return _result("play_music", slots={"query": query}, confidence=0.82)

    if music_scope and any(k in text for k in ("pause", "stop", "off", "وقف", "ايقاف", "إيقاف")):
        return _result("pause_music", confidence=0.88)

    if any(k in text for k in ("dont talk much", "don't talk much", "keep it simple", "short replies", "quiet replies", "تكلم قليل", "رد قصير")):
        return _result("set_response_style", slots={"response_style": "quick", "thinking_ack_mode": "off"}, confidence=0.91)

    if any(k in text for k in ("talk more", "detailed", "in detail", "شرح", "تفصيل")):
        return _result("set_response_style", slots={"response_style": "detailed"}, confidence=0.8)

    if sleep_scope and not (lights_scope or music_scope):
        return _result(
            "start_wind_down",
            slots={"minutes": 30},
            confidence=0.6,
            clarify="Do you want me to start wind-down now with dim lights and calm audio?",
        )

    if lights_scope and not music_scope and "scene" not in text:
        return _result(
            "set_scene",
            slots={"scene_key": "balanced_default"},
            confidence=0.58,
            clarify="Should I set a calm dim scene or keep normal brightness?",
        )

    if music_scope and not any(k in text for k in ("play", "pause", "stop")):
        return _result(
            "play_music",
            slots={"query": "ambient"},
            confidence=0.55,
            clarify="Do you want calm ambient playback now?",
        )

    return _result()
