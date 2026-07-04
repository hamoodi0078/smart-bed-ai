import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

import web_server
from Storage.subscription_store import SubscriptionStore
from scenes.scene_store import SceneStore
from env_isolation import reset_web_server_db_singletons
from time_utils import from_iso


def _workspace_tmp_dir() -> Path:
    root = Path("runtime_data") / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"scene_endpoints_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestSceneEndpoints(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = _workspace_tmp_dir()
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)

        # Scene endpoints require an authenticated user; isolate both the
        # session store and the DB so tests never touch real dev data.
        self._patch_env = patch.dict(
            os.environ,
            {"DATABASE_URL": f"sqlite:///{(tmp / 'scenes.sqlite3').as_posix()}"},
            clear=False,
        )
        self._patch_store = patch.object(
            web_server, "store", SubscriptionStore(db_path=tmp / "subscription_db.json")
        )
        self._patch_scene = patch.object(
            web_server,
            "scene_store",
            SceneStore(path=self.tmp_dir / "scenes_store.json"),
        )
        self._patch_env.start()
        self._patch_store.start()
        self._patch_scene.start()
        reset_web_server_db_singletons(web_server)

        self.client = TestClient(web_server.app)
        response = self.client.post(
            "/v1/auth/register",
            json={
                "email": "scene-tester@example.com",
                "password": "Scenepass123",
                "name": "Scene Tester",
            },
        )
        assert response.status_code == 200, f"scene test login failed: {response.text}"

        # Scene composing is premium-gated — upgrade the test user.
        user_id = response.json().get("user", {}).get("user_id", "")
        web_server._db_user_repository().update_subscription(user_id, status="premium")

    def tearDown(self):
        reset_web_server_db_singletons(web_server)
        self._patch_scene.stop()
        self._patch_store.stop()
        self._patch_env.stop()
        self._tmp.cleanup()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_get_templates_returns_all_five(self):
        response = self.client.get("/v1/scenes/templates")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body.get("templates", [])), 5)
        self.assertEqual(int(body.get("total", 0)), 5)

    def test_get_templates_premium_only_filter(self):
        response = self.client.get("/v1/scenes/templates", params={"premium_only": "true"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        templates = body.get("templates", [])
        self.assertEqual(len(templates), 2)
        self.assertTrue(all(bool(row.get("premium", False)) for row in templates))

    def test_compose_scene_success(self):
        payload = {
            "name": "My Scene",
            "light": {"color": "#FF0000", "intensity": 50, "duration": 5},
            "audio": {"type": "ocean_waves", "volume": 30},
            "premium": False,
            "category": "relaxation",
            "tags": ["custom"],
        }
        response = self.client.post("/v1/scenes/compose", json=payload)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body.get("ok"))
        scene = body.get("scene", {})
        self.assertTrue(str(scene.get("id", "")).strip())
        self.assertTrue(str(scene.get("created_at", "")).strip())
        self.assertEqual(scene.get("name"), payload["name"])
        from_iso(str(scene.get("created_at")))

        applied_state = body.get("applied_state", {})
        self.assertEqual(applied_state.get("light"), payload["light"])
        self.assertEqual(applied_state.get("audio"), payload["audio"])
        self.assertTrue(str(applied_state.get("activated_at", "")).strip())
        from_iso(str(applied_state.get("activated_at")))

    def test_compose_scene_missing_name_returns_422(self):
        payload = {
            "light": {"color": "#FF0000", "intensity": 50, "duration": 5},
            "audio": {"type": "ocean_waves", "volume": 30},
            "premium": False,
            "category": "relaxation",
            "tags": ["custom"],
        }
        response = self.client.post("/v1/scenes/compose", json=payload)
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {})
        self.assertEqual(error.get("code"), "INVALID_SCENE_CONFIG")
        self.assertEqual(error.get("message"), "Missing required field: name")
        self.assertRegex(str(error.get("trace_id", "")), r"^req_[a-f0-9]{8}$")
        self.assertEqual(
            str(response.headers.get("X-Trace-Id", "")), str(error.get("trace_id", ""))
        )

    def test_compose_scene_missing_light_returns_422(self):
        payload = {
            "name": "My Scene",
            "audio": {"type": "ocean_waves", "volume": 30},
            "premium": False,
            "category": "relaxation",
            "tags": ["custom"],
        }
        response = self.client.post("/v1/scenes/compose", json=payload)
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {})
        self.assertEqual(error.get("code"), "INVALID_SCENE_CONFIG")
        self.assertEqual(error.get("message"), "Missing required field: light")

    def test_compose_scene_missing_audio_returns_422(self):
        payload = {
            "name": "My Scene",
            "light": {"color": "#FF0000", "intensity": 50, "duration": 5},
            "premium": False,
            "category": "relaxation",
            "tags": ["custom"],
        }
        response = self.client.post("/v1/scenes/compose", json=payload)
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {})
        self.assertEqual(error.get("code"), "INVALID_SCENE_CONFIG")
        self.assertEqual(error.get("message"), "Missing required field: audio")

    def test_compose_scene_increments_total_count(self):
        before = self.client.get("/v1/scenes/templates").json()
        self.assertEqual(int(before.get("total", 0)), 5)

        self.client.post(
            "/v1/scenes/compose",
            json={
                "name": "My Scene",
                "light": {"color": "#FF0000", "intensity": 50, "duration": 5},
                "audio": {"type": "ocean_waves", "volume": 30},
                "premium": False,
                "category": "relaxation",
                "tags": ["custom"],
            },
        )

        after = self.client.get("/v1/scenes/templates").json()
        self.assertEqual(int(after.get("total", 0)), 6)

    def test_templates_response_has_ok_true(self):
        response = self.client.get("/v1/scenes/templates")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))

    def test_templates_total_matches_list_length(self):
        response = self.client.get("/v1/scenes/templates")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(int(body.get("total", 0)), len(body.get("templates", [])))


if __name__ == "__main__":
    unittest.main()
