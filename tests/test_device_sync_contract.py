"""Contract tests for the device command bridge (app -> cloud -> bed).

Drives the PRODUCTION app (api.app_factory:app), like
tests/test_app_factory_contract.py. Device-facing routes authenticate with a
device JWT (role="device"), never the mobile user JWT.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tests.test_app_factory_contract import AppFactoryContractCase

_QR_OK = {"success": True, "user_id": "", "bed_location": "Kuwait", "paired_at": ""}


class DeviceBridgeContractCase(AppFactoryContractCase):
    """Adds profile-store isolation + device helpers on top of the base fixture."""

    def setUp(self):
        super().setUp()
        import web_server

        profile_path = Path(self._tmp.name) / "profile.json"
        profile_path.write_text("{}", encoding="utf-8")
        self._profile_patcher = patch.object(web_server, "PROFILE_PATH", profile_path)
        self._profile_patcher.start()

    def tearDown(self):
        self._profile_patcher.stop()
        super().tearDown()

    # ── device helpers ────────────────────────────────────────────────────

    def device_token(self, device_id: str) -> dict:
        with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
            resp = self.client.post(
                "/v1/device/auth",
                json={"device_id": device_id, "firmware_version": "1.0.0", "factory_secret": ""},
            )
        assert resp.status_code == 200, f"device auth failed: {resp.text}"
        return resp.json()

    def device_bearer(self, bundle: dict) -> dict:
        return {"Authorization": f"Bearer {bundle['device_access_token']}"}

    def pair_bed(self, auth: dict, device_id: str) -> str:
        """Pair a bed through the real API (QR service patched); return the profile key."""
        import web_server

        with (
            patch.object(
                web_server, "_load_registered_qr_device", return_value={"device_id": device_id}
            ),
            patch.object(web_server, "_pairing_claim_matches_device", return_value=True),
            patch("qr_code.pair_device.pair_device", return_value={"success": True}),
            patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)),
        ):
            resp = self.client.post(
                "/v1/mobile/bed/pair",
                json={"device_id": device_id, "qr_payload": "", "claim_token": ""},
                headers=self.bearer(auth),
            )
        assert resp.status_code == 200, f"pair failed: {resp.text}"
        profile = web_server._safe_profile()
        links = web_server._get_scoped_profile_section(profile, "mobile_bed_links")
        for key, row in links.items():
            if isinstance(row, dict) and str(row.get("device_id", "")) == device_id:
                return str(key)
        raise AssertionError("pairing did not create a bed link")


class DeviceAuthTests(DeviceBridgeContractCase):
    def test_device_auth_issues_token_bundle(self):
        bundle = self.device_token("bed-test-001")
        self.assertTrue(bundle["device_access_token"])
        self.assertTrue(bundle["refresh_token"])
        self.assertTrue(bundle["expires_at"])
        self.assertIn("entitlement", bundle)

    def test_device_auth_rejects_unprovisioned_device(self):
        with patch("qr_code.pair_device.get_device_status", return_value={"success": False}):
            resp = self.client.post(
                "/v1/device/auth",
                json={"device_id": "ghost-bed", "firmware_version": "1.0.0"},
            )
        self.assertEqual(resp.status_code, 404)

    def test_refresh_rotates_and_invalidates_old_token(self):
        bundle = self.device_token("bed-test-002")
        old_refresh = bundle["refresh_token"]
        resp = self.client.post(
            "/v1/device/token/refresh",
            json={"device_id": "bed-test-002", "refresh_token": old_refresh},
        )
        self.assertEqual(resp.status_code, 200)
        new_bundle = resp.json()
        self.assertNotEqual(new_bundle["refresh_token"], old_refresh)
        resp2 = self.client.post(
            "/v1/device/token/refresh",
            json={"device_id": "bed-test-002", "refresh_token": old_refresh},
        )
        self.assertEqual(resp2.status_code, 401)

    def test_device_token_rejected_on_mobile_route(self):
        bundle = self.device_token("bed-test-003")
        resp = self.client.get("/v1/mobile/dashboard", headers=self.device_bearer(bundle))
        self.assertEqual(resp.status_code, 401)
