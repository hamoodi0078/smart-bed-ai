from datetime import datetime


class SensorBridge:
    """Modular hardware-event bridge for pressure/motion-driven proactive greetings."""

    def __init__(self):
        self._last_morning_date = ""
        self._last_evening_date = ""

    def classify_event(self, pressure_active: bool, motion_active: bool, now: datetime | None = None) -> str:
        now = now or datetime.now()
        if not (pressure_active or motion_active):
            return ""

        today = now.date().isoformat()
        if 18 <= now.hour <= 23:
            if self._last_evening_date != today:
                self._last_evening_date = today
                return "bed_entered_evening"
        if 5 <= now.hour <= 11:
            if self._last_morning_date != today:
                self._last_morning_date = today
                return "wake_detected_morning"
        return ""

    @staticmethod
    def tts_profile_for_time(now: datetime | None = None) -> dict:
        now = now or datetime.now()
        if now.hour >= 23 or now.hour < 6:
            return {
                "profile_override": "whisper",
                "pace_multiplier": 0.9,
                "volume_multiplier": 0.58,
                "label": "night_whisper",
            }
        return {
            "profile_override": "default",
            "pace_multiplier": 1.0,
            "volume_multiplier": 1.0,
            "label": "default",
        }

    def proactive_greeting(self, event_name: str, user_name: str = "") -> str:
        name = str(user_name or "").strip()
        prefix = f"{name}, " if name else ""
        if event_name == "bed_entered_evening":
            return f"{prefix}welcome in. I can start a calm evening wind-down whenever you are ready."
        if event_name == "wake_detected_morning":
            return f"{prefix}good morning. I can start a gentle wake routine and today plan in under one minute."
        return ""
