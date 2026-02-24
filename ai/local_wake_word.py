from typing import Iterable


class LocalWakeWordDetector:
    """Local-only wake phrase matcher. No cloud calls required."""

    def __init__(self, primary_phrase: str = "hey smart bed", aliases: Iterable[str] | None = None):
        self.primary_phrase = str(primary_phrase or "hey smart bed").strip().lower()
        normalized_aliases = []
        for alias in aliases or []:
            item = str(alias or "").strip().lower()
            if item and item not in normalized_aliases and item != self.primary_phrase:
                normalized_aliases.append(item)
        self.aliases = tuple(normalized_aliases[:8])

    def detect_in_text(self, text: str) -> bool:
        candidate = str(text or "").strip().lower()
        if not candidate:
            return False
        if self.primary_phrase in candidate:
            return True
        return any(alias in candidate for alias in self.aliases)
