import hashlib
import os
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock
import uuid

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
from subscriptions.billing import BillingService
from subscriptions.paypal_provider import (
    PayPalProvider,
    PayPalSubscriptionDetails,
    PayPalSubscriptionSession,
    PayPalWebhookVerification,
)
from time_utils import to_iso, utcnow
import web_server


@contextmanager
def _noop_io_lock(_path):
    yield


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


class TestBillingService(unittest.TestCase):
    def setUp(self):
        base_tmp = Path.cwd() / ".tmp"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._tmp_dir = base_tmp / f"billing_service_{uuid.uuid4().hex}"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self._tmp_dir / "subscription_db.json"
        self._io_lock_patch = unittest.mock.patch("Storage.io._path_io_lock", _noop_io_lock)
        self._io_lock_patch.start()
        self.store = SubscriptionStore(db_path=self.db_path)

    def tearDown(self):
        self._io_lock_patch.stop()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_checkout_falls_back_to_local_approval_when_paypal_is_unconfigured(self):
        service = BillingService(store=self.store, app_base_url="http://127.0.0.1:8000")

        checkout = service.create_checkout_session(
            user_id="usr_local",
            tier="standard",
            interval="monthly",
            return_url="http://localhost:62000/#/settings",
            cancel_url="http://localhost:62000/#/settings",
        )

        self.assertEqual(checkout.get("payment_provider"), "paypal_local")
        self.assertEqual(checkout.get("provider_environment"), "local_fallback")
        self.assertIn("/billing/paypal/approve?session_id=", str(checkout.get("approve_url", "")))

    def test_checkout_uses_paypal_provider_when_available(self):
        provider = Mock()
        provider.configured = True
        provider.environment = "sandbox"
        provider.currency_code = "USD"
        provider.create_subscription.return_value = PayPalSubscriptionSession(
            subscription_id="I-SUBSCRIPTION123",
            plan_id="P-STANDARD-MONTHLY",
            status="APPROVAL_PENDING",
            approve_url="https://www.sandbox.paypal.com/checkoutnow?ba_token=I-SUBSCRIPTION123",
            raw={"id": "I-SUBSCRIPTION123"},
        )
        service = BillingService(
            store=self.store,
            app_base_url="http://127.0.0.1:8000",
            paypal_provider=provider,
            paypal_plan_ids={("pro", "monthly"): "P-STANDARD-MONTHLY"},
        )

        checkout = service.create_checkout_session(
            user_id="usr_paypal",
            tier="pro",
            interval="monthly",
            return_url="http://localhost:62000/#/settings",
            cancel_url="http://localhost:62000/#/settings",
            payer_email="hamoud@example.com",
        )

        self.assertEqual(checkout.get("provider_subscription_id"), "I-SUBSCRIPTION123")
        self.assertEqual(checkout.get("status"), "approval_pending")
        self.assertEqual(
            checkout.get("approve_url"),
            "https://www.sandbox.paypal.com/checkoutnow?ba_token=I-SUBSCRIPTION123",
        )
        provider.create_subscription.assert_called_once()

    def test_paypal_webhook_marks_subscription_active(self):
        provider = Mock()
        provider.configured = True
        provider.environment = "sandbox"
        provider.currency_code = "USD"
        provider.verify_webhook_signature.return_value = PayPalWebhookVerification(
            verified=True,
            status="SUCCESS",
            raw={"verification_status": "SUCCESS"},
        )
        service = BillingService(
            store=self.store,
            app_base_url="http://127.0.0.1:8000",
            paypal_provider=provider,
        )

        checkout = self.store.create_checkout_session(
            user_id="usr_webhook",
            tier="standard",
            interval="monthly",
            payment_provider="paypal",
            base_url="http://127.0.0.1:8000",
        )
        checkout["provider_subscription_id"] = "I-WEBHOOK"
        self.store.save()

        result = service.handle_paypal_webhook(
            headers={
                "PayPal-Transmission-Id": "abc",
                "PayPal-Transmission-Time": to_iso(utcnow().replace(microsecond=0)),
                "PayPal-Transmission-Sig": "sig",
                "PayPal-Cert-Url": "https://api-m.paypal.com/certs/cert.pem",
                "PayPal-Auth-Algo": "SHA256withRSA",
            },
            payload={
                "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                "resource": {
                    "id": "I-WEBHOOK",
                    "status": "ACTIVE",
                    "plan_id": "P-STANDARD-MONTHLY",
                    "billing_info": {
                        "next_billing_time": "2026-04-15T12:00:00Z",
                    },
                },
            },
        )

        self.assertEqual(result.user_id, "usr_webhook")
        self.assertTrue(result.verified)

        subscription = self.store.get_subscription("usr_webhook")
        self.assertIsNotNone(subscription)
        assert subscription is not None
        self.assertEqual(subscription.get("tier"), "standard")

        session = self.store.get_checkout_session(checkout["session_id"])
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.get("status"), "completed")


