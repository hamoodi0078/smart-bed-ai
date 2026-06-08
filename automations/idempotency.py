from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from pathlib import Path

from Storage.io import atomic_write_json, confine_path, locked_read_json
from config import RUNTIME_DATA_DIR
from time_utils import ensure_utc, from_iso, to_iso, utcnow

IDEMPOTENCY_STORE_PATH = Path("data") / "idempotency_store.json"
IDEMPOTENCY_STORE_VERSION = 1
DEFAULT_WINDOW_SECONDS = 60


def _normalize_window_seconds(value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = DEFAULT_WINDOW_SECONDS
    return max(0, parsed)


def make_fingerprint(automation_id: str, action_type: str, ts: datetime) -> str:
    minute_bucket = ensure_utc(ts).strftime("%Y%m%d%H%M")
    raw = f"{automation_id}:{action_type}:{minute_bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class IdempotencyStore:
    def __init__(self, path: str | Path = IDEMPOTENCY_STORE_PATH):
        self._path = confine_path(RUNTIME_DATA_DIR, path)
        self._last_recorded_expires_at = ""

    @property
    def last_recorded_expires_at(self) -> str:
        return self._last_recorded_expires_at

    def is_duplicate(self, fingerprint: str, window_seconds: int = DEFAULT_WINDOW_SECONDS) -> bool:
        key = self._normalize_fingerprint(fingerprint)
        if not key:
            return False

        data = self._load_state()
        now_utc = utcnow()
        entries = data["fingerprints"]
        state_changed = self._cleanup_entries(entries, now_utc)

        expires_at = self._parse_expiry(entries.get(key, ""))
        if isinstance(expires_at, datetime) and ensure_utc(now_utc) < ensure_utc(expires_at):
            if state_changed:
                self._save_state(data)
            return True

        expires_at_text = self._compute_expiry_iso(now_utc, window_seconds)
        entries[key] = expires_at_text
        self._last_recorded_expires_at = expires_at_text
        self._save_state(data)
        return False

    def record(self, fingerprint: str, window_seconds: int = DEFAULT_WINDOW_SECONDS) -> None:
        key = self._normalize_fingerprint(fingerprint)
        if not key:
            return

        data = self._load_state()
        now_utc = utcnow()
        entries = data["fingerprints"]
        self._cleanup_entries(entries, now_utc)

        expires_at_text = self._compute_expiry_iso(now_utc, window_seconds)
        entries[key] = expires_at_text
        self._last_recorded_expires_at = expires_at_text
        self._save_state(data)

    def cleanup_expired(self) -> None:
        data = self._load_state()
        entries = data["fingerprints"]
        if self._cleanup_entries(entries, utcnow()):
            self._save_state(data)

    @staticmethod
    def _normalize_fingerprint(fingerprint: str) -> str:
        return str(fingerprint or "").strip()

    @staticmethod
    def _parse_expiry(value: str) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return from_iso(text)
        except Exception:
            return None

    def _compute_expiry_iso(self, now_utc: datetime, window_seconds: int) -> str:
        window = _normalize_window_seconds(window_seconds)
        expires_at = ensure_utc(now_utc) + timedelta(seconds=window)
        return to_iso(expires_at.replace(microsecond=0))

    def _cleanup_entries(self, entries: dict[str, str], now_utc: datetime) -> bool:
        now = ensure_utc(now_utc)
        changed = False
        for key in list(entries.keys()):
            expires_at = self._parse_expiry(entries.get(key, ""))
            if (expires_at is None) or (ensure_utc(expires_at) <= now):
                entries.pop(key, None)
                changed = True
        return changed

    def _load_state(self) -> dict[str, object]:
        loaded = locked_read_json(self._path)
        if not isinstance(loaded, dict):
            loaded = {}

        raw_entries = loaded.get("fingerprints", {})
        entries: dict[str, str] = {}
        if isinstance(raw_entries, dict):
            for key, value in raw_entries.items():
                fingerprint = self._normalize_fingerprint(str(key))
                expires_at = str(value or "").strip()
                if fingerprint and expires_at:
                    entries[fingerprint] = expires_at

        return {
            "version": IDEMPOTENCY_STORE_VERSION,
            "fingerprints": entries,
        }

    def _save_state(self, data: dict[str, object]) -> None:
        atomic_write_json(self._path, data)
