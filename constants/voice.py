"""Voice recognition and audio constants."""

from __future__ import annotations


class VoiceThresholds:
    """Voice recognition confidence thresholds."""

    CONFIRM_THRESHOLD: float = 0.58
    MIN_ACCEPT_THRESHOLD: float = 0.50
    ECHO_REJECTION: float = 0.30
    HIGH_CONFIDENCE: float = 0.85


class TTSDefaults:
    """Text-to-speech defaults."""

    MAX_CHUNK_CHARS: int = 500
    FAST_START_SPLIT_CHARS: int = 80
    DEFAULT_SPEED: float = 1.0
    MIN_SPEED: float = 0.5
    MAX_SPEED: float = 2.0


class WakeWordDefaults:
    """Wake word detection defaults."""

    DEFAULT_PHRASE: str = "hey smart bed"
    DEFAULT_TIMEOUT_SECONDS: int = 3
    DEFAULT_PHRASE_LIMIT_SECONDS: int = 3
    BARGE_IN_TIMEOUT_SECONDS: int = 1
    BARGE_IN_PHRASE_LIMIT_SECONDS: int = 1


THERAPIST_DISTRESS_KEYWORDS: tuple[str, ...] = (
    "sad",
    "upset",
    "worried",
    "worry",
    "anxious",
    "stressed",
    "stress",
    "overwhelmed",
    "scared",
    "lonely",
    "depressed",
    "hurt",
    "cry",
    "hopeless",
    "empty",
    "panic",
    "fear",
    "i feel bad",
    "i feel down",
    "i am not okay",
    "im not okay",
    "i'm not okay",
    "i feel worried",
    "\u0642\u0644\u0642\u0627\u0646",
    "\u062d\u0632\u064a\u0646",
    "\u0632\u0639\u0644\u0627\u0646",
    "\u0645\u062a\u0648\u062a\u0631",
    "\u0645\u0636\u063a\u0648\u0637",
)
