import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from automations.base import Automation
from automations.defaults import build_default_automations
from automations.registry import AutomationRegistry
from core.types import Effect


def _ctx(
    *,
    now_utc: datetime,
    timezone_name: str = "UTC",
    sleep_mode_active: bool = False,
    quiet_mode_active: bool = False,
    quiet_window: str = "",
    has_pending_work_planning_reminder_today: bool = False,
    fajr_light_time: str = "04:50",
) -> dict[str, object]:
    return {
        "now_utc": now_utc,
        "timezone": timezone_name,
        "sleep_mode_active": sleep_mode_active,
        "quiet_mode_active": quiet_mode_active,
        "quiet_window": quiet_window,
        "has_pending_work_planning_reminder_today": has_pending_work_planning_reminder_today,
        "fajr_light_time": fajr_light_time,
    }


class TestAutomationRegistry(unittest.TestCase):
    def test_cooldown_blocks_repeated_runs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            registry.register(
                Automation(
                    name="cooldown_test",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "x"})],
                    cooldown_minutes=60,
                )
            )

            first = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc)))
            second = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 0, 10, tzinfo=timezone.utc)))

            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])

    def test_once_per_window_runs_only_once_even_without_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            registry.register(
                Automation(
                    name="window_once",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "w"})],
                    cooldown_minutes=0,
                    window_key=lambda ctx: "2026-03-05:window",
                )
            )

            first = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc)))
            second = registry.run_automations(_ctx(now_utc=datetime(2026, 3, 5, 0, 1, tzinfo=timezone.utc)))

            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])

    def test_persistence_resumes_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "automations_state.json"

            first_registry = AutomationRegistry(state_path=state_path)
            first_registry.register(
                Automation(
                    name="persisted",
                    trigger=lambda ctx: True,
                    action=lambda ctx: [Effect(kind="say", payload={"text": "p"})],
                    cooldown_minutes=120,
                )
            )

            t0 = datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc)
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


class TestDefaultAutomations(unittest.TestCase):
    def _run_defaults(self, ctx: dict[str, object]) -> list[object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "automations_state.json"
            registry = AutomationRegistry(state_path=state_path)
            for automation in build_default_automations():
                registry.register(automation)
            return registry.run_automations(ctx)

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
