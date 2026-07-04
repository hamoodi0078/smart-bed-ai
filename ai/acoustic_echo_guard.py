class AcousticEchoGuard:
    """Simple playback-aware suppression policy for barge-in capture."""

    def __init__(
        self, suppress_during_playback: bool = True, min_confidence_when_playing: float = 0.72
    ):
        self.suppress_during_playback = bool(suppress_during_playback)
        self.min_confidence_when_playing = float(min_confidence_when_playing)

    def should_accept_barge_in(self, playback_active: bool, text: str, confidence: float) -> bool:
        cleaned = str(text or "").strip()
        if not cleaned:
            return False
        if (not self.suppress_during_playback) or (not playback_active):
            return True
        return float(confidence or 0.0) >= self.min_confidence_when_playing
