import threading
import time
from datetime import datetime
from typing import Callable, Optional


class BreathingGuideEngine:
    """4-7-8 breathing routine with LED + voice guidance."""

    def __init__(self):
        self.is_running = False
        self.current_phase = "idle"
        self.cycle_count = 0
        self.total_cycles = 0
        self.start_time = None
        self.thread = None
        self.stop_event = threading.Event()

        self.phases = {
            "inhale": 4.0,
            "hold": 7.0,
            "exhale": 8.0,
            "pause": 2.0,
        }

        self.phase_prompts = {
            "start": "Begin 4-7-8 breathing. Inhale gently through your nose.",
            "inhale": "Breathe in",
            "hold": "Hold",
            "exhale": "Exhale slowly",
            "complete": "Breathing session complete. You are ready to rest.",
        }

        self.led_controller = None
        self.tts_manager = None
        self.audio_player = None
        self.on_complete = None

    def set_led_controller(self, led_controller):
        self.led_controller = led_controller

    def set_tts_manager(self, tts_manager):
        self.tts_manager = tts_manager

    def set_audio_player(self, audio_player):
        self.audio_player = audio_player

    def start_breathing_guide(
        self,
        led_controller,
        tts_manager,
        audio_player,
        duration_minutes: int = 5,
        on_complete: Optional[Callable] = None,
    ) -> str:
        if self.is_running:
            return "Breathing guide is already running."

        self.led_controller = led_controller
        self.tts_manager = tts_manager
        self.audio_player = audio_player
        self.on_complete = on_complete

        self.stop_event.clear()
        self.is_running = True
        self.current_phase = "starting"
        self.cycle_count = 0
        self.start_time = datetime.now()

        cycle_duration = sum(self.phases.values())
        self.total_cycles = max(1, int((max(1, duration_minutes) * 60) / cycle_duration))

        self.thread = threading.Thread(target=self._run_breathing_cycles, daemon=True)
        self.thread.start()
        return f"Started 4-7-8 breathing guide for {duration_minutes} minute(s)."

    def stop_breathing_guide(self) -> str:
        if not self.is_running:
            return "Breathing guide is not running."

        self.stop_event.set()
        self.is_running = False
        self.current_phase = "idle"

        if self.led_controller is not None:
            self.led_controller.set_user_animation("breathing")
            self.led_controller.set_user_brightness(0.15)
            self.led_controller.set_state("sleep")

        return "Breathing guide stopped."

    def _run_breathing_cycles(self):
        try:
            self._speak_prompt(self.phase_prompts["start"])
            time.sleep(1.2)

            for idx in range(self.total_cycles):
                if self.stop_event.is_set():
                    break
                self.cycle_count = idx + 1

                self._run_phase("inhale", self.phases["inhale"], start_b=0.2, end_b=0.8)
                self._run_phase("hold", self.phases["hold"], start_b=0.65, end_b=0.65)
                self._run_phase("exhale", self.phases["exhale"], start_b=0.8, end_b=0.2)
                if idx < self.total_cycles - 1:
                    self._run_phase("pause", self.phases["pause"], start_b=0.2, end_b=0.2)

            if not self.stop_event.is_set():
                self.current_phase = "complete"
                self._speak_prompt(self.phase_prompts["complete"])
                if self.led_controller is not None:
                    self.led_controller.set_user_animation("breathing")
                    self.led_controller.set_user_brightness(0.15)
                    self.led_controller.set_state("sleep")
                if self.on_complete:
                    self.on_complete()
        except Exception as exc:
            print(f"[BreathingGuide] error: {exc}")
        finally:
            self.is_running = False
            self.current_phase = "idle"

    def _run_phase(self, phase_name: str, duration: float, start_b: float, end_b: float):
        if self.stop_event.is_set():
            return

        self.current_phase = phase_name
        if self.led_controller is not None:
            self.led_controller.set_user_animation("breathing")

        if phase_name in self.phase_prompts and phase_name != "pause":
            self._speak_prompt(self.phase_prompts[phase_name])

        steps = max(6, int(duration * 3))
        step_duration = duration / steps
        for i in range(steps):
            if self.stop_event.is_set():
                return
            progress = i / max(1, steps - 1)
            brightness = start_b + (end_b - start_b) * progress
            if self.led_controller is not None:
                self.led_controller.set_user_brightness(brightness, log=False)
            time.sleep(step_duration)

    def _speak_prompt(self, text: str):
        if not self.tts_manager or not self.audio_player:
            return
        try:
            audio_file = self.tts_manager.synthesize_to_mp3(
                text=text,
                filename=f"breathing_prompt_{int(time.time())}.mp3",
                pace_override=0.85,
            )
            if audio_file:
                self.audio_player.play_file(audio_file)
        except Exception as exc:
            print(f"[BreathingGuide] prompt error: {exc}")

    def get_status(self) -> dict:
        elapsed = 0.0
        if self.start_time is not None:
            elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "running": self.is_running,
            "phase": self.current_phase,
            "cycle": self.cycle_count,
            "total_cycles": self.total_cycles,
            "elapsed_time": elapsed,
        }
