"""Tests for AlarmRepository — CRUD operations against an in-memory SQLite DB."""

import os
import unittest

from database import Alarm, DatabaseConnection
from database.repositories import AlarmRepository


def _make_db() -> DatabaseConnection:
    return DatabaseConnection(database_url="sqlite://")


def _make_user(db: DatabaseConnection, email: str = "test@example.com") -> str:
    from database.models import User
    from time_utils import utcnow
    import hashlib

    uid = "u-" + hashlib.md5(email.encode()).hexdigest()[:8]
    with db.get_session() as session:
        if session.get(User, uid) is None:
            session.add(User(
                id=uid,
                email=email,
                password_hash="x",
                full_name="Test User",
            ))
            session.flush()
    return uid


class TestAlarmRepositoryCreate(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.user_id = _make_user(self.db)
        self.repo = AlarmRepository(db=self.db)

    def test_create_returns_alarm_with_correct_fields(self):
        alarm = self.repo.create_alarm(
            user_id=self.user_id,
            time="07:30",
            label="Morning",
            enabled=True,
            days_of_week=[1, 2, 3, 4, 5],
            wake_style="gentle_light",
            smart_window_minutes=20,
        )
        self.assertIsInstance(alarm, Alarm)
        self.assertEqual(alarm.user_id, self.user_id)
        self.assertEqual(alarm.time, "07:30")
        self.assertEqual(alarm.label, "Morning")
        self.assertTrue(alarm.enabled)
        self.assertEqual(alarm.days_of_week, [1, 2, 3, 4, 5])
        self.assertEqual(alarm.wake_style, "gentle_light")
        self.assertEqual(alarm.smart_window_minutes, 20)

    def test_create_assigns_uuid_id(self):
        alarm = self.repo.create_alarm(user_id=self.user_id, time="08:00")
        self.assertIsNotNone(alarm.id)
        self.assertGreater(len(alarm.id), 0)

    def test_create_default_label_is_empty(self):
        alarm = self.repo.create_alarm(user_id=self.user_id, time="06:00")
        self.assertEqual(alarm.label, "")

    def test_create_default_enabled_true(self):
        alarm = self.repo.create_alarm(user_id=self.user_id, time="06:00")
        self.assertTrue(alarm.enabled)


class TestAlarmRepositoryList(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.user_id = _make_user(self.db)
        self.repo = AlarmRepository(db=self.db)

    def test_list_returns_empty_for_new_user(self):
        alarms = self.repo.list_alarms(self.user_id)
        self.assertEqual(alarms, [])

    def test_list_returns_all_user_alarms(self):
        self.repo.create_alarm(user_id=self.user_id, time="06:00", label="A")
        self.repo.create_alarm(user_id=self.user_id, time="07:00", label="B")
        alarms = self.repo.list_alarms(self.user_id)
        self.assertEqual(len(alarms), 2)

    def test_list_does_not_return_other_user_alarms(self):
        other_id = _make_user(self.db, email="other@example.com")
        self.repo.create_alarm(user_id=other_id, time="06:00")
        alarms = self.repo.list_alarms(self.user_id)
        self.assertEqual(alarms, [])

    def test_list_capped_at_max_per_user(self):
        limit = AlarmRepository._MAX_ALARMS_PER_USER
        for i in range(limit):
            self.repo.create_alarm(user_id=self.user_id, time=f"0{i % 9}:00")
        with self.assertRaises(ValueError):
            self.repo.create_alarm(user_id=self.user_id, time="09:00")
        alarms = self.repo.list_alarms(self.user_id)
        self.assertLessEqual(len(alarms), limit)


class TestAlarmRepositoryGetUpdateDelete(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.user_id = _make_user(self.db)
        self.repo = AlarmRepository(db=self.db)
        self.alarm = self.repo.create_alarm(
            user_id=self.user_id, time="09:00", label="Test"
        )

    def test_get_alarm_returns_correct_row(self):
        fetched = self.repo.get_alarm(self.alarm.id, self.user_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, self.alarm.id)

    def test_get_alarm_returns_none_for_wrong_user(self):
        other_id = _make_user(self.db, email="other2@example.com")
        result = self.repo.get_alarm(self.alarm.id, other_id)
        self.assertIsNone(result)

    def test_get_alarm_returns_none_for_missing_id(self):
        result = self.repo.get_alarm("nonexistent-id", self.user_id)
        self.assertIsNone(result)

    def test_update_alarm_changes_label(self):
        updated = self.repo.update_alarm(self.alarm.id, self.user_id, label="Updated")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.label, "Updated")

    def test_update_alarm_changes_enabled(self):
        updated = self.repo.update_alarm(self.alarm.id, self.user_id, enabled=False)
        self.assertIsNotNone(updated)
        self.assertFalse(updated.enabled)

    def test_update_alarm_returns_none_for_wrong_user(self):
        other_id = _make_user(self.db, email="other3@example.com")
        result = self.repo.update_alarm(self.alarm.id, other_id, label="X")
        self.assertIsNone(result)

    def test_delete_alarm_removes_row(self):
        deleted = self.repo.delete_alarm(self.alarm.id, self.user_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.repo.get_alarm(self.alarm.id, self.user_id))

    def test_delete_alarm_returns_false_for_wrong_user(self):
        other_id = _make_user(self.db, email="other4@example.com")
        deleted = self.repo.delete_alarm(self.alarm.id, other_id)
        self.assertFalse(deleted)
        # original alarm still exists
        self.assertIsNotNone(self.repo.get_alarm(self.alarm.id, self.user_id))

    def test_delete_alarm_returns_false_for_missing_id(self):
        deleted = self.repo.delete_alarm("does-not-exist", self.user_id)
        self.assertFalse(deleted)


if __name__ == "__main__":
    unittest.main()
