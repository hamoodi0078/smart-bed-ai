from typing import Optional, Tuple

import requests


class SpotifyManager:
    def __init__(self, access_token: str, device_id: str = "", timeout_seconds: int = 20):
        self.access_token = access_token.strip()
        self.device_id = device_id.strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.access_token)

    def play_track_query(self, query: str) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "Spotify is not configured yet."

        uri, error_message = self._search_top_track_uri(query)
        if error_message:
            return False, error_message
        if not uri:
            return False, f"I could not find a Spotify track for '{query}'."

        return self.play_uri(uri)

    def play_uri(self, uri: str) -> Tuple[bool, str]:
        payload = {"uris": [uri]}
        ok, message = self._api_request("PUT", "/me/player/play", json=payload)
        if not ok:
            return False, message
        return True, f"Playing on Spotify: {uri}"

    def pause(self) -> Tuple[bool, str]:
        ok, message = self._api_request("PUT", "/me/player/pause")
        if not ok:
            return False, message
        return True, "Paused Spotify playback."

    def resume(self) -> Tuple[bool, str]:
        ok, message = self._api_request("PUT", "/me/player/play")
        if not ok:
            return False, message
        return True, "Resumed Spotify playback."

    def next_track(self) -> Tuple[bool, str]:
        ok, message = self._api_request("POST", "/me/player/next")
        if not ok:
            return False, message
        return True, "Skipped to next track."

    def previous_track(self) -> Tuple[bool, str]:
        ok, message = self._api_request("POST", "/me/player/previous")
        if not ok:
            return False, message
        return True, "Went to previous track."

    def set_volume(self, percent: int) -> Tuple[bool, str]:
        volume = max(0, min(100, int(percent)))
        ok, message = self._api_request(
            "PUT", "/me/player/volume", params={"volume_percent": volume}
        )
        if not ok:
            return False, message
        return True, f"Set Spotify volume to {volume}%."

    def _search_top_track_uri(self, query: str) -> Tuple[Optional[str], str]:
        url = "https://api.spotify.com/v1/search"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"q": query, "type": "track", "limit": 1, "market": "from_token"}

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                text = response.text.strip()
                if response.status_code == 401:
                    return None, "Spotify token expired/invalid. Please reconnect Spotify."
                if response.status_code == 403:
                    return None, (
                        "Spotify rejected track search (403). Make sure this Spotify account is allowed "
                        "in your developer app user management."
                    )
                return None, f"Spotify search error ({response.status_code}): {text}"
            body = response.json()
            items = body.get("tracks", {}).get("items", [])
            if not items:
                return None, ""
            return items[0].get("uri"), ""
        except Exception:
            return None, "Spotify search request failed. Check internet and Spotify connection."

    def _api_request(self, method: str, path: str, params=None, json=None) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "Spotify access token is missing."

        url = f"https://api.spotify.com/v1{path}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        req_params = dict(params or {})
        if self.device_id:
            req_params.setdefault("device_id", self.device_id)

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=req_params,
                json=json,
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                text = response.text.strip()
                if response.status_code == 401:
                    return False, "Spotify token expired/invalid. Refresh access token."
                if response.status_code == 404:
                    return False, "No active Spotify device found. Open Spotify app and start playback once."
                return False, f"Spotify API error ({response.status_code}): {text}"
            return True, "ok"
        except Exception:
            return False, "Spotify request failed. Check internet and token."
