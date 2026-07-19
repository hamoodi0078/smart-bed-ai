"""Contract tests for the device command bridge (app -> cloud -> bed).

Drives the PRODUCTION app (api.app_factory:app), like
tests/test_app_factory_contract.py. Device-facing routes authenticate with a
device JWT (role="device"), never the mobile user JWT.
"""

from __future__ import annotations

import concurrent.futures
import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from time_utils import to_iso, utcnow

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
        # Hermetic env: the dev box's .env may set DANAH_ENV=production
        # (load_dotenv exports it), which would trip the device-auth
        # production gate in every test. Production-path tests set their
        # own env explicitly on top of this baseline.
        self._env_patcher = patch.dict(
            os.environ, {"DANAH_ENV": "development", "DEVICE_FACTORY_SECRET": ""}, clear=False
        )
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()
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
            # Pairing canonicalizes device ids (uppercase) — match that form.
            if isinstance(row, dict) and str(row.get("device_id", "")).upper() == device_id.upper():
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


class DeviceSyncTests(DeviceBridgeContractCase):
    def test_sync_unpaired_device_returns_empty(self):
        bundle = self.device_token("bed-sync-000")
        resp = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["commands"], [])
        self.assertIsNone(body["desired_state"])
        self.assertEqual(body["state_version"], "")

    def test_sync_returns_queued_command_once_and_marks_dispatched(self):
        auth = self.register("sync-cmd@example.com")
        device_id = "bed-sync-001"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)

        create = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "winddown"},
            headers=self.bearer(auth),
        )
        self.assertEqual(create.status_code, 200, create.text)
        command_id = create.json()["command_id"]
        self.assertTrue(command_id)

        first = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(first.status_code, 200)
        actions = {c["id"]: c["action"] for c in first.json()["commands"]}
        self.assertEqual(actions.get(command_id), "winddown")

        second = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(
            [c["id"] for c in second.json()["commands"]],
            [],
            "already-dispatched command must not be re-offered within 30s",
        )

    def test_sync_desired_state_reflects_controls_and_alarms(self):
        auth = self.register("sync-state@example.com")
        device_id = "bed-sync-002"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)

        controls = self.client.post(
            "/v1/mobile/device-controls",
            json={"lights_on": True, "audio_on": False, "alarm_on": True, "light_level": 33},
            headers=self.bearer(auth),
        )
        self.assertEqual(controls.status_code, 200, controls.text)
        alarm = self.client.post(
            "/v1/mobile/alarms",
            json={"time": "06:45", "days": [1, 2, 3], "label": "Fajr", "enabled": True},
            headers=self.bearer(auth),
        )
        self.assertEqual(alarm.status_code, 200, alarm.text)

        resp = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        body = resp.json()
        state = body["desired_state"]
        self.assertEqual(state["lighting"]["light_level"], 33)
        self.assertTrue(state["lighting"]["lights_on"])
        times = [a["time"] for a in state["alarms"]]
        self.assertIn("06:45", times)
        self.assertTrue(body["state_version"])

    def test_user_jwt_rejected_on_sync(self):
        auth = self.register("sync-boundary@example.com")
        resp = self.client.get("/v1/device/sync", headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 401)


