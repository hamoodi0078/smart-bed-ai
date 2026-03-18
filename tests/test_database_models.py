import os
import unittest

from sqlalchemy import text

from database import Bed, DatabaseConnection, Event, SleepSession, User


class TestDatabaseModels(unittest.TestCase):
    def setUp(self):
        self._old_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite://"

    def tearDown(self):
        if self._old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._old_database_url

    def test_user_model_has_required_fields(self):
        fields = set(User.__table__.columns.keys())
        expected = {
            "id",
            "email",
            "password_hash",
            "full_name",
            "timezone",
            "locale",
            "subscription_status",
            "trial_start_date",
            "trial_end_date",
            "created_at",
            "updated_at",
        }
        self.assertTrue(expected.issubset(fields))

    def test_bed_model_has_required_fields(self):
        fields = set(Bed.__table__.columns.keys())
        expected = {
            "id",
            "device_id",
            "primary_user_id",
            "partner_user_id",
            "device_online",
            "last_seen",
            "firmware_version",
            "created_at",
        }
        self.assertTrue(expected.issubset(fields))

    def test_event_model_has_required_fields(self):
        fields = set(Event.__table__.columns.keys())
        expected = {"id", "user_id", "bed_id", "event_type", "metadata", "trace_id", "timestamp"}
        self.assertTrue(expected.issubset(fields))

    def test_sleep_session_model_has_required_fields(self):
        fields = set(SleepSession.__table__.columns.keys())
        expected = {
            "id",
            "user_id",
            "date",
            "bedtime",
            "wake_time",
            "total_sleep_minutes",
            "restlessness_score",
            "scenes_used",
            "automations_fired",
            "winddowns_completed",
            "created_at",
        }
        self.assertTrue(expected.issubset(fields))

    def test_database_connection_uses_sqlite_fallback_when_no_env(self):
        os.environ.pop("DATABASE_URL", None)
        db = DatabaseConnection(database_url="")
        self.assertEqual(db.database_url, "sqlite:///./data/manues.db")

    def test_health_check_returns_bool(self):
        db = DatabaseConnection()
        db.create_tables()
        result = db.health_check()
        self.assertIsInstance(result, bool)

    def test_create_tables_persists_schema_version_metadata(self):
        db = DatabaseConnection(database_url="sqlite://")
        db.create_tables()
        with db.engine.connect() as connection:
            stored = connection.execute(
                text(
                    "SELECT value FROM schema_meta WHERE key = :key"
                ),
                {"key": DatabaseConnection.SCHEMA_VERSION_KEY},
            ).scalar_one_or_none()
        self.assertEqual(int(str(stored or "0")), DatabaseConnection.CURRENT_SCHEMA_VERSION)
        self.assertEqual(db.schema_version(), DatabaseConnection.CURRENT_SCHEMA_VERSION)

    def test_create_tables_ensures_required_runtime_tables_exist(self):
        db = DatabaseConnection(database_url="sqlite://")
        db.create_tables()
        with db.engine.connect() as connection:
            names = {
                str(row[0])
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
            }
        self.assertIn("mobile_command_records", names)
        self.assertIn("mobile_auth_sessions", names)
        self.assertIn("beta_metrics_snapshots", names)


if __name__ == "__main__":
    unittest.main()
