from __future__ import annotations

import time

import requests

from spotify.spotify_client import SpotifyClient


class SpotifyControls:
    BASE_PLAYER_URL = "https://api.spotify.com/v1/me/player"

    def __init__(self, client: SpotifyClient):
        self.client = client

    def _request(self, method: str, endpoint: str, *, params: dict | None = None, body: dict | None = None):
        token = self.client.get_valid_token()
        if not token:
            return None, "Spotify is not connected."
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.request(
                method=method,
                url=f"{self.BASE_PLAYER_URL}{endpoint}",
                headers=headers,
                params=params,
                json=body,
                timeout=20,
            )
            return response, ""
        except Exception as exc:
            return None, str(exc)

    def pause(self) -> dict:
        response, error = self._request("PUT", "/pause")
        if error:
            return {"success": False, "action": "paused", "message": error}
        if response is not None and response.status_code in (200, 202, 204):
            return {"success": True, "action": "paused"}
        return {"success": False, "action": "paused", "status_code": response.status_code if response else None}

    def play(self) -> dict:
        response, error = self._request("PUT", "/play")
        if error:
            return {"success": False, "action": "playing", "message": error}
        if response is not None and response.status_code in (200, 202, 204):
            return {"success": True, "action": "playing"}
        return {"success": False, "action": "playing", "status_code": response.status_code if response else None}

    def set_volume(self, volume: int) -> dict:
        safe_volume = max(0, min(100, int(volume)))
        response, error = self._request("PUT", "/volume", params={"volume_percent": safe_volume})
        if error:
            return {"success": False, "volume": safe_volume, "message": error}
        if response is not None and response.status_code in (200, 202, 204):
            return {"success": True, "volume": safe_volume}
        return {"success": False, "volume": safe_volume, "status_code": response.status_code if response else None}

    def get_current_track(self) -> dict:
        response, error = self._request("GET", "/currently-playing")
        if error:
            return {"playing": False, "message": error}
        if response is None or response.status_code == 204:
            return {"playing": False}
        if response.status_code >= 400:
            return {"playing": False, "status_code": response.status_code}

        payload = response.json() if response.content else {}
        item = payload.get("item", {}) if isinstance(payload, dict) else {}
        artists = item.get("artists", []) if isinstance(item, dict) else []
        artist = ""
        if isinstance(artists, list) and artists:
            artist = str(artists[0].get("name", "")) if isinstance(artists[0], dict) else ""

        return {
            "track_name": str(item.get("name", "")) if isinstance(item, dict) else "",
            "artist": artist,
            "is_playing": bool(payload.get("is_playing", False)) if isinstance(payload, dict) else False,
        }

    def fade_volume_down(
        self,
        from_volume: int = 80,
        to_volume: int = 0,
        steps: int = 10,
        delay_seconds: float = 3.0,
    ) -> dict:
        total_steps = max(1, int(steps))
        start = int(from_volume)
        end = int(to_volume)
        last_result = {}

        for i in range(total_steps + 1):
            current = int(round(start + (end - start) * (i / total_steps)))
            last_result = self.set_volume(current)
            if i < total_steps:
                time.sleep(max(0.0, float(delay_seconds)))

        return {
            "success": bool(last_result.get("success", False)),
            "action": "fade_down",
            "from_volume": start,
            "to_volume": end,
            "steps": total_steps,
        }

    def fade_volume_up(
        self,
        from_volume: int = 0,
        to_volume: int = 70,
        steps: int = 10,
        delay_seconds: float = 2.0,
    ) -> dict:
        total_steps = max(1, int(steps))
        start = int(from_volume)
        end = int(to_volume)
        last_result = {}

        for i in range(total_steps + 1):
            current = int(round(start + (end - start) * (i / total_steps)))
            last_result = self.set_volume(current)
            if i < total_steps:
                time.sleep(max(0.0, float(delay_seconds)))

        return {
            "success": bool(last_result.get("success", False)),
            "action": "fade_up",
            "from_volume": start,
            "to_volume": end,
            "steps": total_steps,
        }
