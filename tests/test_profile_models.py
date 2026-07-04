"""Tests for the four profile replacement SQLAlchemy models."""

import os
import unittest

from database import DatabaseConnection
from database.models import (
    User,
    UserPhoneAuth,
    UserProfilePrefs,
    UserRoutine,
    UserSocialIdentity,
)


def _make_db() -> DatabaseConnection:
    return DatabaseConnection(database_url="sqlite://")


def _make_user(db: DatabaseConnection, email: str = "profile@example.com") -> str:
    import hashlib

    uid = "u-" + hashlib.md5(email.encode()).hexdigest()[:8]
    with db.get_session() as session:
        if session.get(User, uid) is None:
            session.add(User(id=uid, email=email, password_hash="x"))
            session.flush()
    return uid


class TestUserRoutineModel(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.uid = _make_user(self.db)

    def test_columns_exist(self):
        cols = set(UserRoutine.__table__.columns.keys())
        self.assertTrue({"id", "user_id", "bedtime", "wake", "weekends_different"}.issubset(cols))

    def test_create_and_fetch(self):
        from uuid import uuid4

        row_id = str(uuid4())
        with self.db.get_session() as session:
            session.add(
                UserRoutine(
                    id=row_id,
                    user_id=self.uid,
                    bedtime="22:30",
                    wake="06:30",
                    weekends_different=True,
                )
            )
            session.flush()

        with self.db.get_session() as session:
            row = session.get(UserRoutine, row_id)
            self.assertIsNotNone(row)
            self.assertEqual(row.bedtime, "22:30")
            self.assertEqual(row.wake, "06:30")
            self.assertTrue(row.weekends_different)

    def test_user_id_is_unique(self):
        from uuid import uuid4
        from sqlalchemy.exc import IntegrityError

        with self.db.get_session() as session:
            session.add(
                UserRoutine(id=str(uuid4()), user_id=self.uid, bedtime="22:00", wake="06:00")
            )
            session.flush()

        with self.assertRaises(Exception):
            with self.db.get_session() as session:
                session.add(
                    UserRoutine(id=str(uuid4()), user_id=self.uid, bedtime="23:00", wake="07:00")
                )
                session.flush()


class TestUserProfilePrefsModel(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.uid = _make_user(self.db, email="prefs@example.com")

    def test_columns_exist(self):
        cols = set(UserProfilePrefs.__table__.columns.keys())
        expected = {
            "id",
            "user_id",
            "display_name",
            "timezone",
            "push_enabled",
            "email_enabled",
            "theme_mode",
        }
        self.assertTrue(expected.issubset(cols))

    def test_create_and_fetch(self):
        from uuid import uuid4

        row_id = str(uuid4())
        with self.db.get_session() as session:
            session.add(
                UserProfilePrefs(
                    id=row_id,
                    user_id=self.uid,
                    display_name="Danah",
                    timezone="Asia/Kuwait",
                    push_enabled=True,
                    email_enabled=False,
                    theme_mode="dark",
                )
            )
            session.flush()

        with self.db.get_session() as session:
            row = session.get(UserProfilePrefs, row_id)
            self.assertIsNotNone(row)
            self.assertEqual(row.display_name, "Danah")
            self.assertEqual(row.timezone, "Asia/Kuwait")
            self.assertFalse(row.email_enabled)

    def test_location_fields_nullable(self):
        from uuid import uuid4

        row_id = str(uuid4())
        with self.db.get_session() as session:
            session.add(UserProfilePrefs(id=row_id, user_id=self.uid))
            session.flush()

        with self.db.get_session() as session:
            row = session.get(UserProfilePrefs, row_id)
            self.assertIsNone(row.latitude)
            self.assertIsNone(row.longitude)
            self.assertIsNone(row.city)


class TestUserSocialIdentityModel(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.uid = _make_user(self.db, email="social@example.com")

    def test_columns_exist(self):
        cols = set(UserSocialIdentity.__table__.columns.keys())
        expected = {"id", "user_id", "provider", "provider_user_id", "email", "email_verified"}
        self.assertTrue(expected.issubset(cols))

    def test_create_and_fetch(self):
        from uuid import uuid4

        row_id = str(uuid4())
        with self.db.get_session() as session:
            session.add(
                UserSocialIdentity(
                    id=row_id,
                    user_id=self.uid,
                    provider="google",
                    provider_user_id="google-uid-123",
                    email="social@gmail.com",
                    email_verified=True,
                )
            )
            session.flush()

        with self.db.get_session() as session:
            row = session.get(UserSocialIdentity, row_id)
            self.assertIsNotNone(row)
            self.assertEqual(row.provider, "google")
            self.assertTrue(row.email_verified)

    def test_unique_constraint_provider_uid(self):
        from uuid import uuid4

        with self.db.get_session() as session:
            session.add(
                UserSocialIdentity(
                    id=str(uuid4()),
                    user_id=self.uid,
                    provider="apple",
                    provider_user_id="apple-uid-999",
                )
            )
            session.flush()

        with self.assertRaises(Exception):
            with self.db.get_session() as session:
                session.add(
                    UserSocialIdentity(
                        id=str(uuid4()),
                        user_id=self.uid,
                        provider="apple",
                        provider_user_id="apple-uid-999",
                    )
                )
                session.flush()


class TestUserPhoneAuthModel(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.uid = _make_user(self.db, email="phone@example.com")

    def test_columns_exist(self):
        cols = set(UserPhoneAuth.__table__.columns.keys())
        self.assertTrue({"id", "phone_number", "user_id"}.issubset(cols))

    def test_create_and_fetch(self):
        from uuid import uuid4

        row_id = str(uuid4())
        with self.db.get_session() as session:
            session.add(
                UserPhoneAuth(
                    id=row_id,
                    user_id=self.uid,
                    phone_number="+96512345678",
                )
            )
            session.flush()

        with self.db.get_session() as session:
            row = session.get(UserPhoneAuth, row_id)
            self.assertIsNotNone(row)
            self.assertEqual(row.phone_number, "+96512345678")

    def test_phone_number_is_unique(self):
        from uuid import uuid4

        with self.db.get_session() as session:
            session.add(
                UserPhoneAuth(
                    id=str(uuid4()),
                    user_id=self.uid,
                    phone_number="+96511111111",
                )
            )
            session.flush()

        with self.assertRaises(Exception):
            with self.db.get_session() as session:
                session.add(
                    UserPhoneAuth(
                        id=str(uuid4()),
                        user_id=self.uid,
                        phone_number="+96511111111",
                    )
                )
                session.flush()


if __name__ == "__main__":
    unittest.main()
