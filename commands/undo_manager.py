from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from threading import RLock
from typing import Any

from time_utils import from_iso, to_iso, utcnow

DEFAULT_UNDO_WINDOW_SECONDS = 10


class UndoManager:
    def __init__(self, window_seconds: int = DEFAULT_UNDO_WINDOW_SECONDS):
        try:
            parsed_window = int(window_seconds)
        except Exception:
            parsed_window = DEFAULT_UNDO_WINDOW_SECONDS
        self._window_seconds = max(1, parsed_window)
        self._actions: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    @staticmethod
    def _normalize_user_id(user_id: str) -> str:
        return str(user_id or "").strip()

    @staticmethod
    def _is_expired(action: dict[str, Any], now_utc=None) -> bool:
        expires_at_raw = str(action.get("expires_at", "") or "").strip()
        if not expires_at_raw:
            return True
        try:
            expires_at = from_iso(expires_at_raw)
        except Exception:
            return True
        now = now_utc if now_utc is not None else utcnow()
        return now >= expires_at

    def record_action(
        self, user_id: str, action_type: str, previous_state: Any, new_state: Any
    ) -> None:
        key = self._normalize_user_id(user_id)
        if not key:
            return
        now_utc = utcnow().replace(microsecond=0)
        expires_at = now_utc + timedelta(seconds=self._window_seconds)
        with self._lock:
            self._actions[key] = {
                "action_type": str(action_type or "").strip(),
                "previous_state": deepcopy(previous_state),
                "new_state": deepcopy(new_state),
                "timestamp": to_iso(now_utc),
                "expires_at": to_iso(expires_at),
            }

    def get_undoable_action(self, user_id: str) -> dict[str, Any] | None:
        key = self._normalize_user_id(user_id)
        if not key:
            return None
        now_utc = utcnow()
        with self._lock:
            action = self._actions.get(key)
            if not isinstance(action, dict):
                return None
            if self._is_expired(action, now_utc=now_utc):
                self._actions.pop(key, None)
                return None
            return deepcopy(action)

    def pop_undo(self, user_id: str) -> dict[str, Any] | None:
        key = self._normalize_user_id(user_id)
        if not key:
            return None
        with self._lock:
            action = self._actions.get(key)
            if not isinstance(action, dict):
                return None
            if self._is_expired(action):
                self._actions.pop(key, None)
                return None
            return deepcopy(self._actions.pop(key))
