"""Emotion detection and routing for Smart Bed AI.

Primary: distilroberta-based transformer classifier (j-hartmann/emotion-english-distilroberta-base).
Fallback: keyword scoring — used when the model is unavailable or text is too short.
"""

from __future__ import annotations

from typing import Dict

from loguru import logger

# ---------------------------------------------------------------------------
# Transformer classifier (optional — graceful fallback when not installed)
# ---------------------------------------------------------------------------

_CLASSIFIER = None
_CLASSIFIER_ATTEMPTED = False

_LABEL_MAP = {
    # HuggingFace model labels → Danah emotion states
    "anger": "distressed",
    "disgust": "distressed",
    "fear": "distressed",
    "sadness": "low_energy",
    "joy": "motivated",
    "surprise": "motivated",
    "neutral": "neutral",
    # secondary names some models use
    "happy": "motivated",
    "excited": "motivated",
    "tired": "low_energy",
    "anxious": "distressed",
    "stressed": "distressed",
}


def _get_classifier():
    global _CLASSIFIER, _CLASSIFIER_ATTEMPTED
    if _CLASSIFIER_ATTEMPTED:
        return _CLASSIFIER
    _CLASSIFIER_ATTEMPTED = True
    try:
        from transformers import pipeline  # type: ignore
        _CLASSIFIER = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=None,
            truncation=True,
        )
        logger.info("Emotion transformer classifier loaded.")
    except Exception as exc:
        logger.warning("Transformer classifier unavailable — using keyword fallback. err=%s", exc)
        _CLASSIFIER = None
    return _CLASSIFIER


# ---------------------------------------------------------------------------
# Keyword fallback (extended vocabulary)
# ---------------------------------------------------------------------------

EMOTION_KEYWORDS: Dict[str, tuple] = {
    "distressed": (
        # English
        "overwhelmed", "anxious", "panic", "panic attack", "stressed", "stress",
        "i can't handle", "i am not okay", "burned out", "burn out", "exhausted mentally",
        "can't cope", "freaking out", "terrified", "dread", "doom", "hopeless",
        "falling apart", "breaking down", "losing it", "angry", "furious", "rage",
        "hate this", "so frustrated", "unbearable",
        # Arabic
        "ضايج", "قلقان", "متوتر", "مستعجل", "زعلان", "غاضب", "عصبي",
        "ما قدرت", "ما اقدر", "ضاق صدري", "انقبض قلبي", "خايف", "فزع",
        "يائس", "مكسور", "منهار", "ماشي وضعي", "عصبت", "ضايقني",
        "مقدر", "مقدر اتحمل", "شعور سيء", "احساس زفت",
    ),
    "low_energy": (
        # English
        "tired", "exhausted", "no energy", "sleepy", "drained", "fatigue",
        "fatigued", "sluggish", "groggy", "heavy", "can't move", "worn out",
        "zero energy", "completely drained", "burned out physically",
        # Arabic
        "تعبان", "منهك", "ما فيني طاقة", "نوم", "نعسان", "خامل",
        "ثقيل", "ما اقدر اتحرك", "فيني ركود", "مافي حيل",
    ),
    "motivated": (
        # English
        "let's do this", "motivated", "ready", "excited", "i can do it",
        "pumped", "energized", "fired up", "can't wait", "let's go",
        "feeling great", "on top of it", "productive", "focused", "determined",
        "inspired", "positive", "optimistic",
        # Arabic
        "يلا نسوي", "جاهز", "متحمس", "اقدر", "بقوة", "نشيط",
        "مستعد", "احساس حلو", "مرتاح", "مبسوط", "فرحان", "واثق",
    ),
    "dream_positive": (
        "beautiful dream", "peaceful dream", "happy dream", "wonderful",
        "amazing dream", "great dream", "lovely dream", "nice dream",
        "had a good dream", "dreamed about paradise",
        # Arabic
        "حلم حلو", "حلم جميل", "حلم طيب", "حلم هادئ", "حلم سعيد",
    ),
    "dream_negative": (
        "nightmare", "scary dream", "bad dream", "terrifying dream",
        "horrible dream", "had a nightmare", "woke up scared",
        "dark dream", "disturbing dream",
        # Arabic
        "كابوس", "حلم مرعب", "حلم سيء", "حلم فظيع", "صحيت خايف",
        "حلم مزعج", "حلم كئيب",
    ),
    "neutral": (
        "okay", "fine", "alright", "normal", "usual", "same",
        # Arabic
        "تمام", "كويس", "ماشي", "عادي", "نفس الشي", "زي الحال",
    ),
}


