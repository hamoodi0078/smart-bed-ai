"""Local wake-word / wake-phrase detector.

Runs entirely on-device with zero cloud calls.  Supports English and
Arabic aliases, fuzzy matching for common STT mis-transcriptions, and
returns a confidence-like score so callers can apply their own threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from loguru import logger


_DEFAULT_ALIASES: tuple[str, ...] = (
    "hey dana",
    "ok dana",
    "hi dana",
    "يا دانة",
    "هاي دانة",
)

_FUZZY_THRESHOLD = 0.80


@dataclass(frozen=True)
class WakeResult:
    """Outcome of a wake-word detection attempt."""
    detected: bool
    matched_phrase: str = ""
    score: float = 0.0


class LocalWakeWordDetector:
    """Local-only wake phrase matcher. No cloud calls required."""

    def __init__(
        self,
        primary_phrase: str = "hey smart bed",
        aliases: Iterable[str] | None = None,
        fuzzy_threshold: float = _FUZZY_THRESHOLD,
    ):
        self.primary_phrase = str(primary_phrase or "hey smart bed").strip().lower()
        self.fuzzy_threshold = float(fuzzy_threshold)

        normalized_aliases: list[str] = []
        for alias in aliases or _DEFAULT_ALIASES:
            item = str(alias or "").strip().lower()
            if item and item not in normalized_aliases and item != self.primary_phrase:
                normalized_aliases.append(item)
        self.aliases = tuple(normalized_aliases[:16])

        logger.debug(
            "WakeWordDetector: primary='{}', {} aliases, fuzzy={:.0%}",
            self.primary_phrase,
            len(self.aliases),
            self.fuzzy_threshold,
        )

    @property
    def all_phrases(self) -> tuple[str, ...]:
        return (self.primary_phrase, *self.aliases)

    def detect_in_text(self, text: str) -> bool:
        """Simple boolean check — backward-compatible API."""
        return self.detect(text).detected

    def detect(self, text: str) -> WakeResult:
        """Return a ``WakeResult`` with the best match and confidence score."""
        candidate = str(text or "").strip().lower()
        if not candidate:
            return WakeResult(detected=False)

        # Exact substring match (fast path)
        for phrase in self.all_phrases:
            if phrase in candidate:
                return WakeResult(detected=True, matched_phrase=phrase, score=1.0)

        # Fuzzy match for STT mis-transcriptions
        best_score = 0.0
        best_phrase = ""
        for phrase in self.all_phrases:
            ratio = SequenceMatcher(None, phrase, candidate[:len(phrase) + 5]).ratio()
            if ratio > best_score:
                best_score = ratio
                best_phrase = phrase

        if best_score >= self.fuzzy_threshold:
            return WakeResult(detected=True, matched_phrase=best_phrase, score=best_score)

        return WakeResult(detected=False, matched_phrase=best_phrase, score=best_score)
