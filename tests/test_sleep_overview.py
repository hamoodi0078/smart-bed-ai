import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

import web_server
from scenes.scene_store import SceneStore


def _workspace_tmp_dir() -> Path:
    root = Path("runtime_data") / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"sleep_overview_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestSleepOverview(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = _workspace_tmp_dir()
        self._scene_store_patcher = patch.object(
            web_server,
            "scene_store",
            SceneStore(path=self.tmp_dir / "scenes_store.json"),
        )
        self._sleep_history_path_patcher = patch.object(
            web_server,
            "SLEEP_HISTORY_PATH",
            self.tmp_dir / "sleep_history.json",
        )
        self._scene_store_patcher.start()
        self._sleep_history_path_patcher.start()
        self.client = TestClient(web_server.app)

    def tearDown(self):
        self._scene_store_patcher.stop()
        self._sleep_history_path_patcher.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sleep_overview_returns_ok_true(self):
        response = self.client.get("/v1/sleep/overview")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))

    def test_readiness_score_is_between_0_and_100(self):
        response = self.client.get("/v1/sleep/overview")
        self.assertEqual(response.status_code, 200)
        score = int(response.json().get("readiness_score", -1))
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_recommended_scene_is_not_null(self):
        response = self.client.get("/v1/sleep/overview")
        self.assertEqual(response.status_code, 200)
        scene = response.json().get("recommended_scene")
        self.assertIsInstance(scene, dict)
        self.assertTrue(str(scene.get("name", "")).strip())

    def test_quick_actions_has_three_items(self):
        response = self.client.get("/v1/sleep/overview")
        self.assertEqual(response.status_code, 200)
        actions = response.json().get("quick_actions", [])
        self.assertEqual(len(actions), 3)

    def test_sensor_confidence_is_100(self):
        response = self.client.get("/v1/sleep/overview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(response.json().get("sensor_confidence", 0)), 100)

    def test_response_has_all_required_fields(self):
        response = self.client.get("/v1/sleep/overview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        required = {
            "ok",
            "readiness_score",
            "readiness_explanation",
            "recommended_scene",
            "quick_actions",
            "last_updated",
        }
        self.assertTrue(required.issubset(set(body.keys())))


if __name__ == "__main__":
    unittest.main()
