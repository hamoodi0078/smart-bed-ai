import shutil
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

import web_server
from env_isolation import IsolatedWebAuthTestCase
from commands.undo_manager import UndoManager
from scenes.scene_store import SceneStore
from time_utils import utcnow


def _workspace_tmp_dir() -> Path:
    root = Path("runtime_data") / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"undo_manager_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestUndoManager(unittest.TestCase):
    def test_record_action_stores_action(self):
        manager = UndoManager(window_seconds=10)

        manager.record_action("u1", "scene_compose", {"before": 1}, {"after": 2})
        action = manager.get_undoable_action("u1")

        self.assertIsNotNone(action)
        self.assertEqual(str(action.get("action_type", "")), "scene_compose")
        self.assertEqual(action.get("previous_state"), {"before": 1})
        self.assertEqual(action.get("new_state"), {"after": 2})
        self.assertTrue(str(action.get("timestamp", "")).strip())
        self.assertTrue(str(action.get("expires_at", "")).strip())

    def test_get_undoable_action_within_window(self):
        manager = UndoManager(window_seconds=10)
        base = utcnow()
        with patch("commands.undo_manager.utcnow", side_effect=[base, base + timedelta(seconds=5)]):
            manager.record_action("u1", "device_command", {"a": 1}, {"a": 2})
            action = manager.get_undoable_action("u1")

        self.assertIsNotNone(action)
        self.assertEqual(str(action.get("action_type", "")), "device_command")

    def test_get_undoable_action_expired_returns_none(self):
        manager = UndoManager(window_seconds=10)
        base = utcnow()
        with patch("commands.undo_manager.utcnow", side_effect=[base, base + timedelta(seconds=11)]):
            manager.record_action("u1", "device_command", {"a": 1}, {"a": 2})
            action = manager.get_undoable_action("u1")

        self.assertIsNone(action)

    def test_pop_undo_removes_action(self):
        manager = UndoManager(window_seconds=10)
        manager.record_action("u1", "scene_compose", {"before": True}, {"before": False})

        first_pop = manager.pop_undo("u1")
        second_read = manager.get_undoable_action("u1")

        self.assertIsNotNone(first_pop)
        self.assertIsNone(second_read)


class TestUndoEndpoints(IsolatedWebAuthTestCase):
    def extra_patchers(self):
        self.tmp_dir = _workspace_tmp_dir()
        self.undo_manager = UndoManager(window_seconds=10)
        self.scene_store = SceneStore(path=self.tmp_dir / "scenes_store.json")
        return [
            patch.object(web_server, "undo_manager", self.undo_manager),
            patch.object(web_server, "scene_store", self.scene_store),
        ]

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_undo_endpoint_returns_ok(self):
        previous_state = self.scene_store.get_all_templates()
        self.scene_store.save_scene(
            {
                "name": "Undo Scene Test",
                "light": {"color": "#00AAFF", "intensity": 40},
                "audio": {"type": "rain", "volume": 25},
                "premium": False,
            }
        )
        new_state = self.scene_store.get_all_templates()
        self.undo_manager.record_action(self.user_id, "scene_compose", previous_state, new_state)

        response = self.client.post("/v1/actions/undo", json={"user_id": self.user_id})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(str(body.get("undone", "")), "scene_compose")
        self.assertEqual(body.get("restored_state"), previous_state)
        self.assertEqual(self.scene_store.get_all_templates(), previous_state)

    def test_undo_endpoint_expired_returns_404(self):
        base = utcnow()
        with patch("commands.undo_manager.utcnow", side_effect=[base, base + timedelta(seconds=11)]):
            self.undo_manager.record_action(self.user_id, "device_command", {"before": 1}, {"after": 2})
            response = self.client.post("/v1/actions/undo", json={"user_id": self.user_id})

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {})
        self.assertEqual(str(error.get("code", "")), "NOTHING_TO_UNDO")
        self.assertRegex(str(error.get("trace_id", "")), r"^req_[a-f0-9]{8}$")
        self.assertEqual(str(response.headers.get("X-Trace-Id", "")), str(error.get("trace_id", "")))

    def test_undo_status_shows_can_undo_true(self):
        self.undo_manager.record_action(self.user_id, "device_command", {"before": 1}, {"after": 2})

        response = self.client.get("/v1/actions/undo/status", params={"user_id": self.user_id})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("can_undo"))
        self.assertEqual(str(body.get("action_type", "")), "device_command")
        self.assertIsInstance(body.get("seconds_remaining"), int)
        self.assertGreaterEqual(int(body.get("seconds_remaining", 0)), 1)


if __name__ == "__main__":
    unittest.main()
