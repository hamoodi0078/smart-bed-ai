from __future__ import annotations

import datetime
import json
import os


class WindDownSession:
    STEPS = [1, 2, 3, 4]
    STEP_NAMES = {
        1: "Breathing",
        2: "Dim Lights",
        3: "Ambient Audio",
        4: "Sleep Ready",
    }
    STEP_DURATIONS = {
        1: 120,
        2: 60,
        3: 180,
        4: 60,
    }

    def __init__(self):
        base_dir = os.path.dirname(__file__)
        self.active_file = os.path.join(base_dir, "active_winddown.json")
        self.history_file = os.path.join(base_dir, "winddown_history.json")

    def _read_json(self, file_path: str, default):
        if not os.path.exists(file_path):
            return default
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return default
        return payload

    def _write_json(self, file_path: str, payload) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def _build_session_id(self) -> str:
        now_tag = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rand_tag = os.urandom(4).hex()
        return f"wd_{now_tag}_{rand_tag}"

    def start(self, user_id: str) -> dict:
        session = {
            "session_id": self._build_session_id(),
            "user_id": str(user_id),
            "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "current_step": 1,
            "status": "active",
        }
        self._write_json(self.active_file, session)
        return session

    def next_step(self):
        active = self._read_json(self.active_file, {})
        if not isinstance(active, dict) or not active:
            return None
        if str(active.get("status", "")) != "active":
            return "completed"

        next_value = int(active.get("current_step", 1) or 1) + 1
        if next_value > max(self.STEPS):
            active["current_step"] = max(self.STEPS)
            active["status"] = "completed"
            active["completed_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            self._write_json(self.active_file, active)
            return "completed"

        active["current_step"] = next_value
        self._write_json(self.active_file, active)
        return next_value

    def get_current_step(self) -> dict | None:
        active = self._read_json(self.active_file, {})
        if not isinstance(active, dict) or not active:
            return None
        step = int(active.get("current_step", 1) or 1)
        return {
            "step": step,
            "name": self.STEP_NAMES.get(step, "Unknown"),
            "duration_seconds": int(self.STEP_DURATIONS.get(step, 0)),
        }

    def complete(self) -> dict | None:
        active = self._read_json(self.active_file, {})
        if not isinstance(active, dict) or not active:
            return None

        active["status"] = "completed"
        active["completed_at"] = datetime.datetime.now().isoformat(timespec="seconds")

        history = self._read_json(self.history_file, [])
        if not isinstance(history, list):
            history = []
        history.append(active)
        self._write_json(self.history_file, history)

        if os.path.exists(self.active_file):
            try:
                os.remove(self.active_file)
            except OSError:
                self._write_json(self.active_file, {})
        return active

    def get_history(self, user_id: str) -> list[dict]:
        history = self._read_json(self.history_file, [])
        if not isinstance(history, list):
            return []
        return [
            item
            for item in history
            if isinstance(item, dict) and str(item.get("user_id", "")) == str(user_id)
        ]

    def is_active(self) -> bool:
        active = self._read_json(self.active_file, {})
        if not isinstance(active, dict) or not active:
            return False
        return str(active.get("status", "")) == "active"