class _FakePayPalProvider(PayPalProvider):
    configured = True
    environment = "sandbox"
    currency_code = "USD"
    _status_map: dict[str, str]

    def __init__(self) -> None:
        super().__init__(
            client_id="fake_id",
            client_secret="fake_secret",
            api_base="https://api-m.sandbox.paypal.com",
            webhook_id="fake_webhook_id",
            brand_name="fake_brand",
            currency_code="USD",
        )
        self._status_map = {"I-ENDPOINT": "ACTIVE"}

    def create_subscription(
        self,
        *,
        session_id: str,
        plan_id: str,
        return_url: str,
        cancel_url: str,
        payer_email: str = "",
    ) -> PayPalSubscriptionSession:
        return PayPalSubscriptionSession(
            subscription_id="I-ENDPOINT",
            plan_id=plan_id,
            status="APPROVAL_PENDING",
            approve_url="https://www.sandbox.paypal.com/checkoutnow?ba_token=I-ENDPOINT",
            raw={
                "id": "I-ENDPOINT",
                "session_id": session_id,
                "plan_id": plan_id,
                "return_url": return_url,
                "cancel_url": cancel_url,
                "payer_email": payer_email,
            },
        )

    def get_subscription_details(self, subscription_id: str) -> PayPalSubscriptionDetails:
        status = self._status_map.get(subscription_id, "ACTIVE")
        return PayPalSubscriptionDetails(
            subscription_id=subscription_id,
            plan_id="P-STANDARD-MONTHLY",
            status=status,
            next_billing_time="2026-04-16T12:00:00Z",
            status_update_time="2026-03-16T12:00:00Z",
            raw={
                "id": subscription_id,
                "status": status,
                "plan_id": "P-STANDARD-MONTHLY",
                "billing_info": {
                    "next_billing_time": "2026-04-16T12:00:00Z",
                },
                "status_update_time": "2026-03-16T12:00:00Z",
            },
        )

    def suspend_subscription(self, subscription_id: str, *, reason: str = "Paused by user") -> None:
        self._status_map[str(subscription_id or "").strip()] = "SUSPENDED"

    def cancel_subscription(
        self, subscription_id: str, *, reason: str = "Cancelled by user"
    ) -> None:
        self._status_map[str(subscription_id or "").strip()] = "CANCELLED"

    def verify_webhook_signature(self, *, headers, payload) -> PayPalWebhookVerification:
        return PayPalWebhookVerification(
            verified=True,
            status="SUCCESS",
            raw={"verification_status": "SUCCESS"},
        )


class _FakeUserRecord:
    def __init__(
        self,
        *,
        user_id: str,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        subscription_status: str = "free",
    ) -> None:
        self.id = user_id
        self.email = email
        self.password_hash = password_hash
        self.full_name = full_name
        self.subscription_status = subscription_status


