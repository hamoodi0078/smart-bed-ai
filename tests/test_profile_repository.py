"""Tests for ProfileRepository — DB-backed profile/settings/routine CRUD."""

import os
import unittest

from database import DatabaseConnection, ProfileRepository
from database.models import User


def _make_db() -> DatabaseConnection:
    return DatabaseConnection(database_url="sqlite://")


def _seed_user(db: DatabaseConnection, email: str = "repo@example.com") -> str:
    import hashlib

    uid = "u-" + hashlib.md5(email.encode()).hexdigest()[:8]
    with db.get_session() as session:
        if session.get(User, uid) is None:
            session.add(User(id=uid, email=email, password_hash="x"))
            session.flush()
    return uid


class TestProfileRepositoryPrefs(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.uid = _seed_user(self.db)
        self.repo = ProfileRepository(db=self.db)

    def test_get_prefs_returns_defaults_for_new_user(self):
        prefs = self.repo.get_profile_prefs(self.uid)
        self.assertEqual(prefs["timezone"], "Asia/Kuwait")
        self.assertTrue(prefs["push_enabled"])
        self.assertEqual(prefs["theme_mode"], "system")

    def test_upsert_creates_row(self):
        prefs = self.repo.upsert_profile_prefs(
            self.uid,
            display_name="Danah",
            timezone="Asia/Riyadh",
            theme_mode="dark",
        )
        self.assertEqual(prefs["display_name"], "Danah")
        self.assertEqual(prefs["timezone"], "Asia/Riyadh")
        self.assertEqual(prefs["theme_mode"], "dark")

    def test_upsert_updates_existing_row(self):
        self.repo.upsert_profile_prefs(self.uid, display_name="First")
        prefs = self.repo.upsert_profile_prefs(self.uid, display_name="Updated")
        self.assertEqual(prefs["display_name"], "Updated")

    def test_upsert_preserves_unmodified_fields(self):
        self.repo.upsert_profile_prefs(self.uid, city="Kuwait City", country_code="KW")
        prefs = self.repo.upsert_profile_prefs(self.uid, theme_mode="light")
        self.assertEqual(prefs["city"], "Kuwait City")
        self.assertEqual(prefs["country_code"], "KW")
        self.assertEqual(prefs["theme_mode"], "light")

    def test_get_returns_none_latitude_by_default(self):
        prefs = self.repo.get_profile_prefs(self.uid)
        self.assertIsNone(prefs["latitude"])

    def test_upsert_location_fields(self):
        prefs = self.repo.upsert_profile_prefs(
            self.uid,
            latitude=29.3759,
            longitude=47.9774,
            city="Kuwait City",
        )
        self.assertAlmostEqual(prefs["latitude"], 29.3759, places=3)
        self.assertAlmostEqual(prefs["longitude"], 47.9774, places=3)

    def test_empty_user_id_returns_defaults(self):
        prefs = self.repo.get_profile_prefs("")
        self.assertIn("timezone", prefs)

    def test_upsert_empty_user_id_raises(self):
        with self.assertRaises(ValueError):
            self.repo.upsert_profile_prefs("", display_name="X")


class TestProfileRepositorySettings(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.uid = _seed_user(self.db, email="settings@example.com")
        self.repo = ProfileRepository(db=self.db)

    def test_get_settings_returns_defaults_for_new_user(self):
        s = self.repo.get_settings(self.uid)
        self.assertEqual(s["response_style"], "balanced")
        self.assertEqual(s["wind_down_minutes"], 45)
        self.assertTrue(s["weekly_insight_enabled"])

    def test_upsert_settings_saves_and_returns(self):
        s = self.repo.upsert_settings(
            self.uid,
            response_style="coaching",
            wind_down_minutes=30,
            partner_mode_enabled=True,
        )
        self.assertEqual(s["response_style"], "coaching")
        self.assertEqual(s["wind_down_minutes"], 30)
        self.assertTrue(s["partner_mode_enabled"])

    def test_upsert_settings_merges_with_defaults(self):
        self.repo.upsert_settings(self.uid, wind_down_minutes=60)
        s = self.repo.get_settings(self.uid)
        self.assertEqual(s["wind_down_minutes"], 60)
        self.assertEqual(s["response_style"], "balanced")

    def test_unknown_settings_key_ignored(self):
        s = self.repo.upsert_settings(self.uid, unknown_key="ignored")
        self.assertNotIn("unknown_key", s)

    def test_get_settings_empty_user_id_returns_defaults(self):
        s = self.repo.get_settings("")
        self.assertIn("response_style", s)


class TestProfileRepositoryRoutine(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.uid = _seed_user(self.db, email="routine@example.com")
        self.repo = ProfileRepository(db=self.db)

    def test_get_routine_returns_defaults_for_new_user(self):
        r = self.repo.get_routine(self.uid)
        self.assertEqual(r["bedtime"], "22:30")
        self.assertEqual(r["wake"], "07:00")
        self.assertFalse(r["weekends_different"])

    def test_upsert_routine_creates_row(self):
        r = self.repo.upsert_routine(self.uid, bedtime="23:00", wake="06:30")
        self.assertEqual(r["bedtime"], "23:00")
        self.assertEqual(r["wake"], "06:30")

    def test_upsert_routine_updates_existing(self):
        self.repo.upsert_routine(self.uid, bedtime="22:00")
        r = self.repo.upsert_routine(self.uid, bedtime="23:30")
        self.assertEqual(r["bedtime"], "23:30")

    def test_upsert_routine_weekends_different(self):
        r = self.repo.upsert_routine(
            self.uid,
            weekends_different=True,
            weekend_bedtime="00:00",
            weekend_wake="09:00",
        )
        self.assertTrue(r["weekends_different"])
        self.assertEqual(r["weekend_bedtime"], "00:00")
        self.assertEqual(r["weekend_wake"], "09:00")


if __name__ == "__main__":
    unittest.main()
