import threading
from typing import Callable, Optional


class SleepRoutineManager:
    def __init__(self):
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._active_minutes: Optional[int] = None

    def start_sleep_timer(self, minutes: int, on_finish: Callable[[], None]) -> str:
        minutes = max(1, int(minutes))

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()

            timer = threading.Timer(minutes * 60, on_finish)
            timer.daemon = True
            timer.start()

            self._timer = timer
            self._active_minutes = minutes

        return f"Sleep timer started for {minutes} minute(s)."

    def cancel_sleep_timer(self) -> str:
        with self._lock:
            if self._timer is None:
                return "No active sleep timer."

            self._timer.cancel()
            self._timer = None
            self._active_minutes = None
            return "Sleep timer canceled."

    def has_active_timer(self) -> bool:
        with self._lock:
            return self._timer is not None

    def status_text(self) -> str:
        with self._lock:
            if self._timer is None:
                return "No active sleep timer."
            return f"Sleep timer is active for {self._active_minutes} minute(s)."
