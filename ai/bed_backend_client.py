from datetime import datetime, timedelta
from typing import Optional

import requests
from time_utils import from_iso, utcnow


class BedBackendClient:
    def __init__(
        self,
        base_url: str,
        device_id: str,
        firmware_version: str = "1.0.0",
        timeout_seconds: int = 20,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.device_id = (device_id or "").strip()
        self.firmware_version = (firmware_version or "1.0.0").strip()
        self.timeout_seconds = max(3, int(timeout_seconds))

        self.device_access_token = ""
        self.refresh_token = ""
        self.access_expires_at: Optional[datetime] = None
        self.entitlement: dict = {}

    def is_configured(self) -> bool:
        return bool(self.base_url and self.device_id)

    @staticmethod
    def _utc_now() -> datetime:
        return utcnow()

    def _parse_expires_at(self, expires_at_text: str) -> Optional[datetime]:
        try:
            return from_iso(str(expires_at_text or ""))
        except Exception:
            return None

    def _is_access_token_valid(self) -> bool:
        if not self.device_access_token:
            return False
        if not self.access_expires_at:
            return True
        return self.access_expires_at > self._utc_now() + timedelta(seconds=20)

    def _store_token_bundle(self, payload: dict):
        self.device_access_token = str(
            payload.get("device_access_token", "") or self.device_access_token
        )
        self.refresh_token = str(payload.get("refresh_token", "") or self.refresh_token)
        self.access_expires_at = self._parse_expires_at(payload.get("expires_at", ""))
        self.entitlement = payload.get("entitlement", self.entitlement) or {}

    def _request(self, method: str, path: str, headers=None, json=None) -> requests.Response:
        url = f"{self.base_url}{path}"
        return requests.request(
            method,
            url,
            headers=headers or {},
            json=json,
            timeout=self.timeout_seconds,
        )

    def _authorized_request(
        self, method: str, path: str, json=None
    ) -> tuple[bool, Optional[dict], str]:
        ok, msg = self.ensure_session()
        if not ok:
            return False, None, msg

        headers = {"Authorization": f"Bearer {self.device_access_token}"}
        try:
            response = self._request(method, path, headers=headers, json=json)
            if response.status_code == 401:
                refreshed, refresh_msg = self.refresh_access_token()
                if not refreshed:
                    return False, None, refresh_msg
                headers = {"Authorization": f"Bearer {self.device_access_token}"}
                response = self._request(method, path, headers=headers, json=json)

            if response.status_code >= 400:
                return False, None, f"Backend error ({response.status_code}): {response.text}"

            return True, response.json(), "ok"
        except Exception:
            return False, None, "Backend request failed."

    def device_auth(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Backend client is not configured."

        payload = {
            "device_id": self.device_id,
            "firmware_version": self.firmware_version,
            "factory_secret": "",
        }
        try:
            response = self._request("POST", "/v1/device/auth", json=payload)
            if response.status_code >= 400:
                return False, f"Device auth failed ({response.status_code}): {response.text}"
            body = response.json()
            self._store_token_bundle(body)
            return True, "Device cloud session is active."
        except Exception:
            return False, "Device auth request failed."

    def refresh_access_token(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Backend client is not configured."
        if not self.refresh_token:
            return False, "Refresh token is missing."

        payload = {
            "device_id": self.device_id,
            "refresh_token": self.refresh_token,
        }
        try:
            response = self._request("POST", "/v1/device/token/refresh", json=payload)
            if response.status_code >= 400:
                return False, f"Token refresh failed ({response.status_code})."
            body = response.json()
            self._store_token_bundle(body)
            return True, "Device token refreshed."
        except Exception:
            return False, "Token refresh request failed."

    def ensure_session(self) -> tuple[bool, str]:
        if self._is_access_token_valid():
            return True, "Device cloud session already valid."
        if self.refresh_token:
            ok, msg = self.refresh_access_token()
            if ok:
                return True, msg
        return self.device_auth()

    def fetch_entitlement(self) -> tuple[bool, dict]:
        ok, body, _ = self._authorized_request("GET", "/v1/entitlements")
        if not ok or not isinstance(body, dict):
            return False, {}
        self.entitlement = body.get("entitlement", {}) or {}
        return True, self.entitlement

    def request_ai_chat(
        self,
        text: str,
        personality: str,
        user_context: str,
        realtime_context: str,
        max_response_tokens: int,
    ) -> tuple[bool, str, dict]:
        payload = {
            "text": text,
            "personality": personality,
            "user_context": user_context,
            "realtime_context": realtime_context,
            "max_response_tokens": max_response_tokens,
        }
        ok, body, message = self._authorized_request("POST", "/v1/ai/chat", json=payload)
        if not ok or not isinstance(body, dict):
            return False, message, {}
        self.entitlement = body.get("entitlement", self.entitlement) or self.entitlement
        if not bool(body.get("ok", False)):
            fallback = str(body.get("fallback_message", "Cloud chat unavailable."))
            return False, fallback, body
        return True, str(body.get("reply", "")), body

    def is_feature_allowed(self, feature_key: str) -> bool:
        features = (
            self.entitlement.get("features", {}) if isinstance(self.entitlement, dict) else {}
        )
        return bool(features.get(feature_key, False))

    def fetch_sync(self) -> tuple[bool, dict, str]:
        """Poll the backend for pending commands + desired state."""
        ok, body, message = self._authorized_request("GET", "/v1/device/sync")
        if not ok or not isinstance(body, dict):
            return False, {}, message
        return True, body, "ok"

    def report_command_result(
        self,
        command_id: str,
        status: str,
        detail: str = "",
        actual_state: Optional[dict] = None,
    ) -> tuple[bool, str]:
        """Report a command's real outcome ("completed" or "failed")."""
        payload = {
            "status": status,
            "detail": detail,
            "actual_state": actual_state or {},
        }
        ok, _body, message = self._authorized_request(
            "POST", f"/v1/device/commands/{command_id}/result", json=payload
        )
        return ok, message

    def status_line(self) -> str:
        if not self.is_configured():
            return "Cloud runtime: disabled (missing APP_BACKEND_BASE_URL or BED_DEVICE_ID)."
        tier = (
            str(self.entitlement.get("tier", "unknown"))
            if isinstance(self.entitlement, dict)
            else "unknown"
        )
        status = (
            str(self.entitlement.get("status", "unknown"))
            if isinstance(self.entitlement, dict)
            else "unknown"
        )
        cloud = (
            bool(self.entitlement.get("cloud_enabled", False))
            if isinstance(self.entitlement, dict)
            else False
        )
        return f"Cloud runtime: tier={tier}, status={status}, cloud_enabled={cloud}."
