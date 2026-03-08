from __future__ import annotations

import time
from datetime import datetime, timezone
import logging
from pathlib import Path
from threading import RLock
from typing import Callable, TypeVar

from Storage.io import atomic_write_json, locked_read_json
from core.structured_logging import emit_json_log


STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"

T = TypeVar("T")
_LOG = logging.getLogger("voice.circuit_breaker")


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_voice_circuit_reset_signal(path: str | Path) -> dict:
    try:
        payload = locked_read_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_voice_circuit_reset_signal(path: str | Path, source: str = "manual") -> dict:
    payload = {
        "token": str(time.time_ns()),
        "requested_at": _utc_iso_now(),
        "source": str(source or "manual").strip() or "manual",
    }
    atomic_write_json(path, payload)
    return payload


class VoiceCircuitBreaker:
    """
    Small in-memory circuit-breaker for the voice pipeline with optional external reset signal.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        backoff_base_seconds: float = 2.0,
        backoff_max_seconds: float = 60.0,
        reset_signal_path: str | Path | None = None,
        time_fn: Callable[[], float] | None = None,
    ):
        self.failure_threshold = max(1, int(failure_threshold))
        self.backoff_base_seconds = max(0.1, float(backoff_base_seconds))
        self.backoff_max_seconds = max(self.backoff_base_seconds, float(backoff_max_seconds))
        self.reset_signal_path = Path(reset_signal_path).expanduser() if reset_signal_path else None
        self._time_fn = time_fn or time.time

        self._lock = RLock()
        self._state = STATE_CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._next_retry_time: float | None = None
        self._last_reset_signal_token = ""
        self._trace_id = "voice_runtime"

    def _log_event(self, *, level: str, event_type: str, metadata: dict | None = None) -> None:
        emit_json_log(
            _LOG,
            level=level,
            event_type=event_type,
            trace_id=self._trace_id,
            metadata=metadata or {},
        )

    def _snapshot_unlocked(self, now: float | None = None) -> dict:
        timestamp_now = float(self._time_fn() if now is None else now)
        retry_time = self._next_retry_time
        cooldown_remaining = 0.0
        if isinstance(retry_time, (int, float)):
            cooldown_remaining = max(0.0, float(retry_time) - timestamp_now)

        return {
            "state": self._state,
            "failure_count": int(self._failure_count),
            "failure_threshold": int(self.failure_threshold),
            "last_failure_time": self._last_failure_time,
            "next_retry_time": retry_time,
            "cooldown_seconds_remaining": cooldown_remaining,
            "backoff_base_seconds": float(self.backoff_base_seconds),
            "backoff_max_seconds": float(self.backoff_max_seconds),
        }

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_unlocked()

    def before_call(self) -> tuple[bool, str]:
        with self._lock:
            now = float(self._time_fn())
            if self._state == STATE_OPEN:
                if isinstance(self._next_retry_time, (int, float)) and now >= float(self._next_retry_time):
                    previous_state = self._state
                    self._state = STATE_HALF_OPEN
                    self._log_event(
                        level="info",
                        event_type="voice_circuit_state_change",
                        metadata={
                            "from_state": previous_state,
                            "to_state": self._state,
                            "reason": "cooldown_elapsed",
                            "failure_count": int(self._failure_count),
                        },
                    )
                    return True, STATE_HALF_OPEN
                return False, STATE_OPEN
            return True, self._state

    def record_success(self) -> dict:
        with self._lock:
            previous_state = self._state
            previous_failures = int(self._failure_count)
            self._state = STATE_CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._next_retry_time = None
            snapshot = self._snapshot_unlocked()
            if previous_state != STATE_CLOSED or previous_failures > 0:
                self._log_event(
                    level="info",
                    event_type="voice_circuit_state_change",
                    metadata={
                        "from_state": previous_state,
                        "to_state": STATE_CLOSED,
                        "reason": "record_success",
                        "failure_count": 0,
                    },
                )
            return snapshot

    def record_failure(self) -> dict:
        with self._lock:
            now = float(self._time_fn())
            previous_state = self._state
            self._failure_count += 1
            self._last_failure_time = now

            if self._failure_count >= self.failure_threshold:
                exponent = max(0, self._failure_count - self.failure_threshold)
                backoff = min(self.backoff_max_seconds, self.backoff_base_seconds * (2**exponent))
                self._state = STATE_OPEN
                self._next_retry_time = now + float(backoff)
            else:
                self._state = STATE_CLOSED
                self._next_retry_time = None

            snapshot = self._snapshot_unlocked(now=now)
            self._log_event(
                level="warning",
                event_type="voice_circuit_failure",
                metadata={
                    "state": self._state,
                    "failure_count": int(self._failure_count),
                    "failure_threshold": int(self.failure_threshold),
                    "cooldown_seconds_remaining": float(snapshot.get("cooldown_seconds_remaining", 0.0) or 0.0),
                },
            )
            if previous_state != self._state:
                self._log_event(
                    level="warning",
                    event_type="voice_circuit_state_change",
                    metadata={
                        "from_state": previous_state,
                        "to_state": self._state,
                        "reason": "record_failure",
                        "failure_count": int(self._failure_count),
                    },
                )
            return snapshot

    def manual_reset(self, reason: str = "manual") -> dict:
        reason_text = str(reason or "manual").strip() or "manual"
        with self._lock:
            previous_state = self._state
            self._state = STATE_CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._next_retry_time = None
            snapshot = self._snapshot_unlocked()
            self._log_event(
                level="info",
                event_type="voice_circuit_state_change",
                metadata={
                    "from_state": previous_state,
                    "to_state": STATE_CLOSED,
                    "reason": reason_text,
                    "failure_count": 0,
                },
            )
            return snapshot

    def consume_manual_reset_signal(self) -> bool:
        signal_path = self.reset_signal_path
        if signal_path is None:
            return False

        payload = read_voice_circuit_reset_signal(signal_path)
        token = str(payload.get("token", "") or "").strip()
        if not token:
            return False

        with self._lock:
            if token == self._last_reset_signal_token:
                return False
            self._last_reset_signal_token = token

        self.manual_reset(reason=str(payload.get("source", "external") or "external"))
        return True

    def run(
        self,
        *,
        operation: Callable[[], T],
        fallback: Callable[[str], T],
        on_failure: Callable[[Exception], None] | None = None,
    ) -> tuple[T, bool, str, dict]:
        allowed, gate_state = self.before_call()
        if not allowed:
            return fallback("circuit_open"), True, "circuit_open", self.snapshot()

        try:
            value = operation()
        except Exception as exc:
            if callable(on_failure):
                try:
                    on_failure(exc)
                except Exception:
                    pass
            snapshot = self.record_failure()
            return fallback("operation_failure"), True, "operation_failure", snapshot

        snapshot = self.record_success()
        return value, False, gate_state, snapshot