class DeviceResultAndToggleTests(DeviceBridgeContractCase):
    def _seed_old_command(self, key: str, command_id: str, seconds_ago: int = 10) -> None:
        import web_server

        profile = web_server._safe_profile()
        old_iso = to_iso(utcnow() - timedelta(seconds=seconds_ago))
        section = web_server._get_scoped_profile_section(profile, "web_device_commands")
        section[key] = [
            {
                "id": command_id,
                "action": "winddown",
                "event": "Wind-down autopilot started",
                "message": "Wind-down autopilot is now active.",
                "status": "queued",
                "trace_id": "",
                "created_at": old_iso,
                "updated_at": old_iso,
                "completed_at": "",
            }
        ]
        profile["web_device_commands"] = section
        web_server._save_profile(profile)

    def test_real_result_reaches_mobile_status(self):
        auth = self.register("loop@example.com")
        device_id = "bed-loop-001"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)

        create = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "optimize_room"},
            headers=self.bearer(auth),
        )
        command_id = create.json()["command_id"]

        sync = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertIn(command_id, [c["id"] for c in sync.json()["commands"]])

        result = self.client.post(
            f"/v1/device/commands/{command_id}/result",
            json={"status": "completed", "detail": "Scene applied on bed.", "actual_state": {}},
            headers=self.device_bearer(bundle),
        )
        self.assertEqual(result.status_code, 200, result.text)

        status = self.client.get(
            f"/v1/mobile/device-commands/{command_id}", headers=self.bearer(auth)
        )
        self.assertEqual(status.json()["command"]["status"], "completed")

    def test_failed_result_marks_failed(self):
        auth = self.register("loop-fail@example.com")
        device_id = "bed-loop-002"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)
        create = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "winddown"},
            headers=self.bearer(auth),
        )
        command_id = create.json()["command_id"]
        self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.client.post(
            f"/v1/device/commands/{command_id}/result",
            json={"status": "failed", "detail": "LED bus unavailable"},
            headers=self.device_bearer(bundle),
        )
        status = self.client.get(
            f"/v1/mobile/device-commands/{command_id}", headers=self.bearer(auth)
        )
        self.assertEqual(status.json()["command"]["status"], "failed")

    def test_simulator_suppressed_while_bed_live(self):
        auth = self.register("toggle-live@example.com")
        device_id = "bed-toggle-001"
        key = self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)
        self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))  # last_seen = now

        self._seed_old_command(key, "cmd_toggle_live_1", seconds_ago=10)
        status = self.client.get(
            "/v1/mobile/device-commands/cmd_toggle_live_1", headers=self.bearer(auth)
        )
        self.assertNotIn(
            status.json()["command"]["status"],
            {"completed", "running"},
            "wall-clock simulator must not advance while the bed is live",
        )

    def test_simulator_advances_when_no_bed_live(self):
        auth = self.register("toggle-stale@example.com")
        device_id = "bed-toggle-002"
        key = self.pair_bed(auth, device_id)
        # No device sync — last_seen never stamped.
        self._seed_old_command(key, "cmd_toggle_stale_1", seconds_ago=10)
        status = self.client.get(
            "/v1/mobile/device-commands/cmd_toggle_stale_1", headers=self.bearer(auth)
        )
        self.assertEqual(status.json()["command"]["status"], "completed")

    def test_result_unknown_command_404(self):
        auth = self.register("loop-404@example.com")
        device_id = "bed-loop-404"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)
        resp = self.client.post(
            "/v1/device/commands/cmd_does_not_exist/result",
            json={"status": "completed"},
            headers=self.device_bearer(bundle),
        )
        self.assertEqual(resp.status_code, 404)


