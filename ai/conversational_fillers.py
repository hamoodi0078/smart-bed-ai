import random
import time
from typing import Sequence


class ConversationalFillerManager:
    """Plays short relational fillers when LLM latency is noticeable."""

    def __init__(
        self,
        trigger_after_seconds: float = 0.5,
        cooldown_seconds: float = 12.0,
        filler_lines: Sequence[str] | None = None,
    ):
        self.trigger_after_seconds = max(0.2, float(trigger_after_seconds))
        self.cooldown_seconds = max(2.0, float(cooldown_seconds))
        self.filler_lines = tuple(
            filler_lines
            or (
                "Hmm...",
                "I see...",
                "Give me one second...",
            )
        )
        self._last_played_ts = 0.0

    def should_play(self, elapsed_seconds: float) -> bool:
        if float(elapsed_seconds) < self.trigger_after_seconds:
            return False
        return (time.monotonic() - self._last_played_ts) >= self.cooldown_seconds

    def pick(self) -> str:
        if not self.filler_lines:
            return ""
        line = random.choice(self.filler_lines)
        self._last_played_ts = time.monotonic()
        return str(line).strip()
