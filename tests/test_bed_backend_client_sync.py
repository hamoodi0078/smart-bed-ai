"""Unit tests for the BedBackendClient device-sync methods (Plan 6)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai.bed_backend_client import BedBackendClient


class FetchSyncTests(unittest.TestCase):
    def _client(self) -> BedBackendClient:
        return BedBackendClient(base_url="http://backend.test", device_id="bed-unit-1")

    def test_fetch_sync_returns_body(self):
        client = self._client()
        payload = {"commands": [], "desired_state": None, "state_version": ""}
        with patch.object(
            client, "_authorized_request", return_value=(True, payload, "ok")
        ) as mocked:
            ok, body, message = client.fetch_sync()
        self.assertTrue(ok)
        self.assertEqual(body, payload)
        mocked.assert_called_once_with("GET", "/v1/device/sync")

    def test_fetch_sync_failure_returns_empty_dict(self):
        client = self._client()
        with patch.object(
            client, "_authorized_request", return_value=(False, None, "Backend request failed.")
        ):
            ok, body, message = client.fetch_sync()
        self.assertFalse(ok)
        self.assertEqual(body, {})
        self.assertEqual(message, "Backend request failed.")

    def test_report_command_result_posts_payload(self):
        client = self._client()
        with patch.object(
            client, "_authorized_request", return_value=(True, {"ok": True}, "ok")
        ) as mocked:
            ok, message = client.report_command_result(
                "cmd_1", "completed", detail="done", actual_state={"animation": "breathing"}
            )
        self.assertTrue(ok)
        mocked.assert_called_once_with(
            "POST",
            "/v1/device/commands/cmd_1/result",
            json={
                "status": "completed",
                "detail": "done",
                "actual_state": {"animation": "breathing"},
            },
        )


if __name__ == "__main__":
    unittest.main()
