import os
import unittest
from datetime import timedelta

from database import DatabaseConnection, UserRepository
from subscriptions import SubscriptionGate
from time_utils import utcnow


class TestSubscriptionGate(unittest.TestCase):
    def setUp(self):
        self._old_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite://"

        self.db = DatabaseConnection()
        self.db.create_tables()
        self.users = UserRepository(db=self.db)
        self.gate = SubscriptionGate(user_repo=self.users)
        self.free_user = self.users.create_user("free@example.com", "hash_free", "Free User")
        self.trial_user = self.users.create_user("trial@example.com", "hash_trial", "Trial User")

    def tearDown(self):
        if self._old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._old_database_url

    def test_non_premium_scene_always_allowed(self):
        result = self.gate.check_scene_access(
            user_id=self.free_user.id,
            scene_name="Cozy Night",
            scene_is_premium=False,
        )
        self.assertTrue(result.get("allowed"))
        self.assertEqual(result.get("reason"), "free_tier")

    def test_premium_scene_blocked_for_free_user(self):
        result = self.gate.check_scene_access(
            user_id=self.free_user.id,
            scene_name="Deep Sleep Pro",
            scene_is_premium=True,
        )
        self.assertFalse(result.get("allowed"))
        self.assertEqual(result.get("reason"), "premium_required")
        self.assertEqual(result.get("subscription_status"), "free")

    def test_premium_scene_allowed_during_trial(self):
        now = utcnow()
        self.users.update_subscription(
            user_id=self.trial_user.id,
            status="trial",
            trial_start=now - timedelta(days=1),
            trial_end=now + timedelta(days=3),
        )
        result = self.gate.check_scene_access(
            user_id=self.trial_user.id,
            scene_name="Premium Sleep Immersion",
            scene_is_premium=True,
        )
        self.assertTrue(result.get("allowed"))
        self.assertEqual(result.get("reason"), "trial_active")
        self.assertEqual(result.get("subscription_status"), "trial")

    def test_trial_expired_blocks_premium_scene(self):
        now = utcnow()
        self.users.update_subscription(
            user_id=self.trial_user.id,
            status="trial",
            trial_start=now - timedelta(days=10),
            trial_end=now - timedelta(days=3),
        )
        result = self.gate.check_scene_access(
            user_id=self.trial_user.id,
            scene_name="Premium Sleep Immersion",
            scene_is_premium=True,
        )
        self.assertFalse(result.get("allowed"))
        self.assertEqual(result.get("reason"), "premium_required")

    def test_trial_days_remaining_calculation(self):
        now = utcnow()
        user = self.users.update_subscription(
            user_id=self.trial_user.id,
            status="trial",
            trial_start=now - timedelta(days=1),
            trial_end=now + timedelta(days=5),
        )
        remaining = self.gate.get_trial_days_remaining(user)
        self.assertGreaterEqual(remaining, 6)

    def test_grace_period_extends_trial_two_days(self):
        now = utcnow()
        user = self.users.update_subscription(
            user_id=self.trial_user.id,
            status="trial",
            trial_start=now - timedelta(days=10),
            trial_end=now - timedelta(hours=12),
        )
        self.assertTrue(self.gate.is_trial_active(user))

        result = self.gate.check_scene_access(
            user_id=self.trial_user.id,
            scene_name="Premium Sleep Immersion",
            scene_is_premium=True,
        )
        self.assertTrue(result.get("allowed"))
        self.assertEqual(result.get("reason"), "trial_active")


if __name__ == "__main__":
    unittest.main()
