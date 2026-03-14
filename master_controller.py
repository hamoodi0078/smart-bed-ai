from __future__ import annotations

from dana.dana_core import DanaCore
from dana.personality import DanaPersonality
from guest_mode.guest_manager import GuestModeManager
from guest_mode.guest_settings import GuestSettings
from islamic_mode.dana_islamic_voice import DanaIslamicVoice
from islamic_mode.prayer_times import PrayerTimesService
from qr_code.pair_device import pair_device, unpair_device
from spotify.prayer_pause import PrayerPauseManager
from spotify.spotify_client import SpotifyClient
from spotify.spotify_controls import SpotifyControls


class MasterController:
    def __init__(self, user_name: str = "Hamoud"):
        self.dana = DanaCore(personality=DanaPersonality.GUIDE, user_name=user_name)
        self.prayer_service = PrayerTimesService()
        self.islamic_voice = DanaIslamicVoice(user_name=user_name)
        self.spotify_client = SpotifyClient()
        self.spotify_controls = SpotifyControls(self.spotify_client)
        self.prayer_pause = PrayerPauseManager(self.spotify_controls)
        self.guest_manager = GuestModeManager()
        self.guest_settings = GuestSettings()
        self.user_name = user_name
        self.islamic_mode_enabled = True
        self.spotify_connected = False
        print("[Danah Abu Halifa] Master Controller initialized. Dana is ready.")

    def handle_prayer_time(self, prayer_name: str, minutes_until: int):
        if self.guest_manager.is_active():
            return {"action": "skipped", "reason": "guest_mode"}

        if self.islamic_mode_enabled and int(minutes_until) <= 10:
            dana_message = self.islamic_voice.get_prayer_approaching_message(
                prayer_name=prayer_name,
                minutes_until=int(minutes_until),
            )
            spotify_paused = False
            if self.spotify_connected:
                pause_result = self.prayer_pause.pause_for_prayer(prayer_name)
                spotify_paused = bool(pause_result.get("paused", False))
            return {
                "action": "prayer_alert",
                "message": dana_message,
                "spotify_paused": spotify_paused,
            }

        return {
            "action": "none",
            "message": "No prayer alert triggered.",
            "spotify_paused": False,
        }

    def handle_wind_down(self, step: int):
        if self.guest_manager.is_active():
            return {
                "step": step,
                "message": "Guest Mode active: using basic wind-down only.",
                "spotify_fading": False,
            }

        dana_message = self.dana.guide.get_wind_down_message(step)
        spotify_fading = False
        if int(step) == 1 and self.spotify_connected:
            self.spotify_controls.fade_volume_down()
            spotify_fading = True

        return {
            "step": step,
            "message": dana_message,
            "spotify_fading": spotify_fading,
        }

    def handle_morning_wake(self, sleep_hours: float):
        if self.guest_manager.is_active():
            return {
                "message": "Good morning! Guest Mode wake-up complete.",
                "spotify_fading_up": False,
            }

        wake_template = self.dana.get_config().wake_message
        wake_message = wake_template.format(hours=f"{float(sleep_hours):.1f}")
        spotify_fading_up = False
        if self.spotify_connected:
            self.spotify_controls.fade_volume_up()
            spotify_fading_up = True

        return {
            "message": wake_message,
            "spotify_fading_up": spotify_fading_up,
        }

    def handle_bed_reset(self, device_id: str):
        unpair_device(device_id)
        if self.guest_manager.is_active():
            self.guest_manager.deactivate()
        self.dana.switch_personality(DanaPersonality.GUIDE)
        return {"reset": True, "message": "Bed has been reset. All data cleared."}

    def switch_dana_personality(self, personality_name: str):
        mapping = {
            "coach": DanaPersonality.COACH,
            "guide": DanaPersonality.GUIDE,
            "therapist": DanaPersonality.THERAPIST,
        }
        personality_key = str(personality_name or "").strip().lower()
        target = mapping.get(personality_key)
        if target is None:
            return "Invalid personality. Choose coach, guide, or therapist."
        return self.dana.switch_personality(target)

    def get_system_status(self):
        return {
            "dana_personality": self.dana.personality.value,
            "islamic_mode": self.islamic_mode_enabled,
            "spotify_connected": self.spotify_connected,
            "guest_mode_active": self.guest_manager.is_active(),
            "user_name": self.user_name,
        }


if __name__ == "__main__":
    controller = MasterController(user_name="Hamoud")
    print(controller.get_system_status())
    print(controller.dana.get_greeting())
