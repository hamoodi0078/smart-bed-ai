import unittest
from datetime import datetime, timedelta, timezone
import json
import shutil
from pathlib import Path
from uuid import uuid4

from automations.base import (
    AUTOMATION_CRITICALITY_CRITICAL,
    AUTOMATION_CRITICALITY_NON_CRITICAL,
    Automation,
)
from automations.defaults import build_default_automations
from automations.registry import AutomationRegistry, is_in_quiet_hours
from core.types import Effect


def _workspace_tmp_dir() -> Path:
    root = Path("runtime_data") / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"automation_registry_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ctx(
    *,
    now_utc: datetime,
    timezone_name: str = "UTC",
    sleep_mode_active: bool = False,
    quiet_mode_active: bool = False,
    quiet_window: str = "",
    quiet_hours_override_until_utc: str = "",
    has_pending_work_planning_reminder_today: bool = False,
    fajr_light_time: str = "04:50",
) -> dict[str, object]:
    return {
        "now_utc": now_utc,
        "timezone": timezone_name,
        "sleep_mode_active": sleep_mode_active,
        "quiet_mode_active": quiet_mode_active,
        "quiet_window": quiet_window,
        "quiet_hours_override_until_utc": quiet_hours_override_until_utc,
        "has_pending_work_planning_reminder_today": has_pending_work_planning_reminder_today,
        "fajr_light_time": fajr_light_time,
    }