def _keyword_score(text: str) -> str:
    lower = text.lower()
    scores: Dict[str, int] = {}
    for state, keywords in EMOTION_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in lower)
        if count:
            scores[state] = count
    if not scores:
        return "neutral"
    return max(scores, key=lambda s: scores[s])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_emotion_state(user_text: str) -> str:
    """Detect dominant emotion. Uses transformer model, falls back to keywords."""
    text = (user_text or "").strip()
    if not text:
        return "neutral"

    # Dream shortcuts (always keyword-driven — model isn't trained on these)
    lower = text.lower()
    if any(k in lower for k in EMOTION_KEYWORDS["dream_negative"]):
        return "dream_negative"
    if any(k in lower for k in EMOTION_KEYWORDS["dream_positive"]):
        return "dream_positive"

    # Try transformer
    clf = _get_classifier()
    if clf is not None and len(text.split()) >= 3:
        try:
            results = clf(text[:512])
            # results is a list of dicts [{"label": ..., "score": ...}]
            if results and isinstance(results[0], list):
                results = results[0]
            best = max(results, key=lambda r: float(r.get("score", 0)))
            label = str(best.get("label", "")).lower()
            mapped = _LABEL_MAP.get(label, "neutral")
            logger.debug("Transformer: label=%s score=%.2f → %s", label, best.get("score", 0), mapped)
            return mapped
        except Exception as exc:
            logger.debug("Transformer inference failed, using keywords: %s", exc)

    # Keyword fallback
    return _keyword_score(text)


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


def emotion_tts_profile(emotion_state: str) -> dict:
    """Map emotional state to voice prosody controls for calming/energizing mirroring."""
    state = str(emotion_state or "neutral").strip().lower()
    profiles: Dict[str, dict] = {
        "distressed": {
            "profile_override": "whisper",
            "pace_multiplier": 0.88,
            "stability": "steady",
            "pitch_style": "lower",
        },
        "anxious": {
            "profile_override": "whisper",
            "pace_multiplier": 0.9,
            "stability": "steady",
            "pitch_style": "lower",
        },
        "sad": {
            "profile_override": "soft",
            "pace_multiplier": 0.92,
            "stability": "gentle",
            "pitch_style": "lower",
        },
        "low_energy": {
            "profile_override": "soft",
            "pace_multiplier": 0.94,
            "stability": "gentle",
            "pitch_style": "warm",
        },
        "motivated": {
            "profile_override": "default",
            "pace_multiplier": 1.04,
            "stability": "confident",
            "pitch_style": "brighter",
        },
        "excited": {
            "profile_override": "default",
            "pace_multiplier": 1.06,
            "stability": "expressive",
            "pitch_style": "brighter",
        },
        "dream_negative": {
            "profile_override": "whisper",
            "pace_multiplier": 0.9,
            "stability": "steady",
            "pitch_style": "lower",
        },
        "dream_positive": {
            "profile_override": "default",
            "pace_multiplier": 1.02,
            "stability": "warm",
            "pitch_style": "warm",
        },
        "neutral": {
            "profile_override": "default",
            "pace_multiplier": 1.0,
            "stability": "balanced",
            "pitch_style": "neutral",
        },
    }
    return dict(profiles.get(state, profiles["neutral"]))