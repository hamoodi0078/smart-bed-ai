import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Storage.io import locked_read_json
import Storage.user_profile as user_profile
from Storage.subscription_store import SubscriptionStore


class TestStorageSchemaVersion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_user_profile_adds_schema_version_on_load(self):
        profile_path = self.base / "user_profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text('{"name":"Dana"}', encoding="utf-8")

        with patch.object(user_profile, "PROFILE_PATH", profile_path):
            loaded = user_profile.load_profile()

        self.assertIsInstance(loaded, dict)
        self.assertEqual(loaded.get("schema_version"), user_profile.PROFILE_SCHEMA_VERSION)
        stored = locked_read_json(profile_path)
        self.assertEqual(stored.get("schema_version"), user_profile.PROFILE_SCHEMA_VERSION)

    def test_subscription_store_adds_schema_version_when_missing(self):
        db_path = self.base / "subscription_db.json"
        db_path.write_text("{}", encoding="utf-8")

        store = SubscriptionStore(db_path=db_path)
        self.assertEqual(store.db.get("schema_version"), 1)

        stored = locked_read_json(db_path)
        self.assertEqual(stored.get("schema_version"), 1)

    def test_subscription_store_saves_schema_version(self):
        db_path = self.base / "subscription_db.json"
        store = SubscriptionStore(db_path=db_path)
        store.save()

        stored = locked_read_json(db_path)
        self.assertEqual(stored.get("schema_version"), 1)


if __name__ == "__main__":
    unittest.main()