class DeviceSyncLockingTests(DeviceBridgeContractCase):
    """NEW-P0-A: the bridge's profile read-modify-write cycles must hold
    web_server._PROFILE_RW_LOCK — a bed polls every 2.5s and used to race
    every concurrent mobile profile write."""

    def test_sync_holds_profile_rw_lock_for_full_cycle(self):
        import web_server

        auth = self.register("bridge-lock@example.com")
        self.pair_bed(auth, "BED-LOCK-01")
        bundle = self.device_token("BED-LOCK-01")

        # Queue a command so the sync definitely persists (dispatch transition)
        resp = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "winddown"},
            headers=self.bearer(auth),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        real_save = web_server._save_profile
        probe_results: list[bool] = []

        def probing_save(payload):
            # Try to take the profile lock from ANOTHER thread mid-cycle.
            # If device_sync correctly wraps its cycle in _profile_rw(),
            # the lock is held and this acquire must fail.
            def try_acquire() -> bool:
                got = web_server._PROFILE_RW_LOCK.acquire(blocking=False)
                if got:
                    web_server._PROFILE_RW_LOCK.release()
                return got

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                probe_results.append(pool.submit(try_acquire).result())
            return real_save(payload)

        with patch.object(web_server, "_save_profile", side_effect=probing_save):
            resp = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(probe_results, "sync with a queued command must persist the profile")
        self.assertTrue(
            all(r is False for r in probe_results),
            "profile lock must be held across the whole read-modify-write cycle",
        )

    def test_sync_skips_redundant_profile_writes(self):
        import web_server

        auth = self.register("bridge-churn@example.com")
        self.pair_bed(auth, "BED-CHURN-01")
        bundle = self.device_token("BED-CHURN-01")
        headers = self.device_bearer(bundle)

        # First sync right after auth: last_seen is fresh, nothing queued.
        self.assertEqual(self.client.get("/v1/device/sync", headers=headers).status_code, 200)

        # Second sync seconds later: nothing changed -> must NOT rewrite the profile.
        with patch.object(web_server, "_save_profile") as save_spy:
            resp = self.client.get("/v1/device/sync", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        save_spy.assert_not_called()


class GetWriteOnReadLockingTests(DeviceBridgeContractCase):
    """Plan 8 Task 5: the dashboard/timeline GETs persist simulator state on
    read — those read-modify-write cycles must hold the profile RW lock or
    they race the 2.5s bed poll and every concurrent mobile write."""

    def _seed_old_queued_command(self, key: str, command_id: str) -> None:
        import web_server

        profile = web_server._safe_profile()
        old_iso = to_iso(utcnow() - timedelta(seconds=10))
        section = web_server._get_scoped_profile_section(profile, "web_device_commands")
        section[key] = [
            {
                "id": command_id,
                "action": "winddown",
                "event": "Wind-down autopilot started",
                "message": "Wind-down autopilot is now active.",
                "status": "queued",
                "trace_id": "",
                "created_at": old_iso,
                "updated_at": old_iso,
                "completed_at": "",
            }
        ]
        profile["web_device_commands"] = section
        web_server._save_profile(profile)

    def _assert_get_persists_under_lock(self, email: str, path: str, command_id: str):
        import web_server

        auth = self.register(email)
        user_id = str(auth.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)
        # Old queued command + no live bed -> the wall-clock simulator
        # advances it, forcing the handler's persist branch.
        self._seed_old_queued_command(user_id, command_id)

        real_save = web_server._save_profile
        probe_results: list[bool] = []

        def probing_save(payload):
            def try_acquire() -> bool:
                got = web_server._PROFILE_RW_LOCK.acquire(blocking=False)
                if got:
                    web_server._PROFILE_RW_LOCK.release()
                return got

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                probe_results.append(pool.submit(try_acquire).result())
            return real_save(payload)

        with patch.object(web_server, "_save_profile", side_effect=probing_save):
            resp = self.client.get(path, headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(probe_results, f"{path} must persist the advanced command state")
        self.assertTrue(
            all(r is False for r in probe_results),
            f"{path} must hold the profile RW lock across its persist cycle",
        )

    def test_dashboard_persist_holds_profile_rw_lock(self):
        self._assert_get_persists_under_lock(
            "dash-lock@example.com", "/v1/mobile/dashboard", "cmd_dash_lock_1"
        )

    def test_timeline_persist_holds_profile_rw_lock(self):
        self._assert_get_persists_under_lock(
            "timeline-lock@example.com", "/v1/mobile/timeline", "cmd_timeline_lock_1"
        )


class DeviceAuthProductionGateTests(DeviceBridgeContractCase):
    """NEW-P0-B: with no DEVICE_FACTORY_SECRET, /v1/device/auth is open —
    anyone with a provisioned serial can mint a device token. Production
    must refuse to serve open device auth."""

    def test_production_without_factory_secret_is_503(self):
        env = {"DANAH_ENV": "production", "DEVICE_FACTORY_SECRET": ""}
        with patch.dict(os.environ, env, clear=False):
            with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
                resp = self.client.post("/v1/device/auth", json={"device_id": "BED-P-01"})
        self.assertEqual(resp.status_code, 503, resp.text)

    def test_wrong_factory_secret_is_401(self):
        with patch.dict(os.environ, {"DEVICE_FACTORY_SECRET": "correct-secret"}, clear=False):
            with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
                resp = self.client.post(
                    "/v1/device/auth",
                    json={"device_id": "BED-P-02", "factory_secret": "wrong"},
                )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_correct_factory_secret_succeeds(self):
        with patch.dict(os.environ, {"DEVICE_FACTORY_SECRET": "correct-secret"}, clear=False):
            with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
                resp = self.client.post(
                    "/v1/device/auth",
                    json={"device_id": "BED-P-03", "factory_secret": "correct-secret"},
                )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["device_access_token"])

    def test_missing_secret_warns_for_production(self):
        from config.settings import validate_production_secrets

        env = {"DANAH_ENV": "production", "DEVICE_FACTORY_SECRET": ""}
        with patch.dict(os.environ, env, clear=False):
            warnings = validate_production_secrets()
        self.assertTrue(any("DEVICE_FACTORY_SECRET" in w for w in warnings), warnings)
