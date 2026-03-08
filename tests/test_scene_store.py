import shutil
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from scenes.scene_store import SceneStore
from time_utils import from_iso


def _workspace_tmp_dir() -> Path:
    root = Path("runtime_data") / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"scene_store_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestSceneStore(unittest.TestCase):
    def test_default_scenes_loaded_on_init(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            scenes = store.get_all_templates()
            self.assertEqual(len(scenes), 5)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_all_templates_returns_list(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            scenes = store.get_all_templates()
            self.assertIsInstance(scenes, list)
            self.assertTrue(all(isinstance(scene, dict) for scene in scenes))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_template_by_id_found(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            scene = store.get_template_by_id("11111111-1111-4111-8111-111111111111")
            self.assertIsNotNone(scene)
            self.assertEqual(scene.get("name"), "Cozy Night")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_template_by_id_not_found_returns_none(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            scene = store.get_template_by_id("00000000-0000-4000-8000-000000000000")
            self.assertIsNone(scene)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_save_scene_generates_id_and_created_at(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            saved = store.save_scene(
                {
                    "name": "Custom Calm",
                    "light": {"color": "#00AACC", "intensity": 25, "duration": 4},
                    "audio": {"type": "rain", "volume": 22},
                    "premium": False,
                    "category": "relaxation",
                    "tags": ["custom"],
                }
            )
            self.assertTrue(saved.get("id"))
            UUID(str(saved.get("id")))
            self.assertTrue(saved.get("created_at"))
            parsed = from_iso(str(saved.get("created_at")))
            self.assertIsNotNone(parsed.tzinfo)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_save_scene_validates_required_fields(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            with self.assertRaises(ValueError):
                store.save_scene(
                    {
                        "light": {"color": "#FFFFFF", "intensity": 10, "duration": 1},
                        "audio": {"type": "none", "volume": 0},
                    }
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_increment_usage_increases_count(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            scene_id = "11111111-1111-4111-8111-111111111111"
            before = store.get_template_by_id(scene_id)
            self.assertIsNotNone(before)
            before_count = int(before.get("usage_count", 0))

            store.increment_usage(scene_id)
            after = store.get_template_by_id(scene_id)
            self.assertIsNotNone(after)
            self.assertEqual(int(after.get("usage_count", 0)), before_count + 1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_get_templates_for_api_format(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            rows = store.get_templates_for_api()
            self.assertTrue(rows)
            expected_keys = {
                "id",
                "name",
                "premium",
                "category",
                "tags",
                "thumbnail_url",
                "usage_count",
            }
            self.assertEqual(set(rows[0].keys()), expected_keys)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_premium_scenes_flagged_correctly(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            rows = store.get_all_templates()
            premium_names = {row.get("name") for row in rows if bool(row.get("premium", False))}
            self.assertIn("Focus Mode", premium_names)
            self.assertIn("Ocean Breeze", premium_names)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_free_scenes_count(self):
        tmp_dir = _workspace_tmp_dir()
        try:
            store = SceneStore(path=tmp_dir / "scenes_store.json")
            rows = store.get_all_templates()
            free_count = sum(1 for row in rows if not bool(row.get("premium", False)))
            self.assertEqual(free_count, 3)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
