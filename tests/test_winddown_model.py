import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from Storage.io import locked_read_json
from winddown import WindDownModel


def _workspace_tmp_dir() -> Path:
    root = Path("runtime_data") / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"winddown_model_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestWindDownModel(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = _workspace_tmp_dir()
        self.store_path = self.tmp_dir / "winddown_session.json"
        self.model = WindDownModel(path=self.store_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_session_returns_dict(self):
        session = self.model.create_session()
        self.assertIsInstance(session, dict)

    def test_create_session_has_flow_id(self):
        session = self.model.create_session()
        self.assertTrue(str(session.get("flow_id", "")).strip())

    def test_create_session_has_four_steps(self):
        session = self.model.create_session()
        self.assertEqual(len(session.get("steps", [])), 4)

    def test_get_step_returns_correct_step(self):
        self.model.create_session()
        step = self.model.get_step(2)
        self.assertIsInstance(step, dict)
        self.assertEqual(int(step.get("step", 0)), 2)
        self.assertEqual(str(step.get("name", "")), "dim_lights")

    def test_get_step_invalid_returns_none(self):
        self.model.create_session()
        self.assertIsNone(self.model.get_step(99))

    def test_get_breathing_timings_returns_list(self):
        self.model.create_session()
        timings = self.model.get_breathing_timings()
        self.assertIsInstance(timings, list)
        self.assertGreaterEqual(len(timings), 1)
        self.assertEqual(int(timings[0].get("minute", -1)), 0)
        self.assertTrue(str(timings[0].get("prompt", "")).strip())

    def test_session_saved_to_file(self):
        created = self.model.create_session()
        stored = locked_read_json(self.store_path)
        self.assertEqual(str(stored.get("flow_id", "")), str(created.get("flow_id", "")))

    def test_get_current_session_returns_session(self):
        created = self.model.create_session()
        current = self.model.get_current_session()
        self.assertIsInstance(current, dict)
        self.assertEqual(str(current.get("flow_id", "")), str(created.get("flow_id", "")))


if __name__ == "__main__":
    unittest.main()