class _FakeUserRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, _FakeUserRecord] = {}
        self._by_email: dict[str, _FakeUserRecord] = {}

    def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        user_id: str | None = None,
    ) -> _FakeUserRecord:
        record = _FakeUserRecord(
            user_id=user_id or f"usr_{uuid.uuid4().hex[:8]}",
            email=email,
            password_hash=password_hash,
            full_name=full_name,
        )
        self._by_id[record.id] = record
        self._by_email[record.email] = record
        return record

    def get_user_by_email(self, email: str):
        return self._by_email.get(str(email or "").strip().lower())

    def get_user_by_id(self, user_id: str):
        return self._by_id.get(str(user_id or "").strip())

    def update_subscription(self, user_id: str, status: str):
        record = self.get_user_by_id(user_id)
        if record is not None:
            record.subscription_status = status
        return record


class _FakeMobileAuthRepository:
    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, str]] = {}

    def issue_tokens(self, *, user_id: str, client_name: str = "") -> dict[str, str | int]:
        access_token = f"access_{uuid.uuid4().hex}"
        refresh_token = f"refresh_{uuid.uuid4().hex}"
        self._tokens[access_token] = {
            "user_id": user_id,
            "client_name": client_name,
        }
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_at": "2099-01-01T00:00:00Z",
            "expires_in": 3600,
            "refresh_token": refresh_token,
            "refresh_expires_at": "2099-02-01T00:00:00Z",
            "client_name": client_name,
        }

    def validate_access_token(self, token: str) -> dict[str, str]:
        return dict(self._tokens.get(str(token or "").strip(), {}))


