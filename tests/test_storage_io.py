import json
import tempfile
import threading
import unittest
from pathlib import Path

from Storage.io import atomic_write_json, confine_path, locked_read_json


class TestStorageIo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.path = self.base / "nested" / "state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_atomic_write_then_locked_read_round_trip(self):
        payload = {
            "schema_version": 1,
            "name": "Dana",
            "numbers": [1, 2, 3],
            "nested": {"ok": True, "value": 42},
        }
        atomic_write_json(self.path, payload)
        loaded = locked_read_json(self.path)
        self.assertEqual(payload, loaded)

    def test_repeated_writes_keep_valid_json(self):
        final_payload = {}
        for i in range(100):
            final_payload = {
                "schema_version": 1,
                "iteration": i,
                "active": True,
                "items": [i, i + 1, i + 2],
            }
            atomic_write_json(self.path, final_payload)

            raw = self.path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            self.assertIsInstance(parsed, dict)
            self.assertEqual(parsed.get("iteration"), i)

        loaded = locked_read_json(self.path)
        self.assertEqual(loaded, final_payload)

    def test_threaded_writes_remain_valid(self):
        errors: list[Exception] = []
        barrier = threading.Barrier(8)

        def writer(thread_id: int):
            try:
                barrier.wait(timeout=5)
                for n in range(50):
                    atomic_write_json(
                        self.path,
                        {
                            "schema_version": 1,
                            "thread_id": thread_id,
                            "counter": n,
                        },
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(idx,)) for idx in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [])
        loaded = locked_read_json(self.path)
        self.assertIsInstance(loaded, dict)
        self.assertEqual(loaded.get("schema_version"), 1)
        self.assertIn("thread_id", loaded)
        self.assertIn("counter", loaded)
        json.loads(self.path.read_text(encoding="utf-8"))

    def test_invalid_json_falls_back_safely(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('{"broken": ', encoding="utf-8")

        loaded = locked_read_json(self.path)
        self.assertEqual(loaded, {})

        quarantined = list(self.path.parent.glob(f"{self.path.stem}.corrupt.*{self.path.suffix}"))
        self.assertGreaterEqual(len(quarantined), 1)

        repaired = {"schema_version": 1, "restored": True}
        atomic_write_json(self.path, repaired)
        self.assertEqual(locked_read_json(self.path), repaired)

    def test_confine_path_valid_cases(self):
        # A relative filename/path resolved under the base
        res1 = confine_path(self.base, "state.json")
        self.assertEqual(res1, (self.base / "state.json").resolve())

        res2 = confine_path(self.base, "nested/state.json")
        self.assertEqual(res2, (self.base / "nested/state.json").resolve())

        # An absolute path that is inside the base
        abs_target = (self.base / "nested" / "file.json").resolve()
        res3 = confine_path(self.base, abs_target)
        self.assertEqual(res3, abs_target)

    def test_confine_path_invalid_cases_outside_base(self):
        # A relative path trying to traverse outside
        with self.assertRaises(ValueError):
            confine_path(self.base, "../escaped.json")

        # An absolute path outside the base
        import tempfile
        with tempfile.TemporaryDirectory() as other_dir:
            other_base = Path(other_dir).resolve()
            # If the candidate is an absolute path outside the base, it must fail
            with self.assertRaises(ValueError):
                confine_path(self.base, other_base / "file.json")


if __name__ == "__main__":
    unittest.main()
