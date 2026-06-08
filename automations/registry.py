from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import math
import logging
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from Storage.io import atomic_write_json, confine_path, locked_read_json
from automations.base import (
    AUTOMATION_CRITICALITY_CRITICAL,
    Automation,
    normalize_automation_criticality,
    normalize_cooldown_minutes,
)
from automations.idempotency import IdempotencyStore, make_fingerprint
from config import RUNTIME_DATA_DIR
from core.structured_logging import emit_json_log
from core.types import Effect
from time_utils import ensure_utc, from_iso, to_iso, utcnow

DEFAULT_QUIET_HOURS_WINDOW = "22:00-07:00"
AUTOMATION_IDEMPOTENCY_WINDOW_SECONDS = 60
_LOG = logging.getLogger("automations.registry")


def _minutes(dt: datetime) -> float:
    return (dt.hour * 60.0) + dt.minute + (dt.second / 60.0) + (dt.microsecond / 60000000.0)


def _parse_hhmm(value: str, fallback: tuple[int, int]) -> tuple[int, int]:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return fallback
    try:
        h_str, m_str = text.split(":", 1)
        h = max(0, min(23, int(h_str)))
        m = max(0, min(59, int(m_str)))
        return h, m
    except Exception:
        return fallback


def _quiet_window_bounds(quiet_window: str) -> tuple[tuple[int, int], tuple[int, int]]:
    raw = str(quiet_window or "").strip()
    if "-" not in raw:
        raw = DEFAULT_QUIET_HOURS_WINDOW
    left, right = [part.strip() for part in raw.split("-", 1)]
    start = _parse_hhmm(left, (22, 0))
    end = _parse_hhmm(right, (7, 0))
    return start, end


def is_in_quiet_hours(
    *,
    now_local: datetime,
    quiet_window: str,
    quiet_mode_active: bool = False,
) -> bool:
    if quiet_mode_active:
        return True
    (start_h, start_m), (end_h, end_m) = _quiet_window_bounds(quiet_window)
    current = _minutes(now_local)
    start = (start_h * 60.0) + start_m
    end = (end_h * 60.0) + end_m
    if start <= end:
        return start <= current < end
    return (current >= start) or (current < end)


def is_quiet_hours_override_active(*, now_utc: datetime, override_until_utc: str) -> bool:
    text = str(override_until_utc or "").strip()
    if not text:
        return False
    try:
        override_until = from_iso(text)
    except Exception:
        return False
    return ensure_utc(now_utc) < ensure_utc(override_until)


