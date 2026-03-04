from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from Storage.io import atomic_write_json, locked_read_json
from automations.base import Automation
from core.types import Effect
from time_utils import ensure_utc, from_iso, to_iso, utcnow


class AutomationRegistry:
    """Registry and runner for effect-based automations with persisted run state."""

    def __init__(self, state_path: Path):
        self._state_path = Path(state_path)
        self._automations: list[Automation] = []
        self._state = self._load_state()

    def register(self, automation: Automation) -> None:
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

        emitted: list[Effect] = []
        state_changed = False
        for automation in self._automations:
            if not automation.enabled:
                continue

            record = self._state.setdefault("automations", {}).setdefault(
                automation.name,
                {"last_ran_utc": "", "last_window_key": ""},
            )

            last_ran = self._parse_optional_utc(record.get("last_ran_utc", ""))
            if last_ran is not None:
                cooldown = max(0, int(automation.cooldown_minutes))
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

            if isinstance(effects, list):
                emitted.extend(effect for effect in effects if isinstance(effect, Effect))

            record["last_ran_utc"] = to_iso(now_utc)
            if current_window_key:
                record["last_window_key"] = current_window_key
            state_changed = True

        if state_changed:
            self._save_state()
        return emitted

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