class TestAutomationRegistry(unittest.TestCase):
    def test_cooldown_blocks_repeated_runs(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            state_path = tmp_dir / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            registry.register(
                Automation(
                    name="cooldown_test",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "x"})],
                    cooldown_minutes=60,
                )
            )

            first = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)))
            second = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 12, 10, tzinfo=timezone.utc)))

            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_once_per_window_runs_only_once(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            state_path = tmp_dir / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            registry.register(
                Automation(
                    name="window_once",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "w"})],
                    cooldown_minutes=60,
                    window_key=lambda ctx: "2026-03-05:window",
                )
            )

            first = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)))
            second = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 12, 1, tzinfo=timezone.utc)))

            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_persistence_resumes_after_restart(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            state_path = tmp_dir / "automations_state.json"

            first_registry = AutomationRegistry(state_path=state_path)
            first_registry.register(
                Automation(
                    name="persisted",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "p"})],
                    cooldown_minutes=120,
                )
            )

            t0 = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)
            t1 = t0 + timedelta(minutes=30)

            first_effects = first_registry.run_automations(_ctx(now_utc=t0))
            self.assertEqual(len(first_effects), 1)

            second_registry = AutomationRegistry(state_path=state_path)
            second_registry.register(
                Automation(
                    name="persisted",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "p"})],
                    cooldown_minutes=120,
                )
            )
            second_effects = second_registry.run_automations(_ctx(now_utc=t1))
            self.assertEqual(second_effects, [])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_cooldown_expires_correctly(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            state_path = tmp_dir / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            registry.register(
                Automation(
                    name="cooldown_expiry",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "ok"})],
                    cooldown_minutes=60,
                )
            )

            t0 = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)
            t1 = t0 + timedelta(minutes=61)
            first = registry.run_automations(_ctx(now_utc=t0))
            second = registry.run_automations(_ctx(now_utc=t1))

            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_invalid_cooldown_values_are_normalized(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            state_path = tmp_dir / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            registry.register(
                Automation(
                    name="too_low",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "low"})],
                    cooldown_minutes=5,
                )
            )
            registry.register(
                Automation(
                    name="too_high",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "high"})],
                    cooldown_minutes=5000,
                )
            )

            rows = {automation.name: automation for automation in registry.list()}
            self.assertEqual(rows["too_low"].cooldown_minutes, 60)
            self.assertEqual(rows["too_high"].cooldown_minutes, 1440)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_last_run_timestamp_persists_in_state(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            state_path = tmp_dir / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            registry.register(
                Automation(
                    name="persist_timestamp",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "ok"})],
                    cooldown_minutes=120,
                )
            )

            now = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)
            registry.run_automations(_ctx(now_utc=now))

            payload = json.loads(state_path.read_text(encoding="utf-8"))
            last_ran = str(
                payload.get("automations", {}).get("persist_timestamp", {}).get("last_ran_utc", "")
            ).strip()
            self.assertTrue(last_ran)
            parsed = datetime.fromisoformat(last_ran.replace("Z", "+00:00"))
            self.assertIsNotNone(parsed.tzinfo)
            self.assertEqual(parsed.utcoffset().total_seconds(), 0.0)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_non_critical_automation_blocked_during_quiet_hours(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            registry = AutomationRegistry(state_path=tmp_dir / "automations_state.json")
            registry.register(
                Automation(
                    name="night_nudge",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "nudge"})],
                    criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
                )
            )
            effects = registry.run_automations(
                _ctx(
                    now_utc=datetime(2026, 3, 5, 23, 30, tzinfo=timezone.utc),
                    timezone_name="UTC",
                    quiet_window="22:00-07:00",
                )
            )
            self.assertEqual(effects, [])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_critical_automation_allowed_during_quiet_hours(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            registry = AutomationRegistry(state_path=tmp_dir / "automations_state.json")
            registry.register(
                Automation(
                    name="critical_wake",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "wake"})],
                    criticality=AUTOMATION_CRITICALITY_CRITICAL,
                )
            )
            effects = registry.run_automations(
                _ctx(
                    now_utc=datetime(2026, 3, 5, 23, 30, tzinfo=timezone.utc),
                    timezone_name="UTC",
                    quiet_window="22:00-07:00",
                )
            )
            self.assertEqual(len(effects), 1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_quiet_hours_override_allows_non_critical_automation(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            registry = AutomationRegistry(state_path=tmp_dir / "automations_state.json")
            registry.register(
                Automation(
                    name="night_nudge_override",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "nudge"})],
                    criticality=AUTOMATION_CRITICALITY_NON_CRITICAL,
                )
            )
            now = datetime(2026, 3, 5, 23, 30, tzinfo=timezone.utc)
            effects = registry.run_automations(
                _ctx(
                    now_utc=now,
                    timezone_name="UTC",
                    quiet_window="22:00-07:00",
                    quiet_hours_override_until_utc=(now + timedelta(minutes=45)).isoformat(),
                )
            )
            self.assertEqual(len(effects), 1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_quiet_hours_window_boundaries(self):
        self.assertFalse(
            is_in_quiet_hours(
                now_local=datetime(2026, 3, 5, 21, 59, tzinfo=timezone.utc),
                quiet_window="22:00-07:00",
            )
        )
        self.assertTrue(
            is_in_quiet_hours(
                now_local=datetime(2026, 3, 5, 22, 0, tzinfo=timezone.utc),
                quiet_window="22:00-07:00",
            )
        )
        self.assertTrue(
            is_in_quiet_hours(
                now_local=datetime(2026, 3, 6, 6, 59, tzinfo=timezone.utc),
                quiet_window="22:00-07:00",
            )
        )
        self.assertFalse(
            is_in_quiet_hours(
                now_local=datetime(2026, 3, 6, 7, 0, tzinfo=timezone.utc),
                quiet_window="22:00-07:00",
            )
        )


class TestDefaultAutomations(unittest.TestCase):
    def _run_defaults(self, ctx: dict[str, object]) -> list[object]:
        tmp_dir = _workspace_tmp_dir()
        try:
            state_path = tmp_dir / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            for automation in build_default_automations():
                registry.register(automation)
            return registry.run_automations(ctx)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_quiet_mode_suppresses_sleep_suggestion(self):
        effects = self._run_defaults(
            _ctx(
                now_utc=datetime(2026, 3, 5, 23, 30, tzinfo=timezone.utc),
                timezone_name="UTC",
                sleep_mode_active=False,
                quiet_mode_active=True,
            )
        )
        self.assertEqual(effects, [])

    def test_morning_wake_requires_sleep_mode(self):
        effects = self._run_defaults(
            _ctx(
                now_utc=datetime(2026, 3, 5, 6, 15, tzinfo=timezone.utc),
                timezone_name="UTC",
                sleep_mode_active=False,
            )
        )
        led_ops = [effect.payload.get("op") for effect in effects if getattr(effect, "kind", "") == "led"]
        self.assertNotIn("wake_up_scene", led_ops)

    def test_configurable_fajr_time_triggers_gentle_light(self):
        effects = self._run_defaults(
            _ctx(
                now_utc=datetime(2026, 3, 5, 5, 22, tzinfo=timezone.utc),
                timezone_name="UTC",
                sleep_mode_active=True,
                fajr_light_time="05:20",
            )
        )
        led_ops = [effect.payload.get("op") for effect in effects if getattr(effect, "kind", "") == "led"]
        self.assertIn("fajr_gentle_light_scene", led_ops)


if __name__ == "__main__":
    unittest.main()
