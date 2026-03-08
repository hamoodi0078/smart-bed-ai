import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from Storage.io import locked_read_json
from automations.base import Automation
from automations.idempotency import IdempotencyStore, make_fingerprint
from automations.registry import AutomationRegistry
from core.types import Effect


def _workspace_tmp_dir() -> Path:
    root = Path("runtime_data") / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"idempotency_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestIdempotencyStore(unittest.TestCase):
    def test_same_fingerprint_within_window_is_duplicate(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = IdempotencyStore(path=tmp_dir / "idempotency_store.json")
            fp = make_fingerprint("auto_1", "say", datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc))

            self.assertFalse(store.is_duplicate(fp, window_seconds=60))
            self.assertTrue(store.is_duplicate(fp, window_seconds=60))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_different_fingerprint_is_not_duplicate(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = IdempotencyStore(path=tmp_dir / "idempotency_store.json")
            ts = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            fp_say = make_fingerprint("auto_1", "say", ts)
            fp_led = make_fingerprint("auto_1", "led", ts)

            self.assertFalse(store.is_duplicate(fp_say, window_seconds=60))
            self.assertFalse(store.is_duplicate(fp_led, window_seconds=60))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_expired_fingerprint_is_not_duplicate(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = IdempotencyStore(path=tmp_dir / "idempotency_store.json")
            fp = make_fingerprint("auto_1", "say", datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc))
            base_now = datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc)

            with patch("automations.idempotency.utcnow", return_value=base_now):
                self.assertFalse(store.is_duplicate(fp, window_seconds=60))

            with patch("automations.idempotency.utcnow", return_value=base_now + timedelta(seconds=61)):
                self.assertFalse(store.is_duplicate(fp, window_seconds=60))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_cleanup_removes_expired_entries(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store_path = tmp_dir / "idempotency_store.json"
            store = IdempotencyStore(path=store_path)
            base_now = datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc)

            with patch("automations.idempotency.utcnow", return_value=base_now):
                store.record("still_valid", window_seconds=120)
                store.record("expired_soon", window_seconds=30)

            with patch("automations.idempotency.utcnow", return_value=base_now + timedelta(seconds=45)):
                store.cleanup_expired()

            payload = locked_read_json(store_path)
            entries = payload.get("fingerprints", {})
            self.assertIn("still_valid", entries)
            self.assertNotIn("expired_soon", entries)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_make_fingerprint_truncates_to_minute(self):
        ts_a = datetime(2026, 3, 8, 12, 4, 5, tzinfo=timezone.utc)
        ts_b = datetime(2026, 3, 8, 12, 4, 35, tzinfo=timezone.utc)

        fp_a = make_fingerprint("auto_1", "say", ts_a)
        fp_b = make_fingerprint("auto_1", "say", ts_b)

        self.assertEqual(fp_a, fp_b)


class TestAutomationRegistryIdempotency(unittest.TestCase):
    def test_automation_registry_blocks_duplicate_trigger(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            idempotency_path = tmp_dir / "idempotency_store.json"
            now = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
            automation = Automation(
                name="dedup_test",
                trigger=lambda ctx: True,
                action=lambda ctx: [Effect(kind="say", payload={"text": "hello"})],
                cooldown_minutes=60,
            )

            first_registry = AutomationRegistry(state_path=tmp_dir / "state_one.json")
            first_registry._idempotency_store = IdempotencyStore(path=idempotency_path)
            first_registry.register(automation)

            second_registry = AutomationRegistry(state_path=tmp_dir / "state_two.json")
            second_registry._idempotency_store = IdempotencyStore(path=idempotency_path)
            second_registry.register(automation)

            first_effects = first_registry.run_automations({"now_utc": now, "timezone": "UTC"})
            second_effects = second_registry.run_automations({"now_utc": now, "timezone": "UTC"})

            self.assertEqual(len(first_effects), 1)
            self.assertEqual(second_effects, [])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
