from __future__ import annotations

import base64
import datetime
import json
import os

import requests


class SpotifyClient:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
    SCOPES = (
        "user-read-playback-state user-modify-playback-state user-read-currently-playing streaming"
    )

    def __init__(self):
        self.client_id = str(os.getenv("SPOTIFY_CLIENT_ID", "")).strip()
        self.client_secret = str(os.getenv("SPOTIFY_CLIENT_SECRET", "")).strip()
        self.redirect_uri = str(os.getenv("SPOTIFY_REDIRECT_URI", "")).strip()
        self.token_path = os.path.join(os.path.dirname(__file__), "spotify_token.json")

    def _basic_auth_header(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(raw.encode("utf-8")).decode("utf-8")

    def _read_token_file(self) -> dict:
        if not os.path.exists(self.token_path):
            return {}
        try:
            with open(self.token_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_token_file(self, payload: dict) -> dict:
        expires_in = int(payload.get("expires_in", 3600) or 3600)
        expires_at = int(datetime.datetime.utcnow().timestamp()) + max(60, expires_in - 20)
        current = self._read_token_file()
        record = {
            "access_token": str(payload.get("access_token", current.get("access_token", ""))),
            "refresh_token": str(payload.get("refresh_token", current.get("refresh_token", ""))),
            "expires_at": expires_at,
        }
        with open(self.token_path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
        return record

    def get_auth_url(self) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "scope": self.SCOPES,
            "redirect_uri": self.redirect_uri,
            "show_dialog": "true",
        }
        return requests.Request("GET", self.AUTHORIZE_URL, params=params).prepare().url

    def exchange_code_for_token(self, code: str) -> dict:
        if (not self.client_id) or (not self.client_secret) or (not self.redirect_uri):
            return {"success": False, "message": "Spotify client credentials are not configured."}

        headers = {
            "Authorization": f"Basic {self._basic_auth_header()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "code": str(code or "").strip(),
            "redirect_uri": self.redirect_uri,
        }
        try:
            response = requests.post(self.TOKEN_URL, headers=headers, data=data, timeout=20)
            response.raise_for_status()
            token_payload = response.json()
            saved = self._save_token_file(token_payload if isinstance(token_payload, dict) else {})
            return {"success": True, **saved}
        except Exception as exc:
            return {"success": False, "message": f"Failed to exchange code: {exc}"}

    def refresh_access_token(self) -> dict:
        token = self._read_token_file()
        refresh_token = str(token.get("refresh_token", "")).strip()
        if not refresh_token:
            return {"success": False, "message": "No refresh token found."}

        headers = {
            "Authorization": f"Basic {self._basic_auth_header()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        try:
            response = requests.post(self.TOKEN_URL, headers=headers, data=data, timeout=20)
            response.raise_for_status()
            token_payload = response.json()
            if isinstance(token_payload, dict) and ("refresh_token" not in token_payload):
                token_payload["refresh_token"] = refresh_token
            saved = self._save_token_file(token_payload if isinstance(token_payload, dict) else {})
            return {"success": True, **saved}
        except Exception as exc:
            return {"success": False, "message": f"Failed to refresh token: {exc}"}

    def get_valid_token(self) -> str:
        token = self._read_token_file()
        access_token = str(token.get("access_token", "")).strip()
        expires_at = int(token.get("expires_at", 0) or 0)
        now_ts = int(datetime.datetime.utcnow().timestamp())

        if (not access_token) or (expires_at <= now_ts):
            refreshed = self.refresh_access_token()
            if not refreshed.get("success"):
                return ""
            return str(refreshed.get("access_token", ""))
        return access_token

    def is_connected(self) -> bool:
        token = self._read_token_file()
        if not token:
            return False
        return bool(self.get_valid_token())
