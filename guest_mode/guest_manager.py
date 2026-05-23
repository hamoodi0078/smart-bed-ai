from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

from config import RUNTIME_DATA_DIR


class GuestModeManager:
    def __init__(self):
        self.state_file = str(RUNTIME_DATA_DIR / "guest_state.json")

    def _default_state(self) -> dict:
        return {
            "active": False,
            "activated_at": "",
            "activated_by": "",
            "auto_reset_at": "",
            "guest_number": 0,
            "deactivated_at": "",
        }

    def _read_state(self) -> dict:
        if not os.path.exists(self.state_file):
            return self._default_state()
        try:
            with open(self.state_file, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        merged = self._default_state()
        merged.update(payload)
        return merged

    def _write_state(self, state: dict) -> None:
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)

    def get_next_6am(self) -> datetime.datetime:
        now = datetime.datetime.now()
        next_six = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now >= next_six:
            next_six = next_six + datetime.timedelta(days=1)
        return next_six

    def activate(self, activated_by: str = "user") -> dict:
        state = self._read_state()
        guest_number = int(state.get("guest_number", 0) or 0) + 1
        now = datetime.datetime.now()
        next_6am = self.get_next_6am()
        new_state = {
            "active": True,
            "activated_at": now.isoformat(timespec="seconds"),
            "activated_by": str(activated_by or "user"),
            "auto_reset_at": next_6am.isoformat(timespec="seconds"),
            "guest_number": guest_number,
            "deactivated_at": "",
        }
        self._write_state(new_state)
        return new_state

    def deactivate(self) -> dict:
        state = self._read_state()
        state["active"] = False
        state["deactivated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        self._write_state(state)
        return state

    def is_active(self) -> bool:
        state = self._read_state()
        if not bool(state.get("active", False)):
            return False
        auto_reset_raw = str(state.get("auto_reset_at", "")).strip()
        if not auto_reset_raw:
            return bool(state.get("active", False))
        try:
            auto_reset_at = datetime.datetime.fromisoformat(auto_reset_raw)
        except ValueError:
            return False
        return datetime.datetime.now() < auto_reset_at

    def should_auto_reset(self) -> bool:
        state = self._read_state()
        auto_reset_raw = str(state.get("auto_reset_at", "")).strip()
        if not auto_reset_raw:
            return False
        try:
            auto_reset_at = datetime.datetime.fromisoformat(auto_reset_raw)
        except ValueError:
            return False
        return bool(state.get("active", False)) and (datetime.datetime.now() >= auto_reset_at)

    def auto_reset(self) -> bool:
        if not self.should_auto_reset():
            return False
        self.deactivate()
        return True

    def get_status(self) -> dict:
        state = self._read_state()
        state["active"] = self.is_active()
        return state
