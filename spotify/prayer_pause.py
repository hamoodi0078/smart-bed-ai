from __future__ import annotations

import datetime
import json
import os

from islamic_mode.prayer_times import PrayerTimesService
from spotify.spotify_controls import SpotifyControls


class PrayerPauseManager:
    def __init__(self, controls: SpotifyControls):
        self.controls = controls
        self.prayer_service = PrayerTimesService()
        self.log_path = os.path.join(os.path.dirname(__file__), "prayer_pauses.json")

    def _load_logs(self) -> list[dict]:
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _append_log(self, entry: dict) -> None:
        logs = self._load_logs()
        logs.append(entry)
        with open(self.log_path, "w", encoding="utf-8") as fh:
            json.dump(logs, fh, indent=2)

    def pause_for_prayer(self, prayer_name: str) -> dict:
        pause_result = self.controls.pause()
        paused_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self._append_log(
            {
                "action": "paused_for_prayer",
                "prayer_name": str(prayer_name),
                "timestamp": paused_at,
            }
        )
        return {
            "paused": bool(pause_result.get("success", False)),
            "reason": f"Prayer time: {prayer_name}",
            "paused_at": paused_at,
        }

    def resume_after_prayer(self) -> dict:
        result = self.controls.play()
        resumed_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self._append_log(
            {
                "action": "resumed_after_prayer",
                "timestamp": resumed_at,
                "success": bool(result.get("success", False)),
            }
        )
        response = dict(result)
        response["resumed_at"] = resumed_at
        return response

    def auto_pause_check(self) -> dict:
        if not self.prayer_service.is_prayer_approaching(minutes_before=3):
            return {"paused": False, "reason": "No prayer within 3 minutes."}

        next_prayer = self.prayer_service.get_next_prayer()
        prayer_name = str(next_prayer.get("name", "Prayer")).strip() or "Prayer"
        minutes_until = int(next_prayer.get("minutes_until", -1) or -1)
        if minutes_until < 0 or minutes_until > 3:
            return {"paused": False, "reason": "No prayer within 3 minutes."}
        return self.pause_for_prayer(prayer_name)
