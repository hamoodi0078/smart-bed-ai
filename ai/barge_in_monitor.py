import threading
import time


class ContinuousBargeInMonitor:
    """Continuously monitors mic energy while AI is speaking."""

    def __init__(self, wake_word_manager, poll_interval_seconds: float = 0.12):
        self.wake_word_manager = wake_word_manager
        self.poll_interval_seconds = max(0.05, float(poll_interval_seconds))
        self._active = threading.Event()
        self._thread = None

    def start(self, on_barge_in):
        self.stop()
        self._active.set()

        def _run():
            while self._active.is_set():
                try:
                    text, confidence = (
                        self.wake_word_manager.capture_barge_in_text_with_confidence()
                    )
                    cleaned = self.wake_word_manager._sanitize_barge_in_text(text, confidence)
                    if cleaned:
                        on_barge_in(cleaned, confidence)
                        self._active.clear()
                        break
                except Exception:
                    pass
                time.sleep(self.poll_interval_seconds)

        self._thread = threading.Thread(target=_run, name="barge-in-monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._active.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.4)
        self._thread = None
