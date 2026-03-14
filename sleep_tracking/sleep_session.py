from __future__ import annotations

import datetime
import json
import os
import uuid


class SleepSession:
    def __init__(self):
        base_dir = os.path.dirname(__file__)
        self.active_file = os.path.join(base_dir, "active_session.json")
        self.log_file = os.path.join(base_dir, "sessions_log.json")

    @staticmethod
    def calculate_duration(start: str, end: str) -> float:
        start_dt = datetime.datetime.fromisoformat(str(start))
        end_dt = datetime.datetime.fromisoformat(str(end))
        hours = (end_dt - start_dt).total_seconds() / 3600.0
        return round(hours, 2)

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

    def start_session(self, user_id: str) -> dict:
        session = {
            "session_id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "sleep_start": datetime.datetime.now().isoformat(timespec="seconds"),
            "status": "sleeping",
        }
        self._write_json(self.active_file, session)
        return session

    def end_session(self, quality_rating: int = None) -> dict | None:
        active = self.get_active_session()
        if active is None:
            return None

        sleep_end = datetime.datetime.now().isoformat(timespec="seconds")
        sleep_start = str(active.get("sleep_start", ""))
        total_hours = self.calculate_duration(sleep_start, sleep_end)

        completed = dict(active)
        completed["sleep_end"] = sleep_end
        completed["total_hours"] = total_hours
        completed["status"] = "completed"
        completed["quality_rating"] = int(quality_rating) if quality_rating is not None else None

        log = self._read_json(self.log_file, [])
        if not isinstance(log, list):
            log = []
        log.append(completed)
        self._write_json(self.log_file, log)

        if os.path.exists(self.active_file):
            try:
                os.remove(self.active_file)
            except OSError:
                self._write_json(self.active_file, {})

        return completed

    def get_active_session(self) -> dict | None:
        payload = self._read_json(self.active_file, None)
        if not isinstance(payload, dict) or not payload:
            return None
        if payload.get("status") != "sleeping":
            return None
        return payload

    def get_session_history(self, user_id: str, limit: int = 30) -> list[dict]:
        log = self._read_json(self.log_file, [])
        if not isinstance(log, list):
            return []
        filtered = [
            item for item in log
            if isinstance(item, dict) and str(item.get("user_id")) == str(user_id)
        ]
        safe_limit = max(1, int(limit))
        return filtered[-safe_limit:]
