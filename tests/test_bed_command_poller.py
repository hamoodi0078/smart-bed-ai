"""Unit tests for BedCommandPoller (Plan 6) — fakes only, no hardware/thread."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from ai.bed_command_poller import ALARM_LABEL_PREFIX, BedCommandPoller


class FakeBackend:
    def __init__(self, payload: dict):
        self.payload = payload
        self.results: list[tuple[str, str, str]] = []

    def fetch_sync(self):
        return True, self.payload, "ok"

    def report_command_result(self, command_id, status, detail="", actual_state=None):
        self.results.append((command_id, status, detail))
        return True, "ok"


class FakeLed:
    def __init__(self):
        self.calls: list[tuple] = []

    def set_user_animation(self, name):
        self.calls.append(("animation", name))

    def set_user_brightness(self, value, log=True):
        self.calls.append(("brightness", round(float(value), 3)))

    def set_color_value(self, value):
        self.calls.append(("color", value))


class FakeSchedule:
    def __init__(self):
        self.alarms: list[SimpleNamespace] = []

    def add_alarm(self, time_24h, label="Alarm", repeat_days=""):
        item = SimpleNamespace(
            id=uuid4().hex[:8],
            time_24h=time_24h,
            label=label,
            enabled=True,
            next_trigger_iso="",
            repeat_days=repeat_days,
        )
        self.alarms.append(item)
        return item

    def remove_alarm(self, alarm_id):
        before = len(self.alarms)
        self.alarms = [a for a in self.alarms if a.id != alarm_id]
        return len(self.alarms) != before

    def list_alarms(self):
        return list(self.alarms)


class FakeOrchestrator:
    def __init__(self):
        self.scenes: list[dict] = []

    def apply_scene(self, led, profile, scene):
        self.scenes.append(scene)
        return str(scene.get("line", ""))


def make_poller(payload: dict):
    backend = FakeBackend(payload)
    led = FakeLed()
    schedule = FakeSchedule()
    orchestrator = FakeOrchestrator()
    poller = BedCommandPoller(
        backend_client=backend,
        led=led,
        schedule=schedule,
        environment_orchestrator=orchestrator,
        profile={"preferences": {"favorite_color": "teal"}},
    )
    return poller, backend, led, schedule, orchestrator


def sync_payload(commands=None, desired_state=None, state_version=""):
    return {
        "server_time": "2026-07-17T00:00:00+00:00",
        "commands": commands or [],
        "desired_state": desired_state,
        "state_version": state_version,
    }


class CommandDispatchTests(unittest.TestCase):
    def test_known_command_reports_completed(self):
        payload = sync_payload(commands=[{"id": "c1", "action": "winddown", "params": {}}])
        poller, backend, led, _, _ = make_poller(payload)
        poller._tick()
        self.assertEqual(backend.results[0][:2], ("c1", "completed"))
        self.assertIn(("animation", "breathing"), led.calls)

    def test_unknown_action_reports_failed(self):
        payload = sync_payload(commands=[{"id": "c2", "action": "teleport", "params": {}}])
        poller, backend, _, _, _ = make_poller(payload)
        poller._tick()
        self.assertEqual(backend.results[0][:2], ("c2", "failed"))

    def test_handler_exception_reports_failed_and_loop_survives(self):
        payload = sync_payload(
            commands=[
                {"id": "bad", "action": "winddown", "params": {}},
                {"id": "good", "action": "wake_recovery", "params": {}},
            ]
        )
        poller, backend, led, _, _ = make_poller(payload)

        def boom(params):
            raise RuntimeError("SPI bus locked")

        poller._handlers["winddown"] = boom
        poller._tick()
        statuses = {cid: status for cid, status, _ in backend.results}
        self.assertEqual(statuses["bad"], "failed")
        self.assertEqual(statuses["good"], "completed")


class ReconcileTests(unittest.TestCase):
    def test_alarms_reconcile_owns_only_app_alarms(self):
        desired = {
            "lighting": {"lights_on": True, "light_level": 40},
            "alarms": [
                {
                    "alarm_id": "a1",
                    "time": "06:30",
                    "days": [1, 2],
                    "enabled": True,
                    "label": "Fajr",
                    "sound": "default",
                    "vibrate": True,
                },
                {
                    "alarm_id": "a2",
                    "time": "22:00",
                    "days": [],
                    "enabled": False,
                    "label": "Off",
                    "sound": "default",
                    "vibrate": True,
                },
            ],
            "scene": None,
        }
        poller, _, _, schedule, _ = make_poller(
            sync_payload(desired_state=desired, state_version="v1")
        )
        schedule.add_alarm("05:00", label="voice alarm")  # not app-owned
        schedule.add_alarm("09:00", label=f"{ALARM_LABEL_PREFIX} stale")  # app-owned leftover
        poller._tick()
        labels = [a.label for a in schedule.list_alarms()]
        self.assertIn("voice alarm", labels)
        self.assertNotIn(f"{ALARM_LABEL_PREFIX} stale", labels)
        app_alarms = [a for a in schedule.list_alarms() if a.label.startswith(ALARM_LABEL_PREFIX)]
        self.assertEqual(len(app_alarms), 1)
        self.assertEqual(app_alarms[0].time_24h, "06:30")
        self.assertEqual(app_alarms[0].repeat_days, "0,1")  # app days 1,2 -> weekday 0,1

    def test_scene_applied_via_orchestrator(self):
        desired = {
            "lighting": {"lights_on": True, "light_level": 45},
            "alarms": [],
            "scene": {"scene_key": "calm_recovery"},
        }
        poller, _, _, _, orchestrator = make_poller(
            sync_payload(desired_state=desired, state_version="v1")
        )
        poller._tick()
        self.assertEqual(orchestrator.scenes[0]["key"], "calm_recovery")
        self.assertEqual(orchestrator.scenes[0]["animation"], "breathing")

    def test_unchanged_state_version_skips_reconcile(self):
        desired = {
            "lighting": {"lights_on": True, "light_level": 45},
            "alarms": [],
            "scene": {"scene_key": "calm_recovery"},
        }
        poller, _, _, _, orchestrator = make_poller(
            sync_payload(desired_state=desired, state_version="v1")
        )
        poller._tick()
        poller._tick()
        self.assertEqual(len(orchestrator.scenes), 1)

    def test_lights_off_wins_over_scene(self):
        desired = {
            "lighting": {"lights_on": False, "light_level": 45},
            "alarms": [],
            "scene": {"scene_key": "calm_recovery"},
        }
        poller, _, led, _, _ = make_poller(sync_payload(desired_state=desired, state_version="v1"))
        poller._tick()
        self.assertEqual(led.calls[-1], ("brightness", 0.0))


if __name__ == "__main__":
    unittest.main()