class AutomationRegistry:
    """Registry and runner for effect-based automations with persisted run state."""

    def __init__(self, state_path: Path):
        self._state_path = self._confine_state_path(state_path)
        self._automations: list[Automation] = []
        self._state = self._load_state()
        self._idempotency_store = IdempotencyStore(path=self._state_path.with_name("idempotency_store.json"))

    @staticmethod
    def _confine_state_path(candidate: str | Path) -> Path:
        """Resolve *candidate* and verify it stays inside RUNTIME_DATA_DIR.

        Prevents path-traversal when state_path originates from config or
        constructor arguments (addresses SonarCloud python:S5144).
        """
        return confine_path(RUNTIME_DATA_DIR, candidate)


    def register(self, automation: Automation) -> None:
        normalized_cooldown = normalize_cooldown_minutes(automation.cooldown_minutes)
        normalized_criticality = normalize_automation_criticality(automation.criticality)
        try:
            original_cooldown = int(automation.cooldown_minutes)
        except Exception:
            original_cooldown = None
        if (
            (original_cooldown is None)
            or (normalized_cooldown != original_cooldown)
            or (normalized_criticality != str(automation.criticality or "").strip().lower())
        ):
            automation = replace(
                automation,
                cooldown_minutes=normalized_cooldown,
                criticality=normalized_criticality,
            )
        self._automations = [item for item in self._automations if item.name != automation.name]
        self._automations.append(automation)

    def list(self) -> list[Automation]:
        return list(self._automations)

    def run_automations(self, ctx: dict[str, Any]) -> list[Effect]:
        now_utc = ensure_utc(ctx.get("now_utc") if isinstance(ctx.get("now_utc"), datetime) else utcnow())
        timezone_name = str(ctx.get("timezone", "UTC") or "UTC").strip() or "UTC"
        try:
            now_local = now_utc.astimezone(ZoneInfo(timezone_name))
        except Exception:
            timezone_name = "UTC"
            now_local = now_utc

        run_ctx = dict(ctx)
        run_ctx["now_utc"] = now_utc
        run_ctx["now_local"] = now_local
        run_ctx["timezone"] = timezone_name
        quiet_window = str(run_ctx.get("quiet_window", DEFAULT_QUIET_HOURS_WINDOW) or DEFAULT_QUIET_HOURS_WINDOW).strip()
        quiet_mode_active = bool(run_ctx.get("quiet_mode_active", False))
        override_active = is_quiet_hours_override_active(
            now_utc=now_utc,
            override_until_utc=str(run_ctx.get("quiet_hours_override_until_utc", "") or ""),
        )
        quiet_active_now = is_in_quiet_hours(
            now_local=now_local,
            quiet_window=quiet_window,
            quiet_mode_active=quiet_mode_active,
        ) and (not override_active)
        run_ctx["quiet_window"] = quiet_window
        run_ctx["quiet_hours_active"] = quiet_active_now
        run_ctx["quiet_hours_override_active"] = override_active
        trace_id = str(run_ctx.get("trace_id", "automation_runtime") or "automation_runtime")

        if quiet_active_now or override_active:
            emit_json_log(
                _LOG,
                level="info",
                event_type="quiet_hours_decision",
                trace_id=trace_id,
                metadata={
                    "quiet_window": quiet_window,
                    "quiet_active": quiet_active_now,
                    "override_active": override_active,
                    "timezone": timezone_name,
                },
            )

        emitted: list[Effect] = []
        state_changed = False
        for automation in self._automations:
            if not automation.enabled:
                continue

            criticality = normalize_automation_criticality(automation.criticality)
            if quiet_active_now and criticality != AUTOMATION_CRITICALITY_CRITICAL:
                emit_json_log(
                    _LOG,
                    level="info",
                    event_type="automation_blocked_quiet_hours",
                    trace_id=trace_id,
                    metadata={
                        "automation": automation.name,
                        "criticality": criticality,
                        "quiet_window": quiet_window,
                    },
                )
                continue

            record = self._state.setdefault("automations", {}).setdefault(
                automation.name,
                {"last_ran_utc": "", "last_window_key": ""},
            )

            last_ran = self._parse_optional_utc(record.get("last_ran_utc", ""))
            if automation.cron_expr:
                from core.cron_utils import should_fire_now
                if not should_fire_now(automation.cron_expr, now=now_utc, tolerance_seconds=60):
                    continue
            elif last_ran is not None:
                cooldown = normalize_cooldown_minutes(automation.cooldown_minutes)
                if now_utc - last_ran < timedelta(minutes=cooldown):
                    continue

            current_window_key = ""
            if callable(automation.window_key):
                resolved = automation.window_key(run_ctx)
                current_window_key = str(resolved or "")
                if current_window_key and current_window_key == str(record.get("last_window_key", "") or ""):
                    continue

            try:
                should_fire = bool(automation.trigger(run_ctx))
            except Exception:
                continue
            if not should_fire:
                continue

            try:
                effects = automation.action(run_ctx)
            except Exception:
                continue

            valid_effects = []
            if isinstance(effects, list):
                for effect in effects:
                    if not isinstance(effect, Effect):
                        continue

                    action_type = str(effect.kind or "").strip().lower() or "effect"
                    fingerprint = make_fingerprint(
                        automation_id=automation.name,
                        action_type=action_type,
                        ts=now_utc,
                    )
                    if self._idempotency_store.is_duplicate(
                        fingerprint=fingerprint,
                        window_seconds=AUTOMATION_IDEMPOTENCY_WINDOW_SECONDS,
                    ):
                        emit_json_log(
                            _LOG,
                            level="info",
                            event_type="automation_dedup_blocked",
                            trace_id=trace_id,
                            metadata={
                                "automation_id": automation.name,
                                "fingerprint": fingerprint,
                                "window_seconds": AUTOMATION_IDEMPOTENCY_WINDOW_SECONDS,
                            },
                        )
                        continue

                    self._idempotency_store.record(
                        fingerprint=fingerprint,
                        window_seconds=AUTOMATION_IDEMPOTENCY_WINDOW_SECONDS,
                    )
                    emit_json_log(
                        _LOG,
                        level="info",
                        event_type="idempotency_record_saved",
                        trace_id=trace_id,
                        metadata={
                            "fingerprint": fingerprint,
                            "expires_at": self._idempotency_store.last_recorded_expires_at,
                        },
                    )
                    valid_effects.append(effect)
                emitted.extend(valid_effects)

            emit_json_log(
                _LOG,
                level="info",
                event_type="automation_triggered",
                trace_id=trace_id,
                metadata={
                    "automation": automation.name,
                    "criticality": criticality,
                    "effects_count": len(valid_effects),
                    "quiet_hours_active": quiet_active_now,
                },
            )

            record["last_ran_utc"] = to_iso(now_utc)
            if current_window_key:
                record["last_window_key"] = current_window_key
            state_changed = True

        if state_changed:
            self._save_state()
        return emitted

    def cooldown_status(self, now_utc: datetime | None = None) -> list[dict[str, Any]]:
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        rows: list[dict[str, Any]] = []
        for automation in self._automations:
            record = self._state.setdefault("automations", {}).setdefault(
                automation.name,
                {"last_ran_utc": "", "last_window_key": ""},
            )
            cooldown = normalize_cooldown_minutes(automation.cooldown_minutes)
            last_ran = self._parse_optional_utc(record.get("last_ran_utc", ""))

            next_run_utc = ""
            next_run_in_minutes = 0
            if automation.cron_expr:
                from core.cron_utils import next_fire, should_fire_now
                nf = next_fire(automation.cron_expr, now=now)
                if nf:
                    next_run_utc = to_iso(nf)
                    seconds_remaining = max(0.0, (nf - now).total_seconds())
                    next_run_in_minutes = int(math.ceil(seconds_remaining / 60.0))
            elif isinstance(last_ran, datetime):
                next_run_at = ensure_utc(last_ran) + timedelta(minutes=cooldown)
                next_run_utc = to_iso(next_run_at)
                seconds_remaining = max(0.0, (next_run_at - now).total_seconds())
                next_run_in_minutes = int(math.ceil(seconds_remaining / 60.0))

            rows.append(
                {
                    "name": automation.name,
                    "cron_expr": automation.cron_expr or "",
                    "cooldown_minutes": cooldown,
                    "criticality": normalize_automation_criticality(automation.criticality),
                    "last_ran_utc": to_iso(last_ran) if isinstance(last_ran, datetime) else "",
                    "next_run_utc": next_run_utc,
                    "next_run_in_minutes": next_run_in_minutes,
                    "available_now": next_run_in_minutes <= 0,
                }
            )
        return rows

    def _parse_optional_utc(self, raw: Any) -> datetime | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            return from_iso(text)
        except Exception:
            return None

    def _load_state(self) -> dict[str, Any]:
        data = locked_read_json(self._state_path)
        if not isinstance(data, dict):
            data = {}
        automations = data.get("automations")
        if not isinstance(automations, dict):
            automations = {}
        return {"version": 1, "automations": automations}

    def _save_state(self) -> None:
        atomic_write_json(self._state_path, self._state)
