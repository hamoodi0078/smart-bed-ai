import hashlib
import os
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
import qr_code.pair_device as qr_pair_device
import web_server


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


@contextmanager
def _noop_io_lock(_path):
    yield


class TestMobilePairingAndAlarmApi(unittest.TestCase):
    def setUp(self):
        base_tmp = Path.cwd() / ".tmp"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._tmp_dir = base_tmp / f"mobile_pairing_alarm_{uuid.uuid4().hex}"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self._tmp_dir / "subscription_db.json"
        self.profile_path = self._tmp_dir / "user_profile.json"
        self._sqlite_path = self._tmp_dir / "mobile_pairing_alarm.sqlite3"
        self._database_url = f"sqlite:///{self._sqlite_path.as_posix()}"

        self._io_lock_patch = patch("Storage.io._path_io_lock", _noop_io_lock)
        self._patch_env = patch.dict(
            os.environ,
            {"DATABASE_URL": self._database_url},
            clear=False,
        )
        self._io_lock_patch.start()
        self.store = SubscriptionStore(db_path=self.db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: stored_hash == _legacy_sha256(password)
        self._patch_store = patch.object(web_server, "store", self.store)
        self._patch_profile = patch.object(web_server, "PROFILE_PATH", self.profile_path)
        self._patch_env.start()
        self._patch_store.start()
        self._patch_profile.start()

        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_BETA_PROGRESS_REPOSITORY = None
        web_server._DB_EVENT_REPOSITORY = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None
        web_server._DB_MOBILE_AUTH_REPOSITORY = None

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
        self._io_lock_patch.stop()
        self._patch_profile.stop()
        self._patch_store.stop()
        self._patch_env.stop()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _register(self, email: str) -> tuple[dict[str, str], str]:
        response = self.client.post(
            "/v1/mobile/auth/register",
            json={
                "email": email,
                "password": "secret123",
                "name": "Pairing User",
                "client_name": "flutter_pairing",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        access_token = str(body.get("access_token", "") or "")
        self.assertTrue(access_token)
        user_id = str(body.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)
        return {"Authorization": f"Bearer {access_token}"}, user_id

    def test_mobile_pairing_and_unpair_contract(self):
        headers, user_id = self._register("pairing-user@example.com")
        device_id = "DANA-KW-001-ABCD"
        claim_token = "claim-token-123"

        with (
            patch.object(
                web_server,
                "_load_registered_qr_device",
                return_value={
                    "device_id": device_id,
                    "bed_location": "Kuwait",
                    "claim_token": claim_token,
                },
            ),
            patch.object(
                qr_pair_device,
                "pair_device",
                return_value={"success": True, "message": "paired"},
            ),
            patch.object(
                qr_pair_device,
                "get_device_status",
                side_effect=[
                    {
                        "success": True,
                        "device_id": device_id,
                        "paired": True,
                        "bed_location": "Kuwait",
                        "paired_at": "2026-03-18T10:00:00Z",
                        "user_id": user_id,
                    },
                    {
                        "success": True,
                        "device_id": device_id,
                        "paired": True,
                        "bed_location": "Kuwait",
                        "paired_at": "2026-03-18T10:00:00Z",
                        "user_id": user_id,
                    },
                    {
                        "success": True,
                        "device_id": device_id,
                        "paired": True,
                        "bed_location": "Kuwait",
                        "paired_at": "2026-03-18T10:00:00Z",
                        "user_id": user_id,
                    },
                ],
            ),
            patch.object(
                qr_pair_device,
                "unpair_device",
                return_value={"success": True, "message": "unpaired"},
            ),
        ):
            pair = self.client.post(
                "/v1/mobile/bed/pair",
                json={"device_id": device_id, "claim_token": claim_token},
                headers=headers,
            )
            self.assertEqual(pair.status_code, 200)
            pair_body = pair.json()
            self.assertTrue(pair_body.get("ok"))
            self.assertTrue(pair_body.get("paired"))
            self.assertEqual(pair_body.get("device_id"), device_id)
            self.assertTrue(bool(pair_body.get("provisioning_verified", False)))

            status = self.client.get("/v1/mobile/bed/pairing", headers=headers)
            self.assertEqual(status.status_code, 200)
            status_body = status.json()
            self.assertTrue(status_body.get("paired"))
            self.assertEqual(status_body.get("device_id"), device_id)

            unpair = self.client.post(
                "/v1/mobile/bed/unpair",
                json={"device_id": device_id},
                headers=headers,
            )
            self.assertEqual(unpair.status_code, 200)
            self.assertTrue(unpair.json().get("ok"))

    def test_mobile_pairing_rejects_invalid_claim_token(self):
        headers, _ = self._register("pairing-claim@example.com")
        device_id = "DANA-KW-001-CLM1"
        with (
            patch.object(
                web_server,
                "_load_registered_qr_device",
                return_value={
                    "device_id": device_id,
                    "bed_location": "Kuwait",
                    "claim_token": "expected-claim-token",
                },
            ),
            patch.object(
                qr_pair_device,
                "pair_device",
                return_value={"success": True, "message": "paired"},
            ),
            patch.object(
                qr_pair_device,
                "get_device_status",
                return_value={
                    "success": True,
                    "device_id": device_id,
                    "paired": False,
                    "bed_location": "Kuwait",
                },
            ),
        ):
            rejected = self.client.post(
                "/v1/mobile/bed/pair",
                json={"device_id": device_id, "claim_token": "wrong-token"},
                headers=headers,
            )
            self.assertEqual(rejected.status_code, 401)

    def test_mobile_alarm_crud_contract(self):
        headers, _ = self._register("alarm-user@example.com")

        create = self.client.post(
            "/v1/mobile/alarms",
            json={
                "time": "06:30",
                "days": [1, 2, 3, 4, 5],
                "enabled": True,
                "label": "Weekday wake",
            },
            headers=headers,
        )
        self.assertEqual(create.status_code, 200)
        create_body = create.json()
        self.assertTrue(create_body.get("ok"))
        alarms = create_body.get("alarms", [])
        self.assertIsInstance(alarms, list)
        self.assertEqual(len(alarms), 1)
        alarm_id = str(alarms[0].get("alarm_id", "") or "")
        self.assertTrue(alarm_id)

        fetch = self.client.get("/v1/mobile/alarms", headers=headers)
        self.assertEqual(fetch.status_code, 200)
        fetched_alarms = fetch.json().get("alarms", [])
        self.assertEqual(len(fetched_alarms), 1)
        self.assertEqual(str(fetched_alarms[0].get("time", "")), "06:30")

        toggle = self.client.post(
            f"/v1/mobile/alarms/{alarm_id}/toggle",
            json={"enabled": False},
            headers=headers,
        )
        self.assertEqual(toggle.status_code, 200)
        self.assertTrue(toggle.json().get("ok"))

        remove = self.client.delete(
            f"/v1/mobile/alarms/{alarm_id}",
            headers=headers,
        )
        self.assertEqual(remove.status_code, 200)
        self.assertTrue(remove.json().get("ok"))

        fetch_after = self.client.get("/v1/mobile/alarms", headers=headers)
        self.assertEqual(fetch_after.status_code, 200)
        self.assertEqual(fetch_after.json().get("alarms", []), [])


if __name__ == "__main__":
    unittest.main()