class TestMobileBillingEndpoints(unittest.TestCase):
    def setUp(self):
        base_tmp = Path.cwd() / ".tmp"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._tmp_dir = base_tmp / f"billing_endpoint_{uuid.uuid4().hex}"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._subscription_db_path = self._tmp_dir / "subscription_db.json"
        self._profile_path = self._tmp_dir / "user_profile.json"
        self._sqlite_path = self._tmp_dir / "mobile_billing.sqlite3"
        self._database_url = f"sqlite:///{self._sqlite_path.as_posix()}"
        self._fake_user_repo = _FakeUserRepository()
        self._fake_mobile_auth_repo = _FakeMobileAuthRepository()

        self._io_lock_patch = unittest.mock.patch("Storage.io._path_io_lock", _noop_io_lock)
        self._io_lock_patch.start()
        self.store = SubscriptionStore(db_path=self._subscription_db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: (
            stored_hash == _legacy_sha256(password)
        )

        self._env_patch = unittest.mock.patch.dict(
            os.environ,
            {"DATABASE_URL": self._database_url},
            clear=False,
        )
        self._patch_store = unittest.mock.patch.object(web_server, "store", self.store)
        self._patch_profile = unittest.mock.patch.object(
            web_server, "PROFILE_PATH", self._profile_path
        )
        self._patch_user_repo = unittest.mock.patch.object(
            web_server,
            "_db_user_repository",
            lambda: self._fake_user_repo,
        )
        self._patch_mobile_auth_repo = unittest.mock.patch.object(
            web_server,
            "_db_mobile_auth_repository",
            lambda: self._fake_mobile_auth_repo,
        )

        self._env_patch.start()
        self._patch_store.start()
        self._patch_profile.start()
        self._patch_user_repo.start()
        self._patch_mobile_auth_repo.start()

        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_BETA_PROGRESS_REPOSITORY = None
        web_server._DB_EVENT_REPOSITORY = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None
        web_server._DB_MOBILE_AUTH_REPOSITORY = None
        web_server._BILLING_SERVICE = BillingService(
            store=self.store,
            app_base_url="http://testserver",
            paypal_provider=_FakePayPalProvider(),
            paypal_plan_ids={("standard", "monthly"): "P-STANDARD-MONTHLY"},
        )
        self.client = TestClient(web_server.app)

    def tearDown(self):
        connection = getattr(web_server, "_DB_CONNECTION", None)
        if connection is not None:
            try:
                connection.engine.dispose()
            except Exception:
                pass
        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_BETA_PROGRESS_REPOSITORY = None
        web_server._DB_EVENT_REPOSITORY = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None
        web_server._DB_MOBILE_AUTH_REPOSITORY = None
        web_server._BILLING_SERVICE = None
        self._io_lock_patch.stop()
        self._patch_mobile_auth_repo.stop()
        self._patch_user_repo.stop()
        self._patch_profile.stop()
        self._patch_store.stop()
        self._env_patch.stop()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _register(self, email: str) -> tuple[dict, dict[str, str]]:
        response = self.client.post(
            "/v1/mobile/auth/register",
            json={
                "email": email,
                "password": "Secret1234",
                "name": "Billing User",
                "client_name": "flutter_billing",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        access_token = str(body.get("access_token", "") or "")
        self.assertTrue(access_token)
        headers = {"Authorization": f"Bearer {access_token}"}
        return body, headers

    @staticmethod
    def _paypal_headers(transmission_id: str) -> dict[str, str]:
        return {
            "PayPal-Transmission-Id": str(transmission_id or "").strip(),
            "PayPal-Transmission-Time": to_iso(utcnow().replace(microsecond=0)),
            "PayPal-Transmission-Sig": "sig",
            "PayPal-Cert-Url": "https://api-m.sandbox.paypal.com/certs/cert.pem",
            "PayPal-Auth-Algo": "SHA256withRSA",
        }

    def test_mobile_checkout_redirect_flow_marks_subscription_premium(self):
        register_body, headers = self._register("billing-flow@example.com")
        user_id = str(register_body.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)

        checkout_response = self.client.post(
            "/v1/mobile/subscription/checkout",
            json={
                "tier": "standard",
                "interval": "monthly",
                "return_url": "http://localhost:62000/#/settings",
                "cancel_url": "http://localhost:62000/#/settings",
            },
            headers=headers,
        )
        self.assertEqual(checkout_response.status_code, 200)
        checkout_body = checkout_response.json()
        session_id = str(checkout_body.get("checkout", {}).get("session_id", "") or "")
        self.assertTrue(session_id)
        self.assertEqual(
            checkout_body.get("checkout", {}).get("approve_url"),
            "https://www.sandbox.paypal.com/checkoutnow?ba_token=I-ENDPOINT",
        )

        approve_response = self.client.get(
            f"/billing/paypal/approve?session_id={session_id}&ba_token=I-ENDPOINT&PayerID=PAYER123",
            follow_redirects=False,
        )
        self.assertEqual(approve_response.status_code, 302)
        self.assertIn("payment=success", str(approve_response.headers.get("location", "")))

        subscription = self.store.get_subscription(user_id)
        self.assertIsNotNone(subscription)
        assert subscription is not None
        self.assertEqual(subscription.get("tier"), "standard")
        self.assertEqual(subscription.get("payment_provider"), "paypal")

        checkout = self.store.get_checkout_session(session_id)
        self.assertIsNotNone(checkout)
        assert checkout is not None
        self.assertEqual(checkout.get("status"), "completed")
        self.assertEqual(checkout.get("provider_subscription_id"), "I-ENDPOINT")

    def test_mobile_pause_and_cancel_active_subscription(self):
        register_body, headers = self._register("billing-actions@example.com")
        user_id = str(register_body.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)

        checkout_response = self.client.post(
            "/v1/mobile/subscription/checkout",
            json={
                "tier": "standard",
                "interval": "monthly",
                "return_url": "http://localhost:62000/#/settings",
                "cancel_url": "http://localhost:62000/#/settings",
            },
            headers=headers,
        )
        self.assertEqual(checkout_response.status_code, 200)
        session_id = str(checkout_response.json().get("checkout", {}).get("session_id", "") or "")
        self.assertTrue(session_id)

        approve_response = self.client.get(
            f"/billing/paypal/approve?session_id={session_id}&ba_token=I-ENDPOINT&PayerID=PAYER123",
            follow_redirects=False,
        )
        self.assertEqual(approve_response.status_code, 302)

        pause_response = self.client.post(
            "/v1/mobile/subscription/pause",
            json={"reason": "Testing pause flow"},
            headers=headers,
        )
        self.assertEqual(pause_response.status_code, 200)
        pause_body = pause_response.json()
        self.assertEqual(str(pause_body.get("status", "")).lower(), "paused")
        self.assertEqual(str(pause_body.get("provider_status", "")).upper(), "SUSPENDED")

        cancel_response = self.client.post(
            "/v1/mobile/subscription/cancel-active",
            json={"reason": "Testing cancel flow"},
            headers=headers,
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_body = cancel_response.json()
        self.assertEqual(str(cancel_body.get("status", "")).lower(), "inactive")
        self.assertEqual(str(cancel_body.get("plan_tier", "")).lower(), "free")

    def test_mobile_subscription_history_returns_stored_payment_events(self):
        register_body, headers = self._register("billing-history@example.com")
        user_id = str(register_body.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)

        checkout_response = self.client.post(
            "/v1/mobile/subscription/checkout",
            json={
                "tier": "standard",
                "interval": "monthly",
                "return_url": "http://localhost:62000/#/settings",
                "cancel_url": "http://localhost:62000/#/settings",
            },
            headers=headers,
        )
        self.assertEqual(checkout_response.status_code, 200)
        session_id = str(checkout_response.json().get("checkout", {}).get("session_id", "") or "")
        self.assertTrue(session_id)

        approve_response = self.client.get(
            f"/billing/paypal/approve?session_id={session_id}&ba_token=I-ENDPOINT&PayerID=PAYER123",
            follow_redirects=False,
        )
        self.assertEqual(approve_response.status_code, 302)

        pause_response = self.client.post(
            "/v1/mobile/subscription/pause",
            json={"reason": "History pause"},
            headers=headers,
        )
        self.assertEqual(pause_response.status_code, 200)

        history_response = self.client.get(
            "/v1/mobile/subscription/history?limit=12",
            headers=headers,
        )
        self.assertEqual(history_response.status_code, 200)
        body = history_response.json()
        self.assertTrue(body.get("ok"))
        events = body.get("events", [])
        self.assertIsInstance(events, list)
        self.assertGreaterEqual(len(events), 2)
        event_types = {
            str(event.get("event_type", "")).lower() for event in events if isinstance(event, dict)
        }
        self.assertIn("billing.subscription.activated", event_types)
        self.assertIn("billing.subscription.suspended", event_types)

    def test_paypal_webhook_duplicate_event_is_idempotent(self):
        register_body, headers = self._register("billing-webhook-dedupe@example.com")
        user_id = str(register_body.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)

        checkout_response = self.client.post(
            "/v1/mobile/subscription/checkout",
            json={
                "tier": "standard",
                "interval": "monthly",
                "return_url": "http://localhost:62000/#/settings",
                "cancel_url": "http://localhost:62000/#/settings",
            },
            headers=headers,
        )
        self.assertEqual(checkout_response.status_code, 200)
        payload = {
            "id": "WH-EVENT-DEDUPE-1",
            "event_type": "BILLING.SUBSCRIPTION.RENEWED",
            "resource": {
                "id": "I-ENDPOINT",
                "status": "ACTIVE",
                "plan_id": "P-STANDARD-MONTHLY",
                "billing_info": {
                    "next_billing_time": "2026-05-16T12:00:00Z",
                },
            },
        }

        first = self.client.post(
            "/v1/billing/paypal/webhook",
            json=payload,
            headers=self._paypal_headers("tx-dedupe-1"),
        )
        self.assertEqual(first.status_code, 200)
        first_body = first.json()
        self.assertFalse(bool(first_body.get("duplicate")))

        second = self.client.post(
            "/v1/billing/paypal/webhook",
            json=payload,
            headers=self._paypal_headers("tx-dedupe-2"),
        )
        self.assertEqual(second.status_code, 200)
        second_body = second.json()
        self.assertTrue(bool(second_body.get("duplicate")))

        events = self.store.list_payment_events(user_id, limit=30)
        renewed_events = [
            row
            for row in events
            if str(row.get("event_type", "")).lower() == "billing.subscription.renewed"
        ]
        self.assertEqual(len(renewed_events), 1)

    def test_paypal_webhook_replay_transmission_is_rejected(self):
        _register_body, headers = self._register("billing-webhook-replay@example.com")
        checkout_response = self.client.post(
            "/v1/mobile/subscription/checkout",
            json={
                "tier": "standard",
                "interval": "monthly",
                "return_url": "http://localhost:62000/#/settings",
                "cancel_url": "http://localhost:62000/#/settings",
            },
            headers=headers,
        )
        self.assertEqual(checkout_response.status_code, 200)

        tx_id = "tx-replay-1"
        first_payload = {
            "id": "WH-REPLAY-1",
            "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
            "resource": {
                "id": "I-ENDPOINT",
                "status": "ACTIVE",
                "plan_id": "P-STANDARD-MONTHLY",
            },
        }
        second_payload = {
            "id": "WH-REPLAY-2",
            "event_type": "BILLING.SUBSCRIPTION.RENEWED",
            "resource": {
                "id": "I-ENDPOINT",
                "status": "ACTIVE",
                "plan_id": "P-STANDARD-MONTHLY",
            },
        }

        first = self.client.post(
            "/v1/billing/paypal/webhook",
            json=first_payload,
            headers=self._paypal_headers(tx_id),
        )
        self.assertEqual(first.status_code, 200)

        replay = self.client.post(
            "/v1/billing/paypal/webhook",
            json=second_payload,
            headers=self._paypal_headers(tx_id),
        )
        self.assertEqual(replay.status_code, 400)
        json_body = (
            replay.json()
            if replay.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        body = json_body if isinstance(json_body, dict) else {}
        detail = str(body.get("detail", "")).lower()
        if not detail:
            err_val = body.get("error")
            detail = str(err_val.get("message", "")).lower() if isinstance(err_val, dict) else ""
        if not detail:
            detail = replay.text.lower()
        self.assertIn("replay", detail)

    def test_admin_billing_timeline_returns_feed(self):
        register_body, headers = self._register("billing-admin-feed@example.com")
        user_id = str(register_body.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)

        checkout_response = self.client.post(
            "/v1/mobile/subscription/checkout",
            json={
                "tier": "standard",
                "interval": "monthly",
                "return_url": "http://localhost:62000/#/settings",
                "cancel_url": "http://localhost:62000/#/settings",
            },
            headers=headers,
        )
        self.assertEqual(checkout_response.status_code, 200)

        webhook_payload = {
            "id": "WH-ADMIN-FEED-1",
            "event_type": "BILLING.SUBSCRIPTION.RENEWED",
            "resource": {
                "id": "I-ENDPOINT",
                "status": "ACTIVE",
                "plan_id": "P-STANDARD-MONTHLY",
            },
        }
        webhook = self.client.post(
            "/v1/billing/paypal/webhook",
            json=webhook_payload,
            headers=self._paypal_headers("tx-admin-feed-1"),
        )
        self.assertEqual(webhook.status_code, 200)

        admin_user = self.store.upsert_admin_user(
            user_id="admin_user_1",
            email="admin@example.com",
            role="admin",
            status="active",
        )
        admin_session = self.store.issue_admin_token(
            user_id=str(admin_user.get("user_id", "")),
            role="admin",
            ttl_hours=12,
        )
        self.client.cookies.set("sb_admin_token", str(admin_session.get("access_token", "")))

        response = self.client.get("/v1/admin/billing/timeline?limit=20")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        items = body.get("items", [])
        self.assertIsInstance(items, list)
        self.assertGreaterEqual(len(items), 1)
        summary = body.get("summary", {})
        self.assertGreaterEqual(int(summary.get("total_events", 0)), 1)


if __name__ == "__main__":
    unittest.main()
