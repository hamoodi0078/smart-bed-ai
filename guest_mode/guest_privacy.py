from __future__ import annotations

import datetime
import json
import os


class GuestPrivacyManager:
    def __init__(self):
        self.temp_data_file = "guest_mode/guest_temp_data.json"

    def clear_session_data(self) -> dict:
        if os.path.exists(self.temp_data_file):
            try:
                os.remove(self.temp_data_file)
                return {"cleared": True, "file": self.temp_data_file}
            except OSError as exc:
                return {"cleared": False, "file": self.temp_data_file, "error": str(exc)}
        return {"cleared": True, "file": self.temp_data_file}

    def block_voice_recording(self) -> dict:
        return {
            "recording_blocked": True,
            "reason": "Guest Mode active — voice data is not stored",
        }

    def get_privacy_summary(self) -> dict:
        return {
            "stored": ["nothing"],
            "not_stored": ["voice commands", "LED preferences", "sleep data", "usage patterns"],
        }

    def log_guest_action(self, action: str) -> dict:
        os.makedirs(os.path.dirname(self.temp_data_file), exist_ok=True)

        payload: dict = {"actions": []}
        if os.path.exists(self.temp_data_file):
            try:
                with open(self.temp_data_file, "r", encoding="utf-8") as fh:
                    existing = json.load(fh)
                if isinstance(existing, dict):
                    payload = existing
            except (OSError, json.JSONDecodeError):
                payload = {"actions": []}

        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            actions = []
        entry = {
            "action": str(action or ""),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        actions.append(entry)
        payload["actions"] = actions

        with open(self.temp_data_file, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        return entry
