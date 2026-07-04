"""Tests for OtpRepository and SpotifyTokenRepository."""

import os
import unittest
from datetime import datetime, timedelta, timezone

from database import DatabaseConnection, OtpRepository, SpotifyTokenRepository
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


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TestOtpRepository(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.repo = OtpRepository(db=self.db)

    def test_create_and_get(self):
        expires = _utcnow() + timedelta(minutes=10)
        self.repo.create(
            request_id="otp_abc123",
            phone_number="+96512345678",
            otp_digest="digest_xyz",
            expires_at=expires,
            client_name="flutter_app",
            delivery_provider="twilio",
            delivery_status="accepted",
            delivery_message_id="msg_001",
        )
        row = self.repo.get("otp_abc123")
        self.assertIsNotNone(row)
        self.assertEqual(row["phone_number"], "+96512345678")
        self.assertEqual(row["otp_digest"], "digest_xyz")
        self.assertEqual(row["attempts"], 0)
        self.assertEqual(row["delivery_provider"], "twilio")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.repo.get("nonexistent_id"))

    def test_increment_attempts(self):
        expires = _utcnow() + timedelta(minutes=10)
        self.repo.create(
            request_id="otp_inc", phone_number="+1", otp_digest="d", expires_at=expires
        )
        count = self.repo.increment_attempts("otp_inc")
        self.assertEqual(count, 1)
        count2 = self.repo.increment_attempts("otp_inc")
        self.assertEqual(count2, 2)
        row = self.repo.get("otp_inc")
        self.assertEqual(row["attempts"], 2)

    def test_increment_missing_returns_zero(self):
        self.assertEqual(self.repo.increment_attempts("missing"), 0)

    def test_delete(self):
        expires = _utcnow() + timedelta(minutes=10)
        self.repo.create(
            request_id="otp_del", phone_number="+1", otp_digest="d", expires_at=expires
        )
        self.assertIsNotNone(self.repo.get("otp_del"))
        self.repo.delete("otp_del")
        self.assertIsNone(self.repo.get("otp_del"))

    def test_delete_missing_is_noop(self):
        self.repo.delete("nope")  # should not raise

    def test_cleanup_expired_removes_stale(self):
        past = _utcnow() - timedelta(minutes=5)
        future = _utcnow() + timedelta(minutes=5)
        self.repo.create(request_id="otp_past", phone_number="+1", otp_digest="d", expires_at=past)
        self.repo.create(
            request_id="otp_future", phone_number="+2", otp_digest="d", expires_at=future
        )
        deleted = self.repo.cleanup_expired()
        self.assertEqual(deleted, 1)
        self.assertIsNone(self.repo.get("otp_past"))
        self.assertIsNotNone(self.repo.get("otp_future"))

    def test_cleanup_no_expired_returns_zero(self):
        future = _utcnow() + timedelta(minutes=5)
        self.repo.create(request_id="otp_ok", phone_number="+1", otp_digest="d", expires_at=future)
        self.assertEqual(self.repo.cleanup_expired(), 0)


class TestSpotifyTokenRepository(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        self.db = _make_db()
        self.db.create_tables()
        self.repo = SpotifyTokenRepository(db=self.db)

    def test_upsert_creates_new(self):
        token = self.repo.upsert(
            "user_key_1",
            access_token="at_abc",
            refresh_token="rt_xyz",
            scope="streaming",
            spotify_user_id="sp_001",
            display_name="Dana",
            spotify_email="dana@example.com",
            expires_at="2026-12-31T00:00:00Z",
        )
        self.assertEqual(token["access_token"], "at_abc")
        self.assertEqual(token["spotify_user_id"], "sp_001")
        self.assertEqual(token["display_name"], "Dana")

    def test_get_returns_token(self):
        self.repo.upsert("user_k2", access_token="at_2", expires_at="2026-01-01T00:00:00Z")
        got = self.repo.get("user_k2")
        self.assertIsNotNone(got)
        self.assertEqual(got["access_token"], "at_2")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.repo.get("unknown_user"))

    def test_upsert_updates_existing(self):
        self.repo.upsert("user_k3", access_token="old_at", expires_at="2025-01-01T00:00:00Z")
        self.repo.upsert("user_k3", access_token="new_at", expires_at="2027-01-01T00:00:00Z")
        got = self.repo.get("user_k3")
        self.assertEqual(got["access_token"], "new_at")
        self.assertEqual(got["expires_at"], "2027-01-01T00:00:00Z")

    def test_update_access_token(self):
        self.repo.upsert("user_k4", access_token="orig", expires_at="2025-01-01T00:00:00Z")
        self.repo.update_access_token(
            "user_k4", access_token="refreshed_at", expires_at="2027-01-01T00:00:00Z"
        )
        got = self.repo.get("user_k4")
        self.assertEqual(got["access_token"], "refreshed_at")
        self.assertEqual(got["expires_at"], "2027-01-01T00:00:00Z")

    def test_update_access_token_missing_is_noop(self):
        self.repo.update_access_token("nope", access_token="x", expires_at="y")  # should not raise

    def test_delete(self):
        self.repo.upsert("user_k5", access_token="x", expires_at="2027-01-01T00:00:00Z")
        self.assertIsNotNone(self.repo.get("user_k5"))
        self.repo.delete("user_k5")
        self.assertIsNone(self.repo.get("user_k5"))

    def test_delete_missing_is_noop(self):
        self.repo.delete("nonexistent")  # should not raise

    def test_upsert_preserves_refresh_token_on_update(self):
        self.repo.upsert(
            "user_k6", access_token="a", refresh_token="rt_keep", expires_at="2026-01-01T00:00:00Z"
        )
        self.repo.upsert("user_k6", access_token="a2", expires_at="2027-01-01T00:00:00Z")
        got = self.repo.get("user_k6")
        self.assertEqual(got["refresh_token"], "rt_keep")


if __name__ == "__main__":
    unittest.main()
