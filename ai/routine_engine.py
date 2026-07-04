from typing import Optional, Tuple


class RoutineEngine:
    def __init__(self):
        self.breathing_guide = None

    def set_breathing_guide(self, breathing_guide):
        self.breathing_guide = breathing_guide

    WEEKDAY_MAP = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tues": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }

    def start_bedtime_routine(self, led, local_music, sleep_routine, minutes: int = 30) -> str:
        minutes = max(1, int(minutes))
        led.set_user_animation("breathing")
        led.set_user_brightness(0.25)
        local_music.play_query("")

        def _finish():
            local_music.pause()
            led.set_state("sleep")
            led.set_user_brightness(0.15)
            print("Bed: Bedtime routine finished. Music paused and lights dimmed.")

        sleep_routine.start_sleep_timer(minutes, _finish)
        return f"Bedtime routine started for {minutes} minute(s)."

    def trigger_morning_routine(self, led, local_music) -> str:
        led.set_state("speaking")
        led.set_user_animation("pulse")
        led.set_user_brightness(0.85)
        ok, message = local_music.play_query("")
        led.set_state("listening")
        if ok:
            return "Morning routine started: lights brightened and music started."
        return f"Morning routine started: lights brightened. {message}"

    def start_breathing_guide_routine(
        self,
        led,
        tts_manager,
        audio_player,
        duration_minutes: int = 5,
    ) -> str:
        if self.breathing_guide is None:
            return "Breathing guide is not available right now."
        return self.breathing_guide.start_breathing_guide(
            led_controller=led,
            tts_manager=tts_manager,
            audio_player=audio_player,
            duration_minutes=duration_minutes,
        )

    def stop_breathing_guide_routine(self) -> str:
        if self.breathing_guide is None:
            return "Breathing guide is not available right now."
        return self.breathing_guide.stop_breathing_guide()

    @staticmethod
    def parse_minutes_from_text(user_text: str, default_minutes: int = 30) -> int:
        lower = user_text.lower()
        parts = [
            p for p in lower.replace("minutes", "").replace("minute", "").split() if p.isdigit()
        ]
        if not parts:
            return default_minutes
        return max(1, int(parts[0]))

    @staticmethod
    def parse_time_from_text(user_text: str) -> Tuple[Optional[str], str]:
        lower = user_text.lower().strip()
        if "for" not in lower:
            return None, "Use: set morning routine for 07:00"

        time_part = user_text.split("for", 1)[1].strip()
        if ":" not in time_part:
            return None, "Use 24h format like 07:00"

        hhmm = time_part[:5]
        try:
            hour, minute = [int(x) for x in hhmm.split(":", 1)]
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None, "Use valid 24h time like 07:00"
        except Exception:
            return None, "Use valid 24h time like 07:00"

        return f"{hour:02d}:{minute:02d}", ""

    @classmethod
    def parse_repeat_days_from_text(cls, user_text: str) -> str:
        lower = user_text.lower()
        if "every day" in lower or "daily" in lower:
            return "0,1,2,3,4,5,6"
        if "weekdays" in lower:
            return "0,1,2,3,4"
        if "weekends" in lower:
            return "5,6"

        if "on " not in lower:
            return ""

        tail = lower.split("on", 1)[1]
        tokens = [x.strip(" ,.") for x in tail.replace("and", ",").split(",") if x.strip()]

        days = []
        for token in tokens:
            if token in cls.WEEKDAY_MAP:
                days.append(cls.WEEKDAY_MAP[token])

        if not days:
            return ""

        days = sorted(set(days))
        return ",".join(str(d) for d in days)
