"""Billing/admin state must survive process restarts (Plan 8, campaign Phase 2).

The JSON store is a per-process file; on ephemeral container filesystems a
redeploy erases checkout sessions, webhook idempotency, payment history,
subscription tiers and admin sessions. These tests simulate a restart by
building a SECOND SubscriptionStore on a fresh JSON path that shares only the
DATABASE_URL with the first — anything the second store can't see was never
durable.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from Storage.subscription_store import SubscriptionStore


class BillingDbPersistenceCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        self._env = patch.dict(
            os.environ,
            {"DATABASE_URL": f"sqlite:///{(tmp / 'test.sqlite3').as_posix()}"},
            clear=False,
        )
        self._env.start()
        from database.connection import get_shared_connection, reset_shared_connection

        reset_shared_connection()
        get_shared_connection().create_tables()

    def tearDown(self):
        from database.connection import reset_shared_connection

        reset_shared_connection()
        self._env.stop()
        self._tmp.cleanup()

    def fresh_store(self, name: str) -> SubscriptionStore:
        return SubscriptionStore(db_path=Path(self._tmp.name) / f"{name}.json")


class CheckoutPersistenceTests(BillingDbPersistenceCase):
    def test_checkout_session_survives_process_restart(self):
        store_a = self.fresh_store("a")
        checkout = store_a.create_checkout_session(
            user_id="user-chk-1", tier="standard", interval="monthly"
        )
        session_id = checkout["session_id"]
        updated = store_a.update_checkout_session(
            session_id, status="approved", provider_order_id="ORD-1"
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "approved")

        store_b = self.fresh_store("b")
        found = store_b.get_checkout_session(session_id)
        self.assertIsNotNone(found, "checkout session must survive a restart")
        self.assertEqual(found["status"], "approved")
        self.assertEqual(found["user_id"], "user-chk-1")
        by_order = store_b.get_checkout_session_by_provider_order_id("ORD-1")
        self.assertIsNotNone(by_order)
        self.assertEqual(by_order["session_id"], session_id)


class PaymentEventPersistenceTests(BillingDbPersistenceCase):
    def test_payment_events_and_subscription_survive_process_restart(self):
        store_a = self.fresh_store("a")
        store_a.apply_billing_webhook(
            event_type="payment.succeeded",
            user_id="user-evt-1",
            tier="standard",
            interval="monthly",
        )
        self.assertEqual(store_a.get_subscription("user-evt-1")["tier"], "standard")

        store_b = self.fresh_store("b")
        events = store_b.list_payment_events("user-evt-1")
        self.assertTrue(events, "payment events must survive a restart")
        self.assertEqual(events[0]["event_type"], "payment.succeeded")
        # Hydration: the tier must come back from the DB even though B's JSON
        # file has never seen this user.
        self.assertEqual(store_b.get_subscription("user-evt-1")["tier"], "standard")


class WebhookReceiptPersistenceTests(BillingDbPersistenceCase):
    def test_webhook_receipts_survive_process_restart(self):
        store_a = self.fresh_store("a")
        store_a.remember_billing_webhook_receipt(
            idempotency_key="idem-1",
            event_type="payment.succeeded",
            user_id="user-rcpt-1",
            event_id="evt-1",
        )
        store_a.remember_billing_webhook_replay(
            replay_key="replay-1", transmission_id="tx-1", event_id="evt-1"
        )

        store_b = self.fresh_store("b")
        receipt = store_b.get_billing_webhook_receipt("idem-1")
        self.assertIsNotNone(receipt, "idempotency receipt must survive a restart")
        self.assertEqual(receipt["event_type"], "payment.succeeded")
        replay = store_b.get_billing_webhook_replay("replay-1")
        self.assertIsNotNone(replay, "replay receipt must survive a restart")
        self.assertEqual(replay["transmission_id"], "tx-1")

        # Fresh receipts survive a prune with a normal TTL...
        result = store_b.prune_billing_webhook_memory(max_age_seconds=3600)
        self.assertEqual(result["removed_idempotency"], 0)
        self.assertIsNotNone(store_b.get_billing_webhook_receipt("idem-1"))

        # ...and a prune that treats everything as expired removes them from
        # the DB too — a THIRD store must not resurrect them.
        far_future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        with patch.object(
            SubscriptionStore, "_utc_now", new=staticmethod(lambda: far_future)
        ):
            store_b.prune_billing_webhook_memory(max_age_seconds=60)
        store_c = self.fresh_store("c")
        self.assertIsNone(store_c.get_billing_webhook_receipt("idem-1"))
        self.assertIsNone(store_c.get_billing_webhook_replay("replay-1"))


class AdminSessionPersistenceTests(BillingDbPersistenceCase):
    def test_admin_session_survives_process_restart(self):
        store_a = self.fresh_store("a")
        store_a.upsert_admin_user(
            user_id="user-adm-1", email="admin@example.com", role="admin"
        )
        session = store_a.issue_admin_token(user_id="user-adm-1", role="admin")
        token = session["access_token"]
        self.assertIsNotNone(store_a.validate_admin_token(token))

        store_b = self.fresh_store("b")
        # admin_users stay JSON (out of Plan 8 scope) — seed the user row in
        # B; the SESSION is what must come back from the DB.
        store_b.upsert_admin_user(
            user_id="user-adm-1", email="admin@example.com", role="admin"
        )
        payload = store_b.validate_admin_token(token)
        self.assertIsNotNone(payload, "admin session must survive a restart")
        self.assertEqual(payload["user_id"], "user-adm-1")


class NoDatabaseFallbackTests(unittest.TestCase):
    """Without DATABASE_URL every flow must behave exactly as today (JSON only)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        self._env = patch.dict(os.environ, env, clear=True)
        self._env.start()
        from database.connection import reset_shared_connection

        reset_shared_connection()

    def tearDown(self):
        from database.connection import reset_shared_connection

        reset_shared_connection()
        self._env.stop()
        self._tmp.cleanup()

    def test_json_only_flows_work_without_database_url(self):
        store = SubscriptionStore(db_path=Path(self._tmp.name) / "solo.json")
        checkout = store.create_checkout_session(
            user_id="user-solo", tier="pro", interval="yearly"
        )
        self.assertIsNotNone(store.get_checkout_session(checkout["session_id"]))
        store.apply_billing_webhook(
            event_type="payment.succeeded", user_id="user-solo", tier="pro"
        )
        self.assertEqual(store.get_subscription("user-solo")["tier"], "pro")
        self.assertTrue(store.list_payment_events("user-solo"))
        store.remember_billing_webhook_receipt(
            idempotency_key="idem-solo", event_type="payment.succeeded", user_id="user-solo"
        )
        self.assertIsNotNone(store.get_billing_webhook_receipt("idem-solo"))


if __name__ == "__main__":
    unittest.main()
