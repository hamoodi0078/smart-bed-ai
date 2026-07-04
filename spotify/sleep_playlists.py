from __future__ import annotations

import requests

from spotify.spotify_client import SpotifyClient
from spotify.spotify_controls import SpotifyControls


class SleepPlaylists:
    PLAYLIST_MOODS = {
        "sleep": "sleep music ambient",
        "wind_down": "calm relaxing wind down",
        "focus": "focus deep work instrumental",
        "morning": "morning energy positive",
        "islamic": "quran recitation peaceful",
        "nature": "nature sounds rain forest",
        "meditation": "meditation mindfulness",
    }

    def search_playlist(self, mood: str, client: SpotifyClient) -> list[dict]:
        token = client.get_valid_token()
        if not token:
            return []

        mood_key = str(mood or "").strip().lower()
        query = self.PLAYLIST_MOODS.get(mood_key, mood_key)
        headers = {"Authorization": f"Bearer {token}"}
        params = {"q": query, "type": "playlist", "limit": 3}

        try:
            response = requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        items = payload.get("playlists", {}).get("items", []) if isinstance(payload, dict) else []
        results: list[dict] = []
        for item in items[:3]:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "name": str(item.get("name", "")),
                    "uri": str(item.get("uri", "")),
                    "tracks_count": int(item.get("tracks", {}).get("total", 0))
                    if isinstance(item.get("tracks", {}), dict)
                    else 0,
                }
            )
        return results

    def play_mood_playlist(
        self,
        mood: str,
        controls: SpotifyControls,
        client: SpotifyClient,
    ) -> dict:
        options = self.search_playlist(mood, client)
        if not options:
            return {"success": False, "message": f"No playlist found for mood '{mood}'."}

        selected = options[0]
        token = client.get_valid_token()
        if not token:
            return {"success": False, "message": "Spotify is not connected."}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"context_uri": selected.get("uri", "")}
        try:
            response = requests.put(
                "https://api.spotify.com/v1/me/player/play",
                headers=headers,
                json=payload,
                timeout=20,
            )
            if response.status_code not in (200, 202, 204):
                return {
                    "success": False,
                    "message": f"Spotify play failed ({response.status_code}).",
                }
        except Exception as exc:
            return {"success": False, "message": str(exc)}

        controls.play()
        return {
            "success": True,
            "mood": str(mood),
            "playlist": selected,
        }

    def get_recommended_mood(self, hour: int) -> str:
        safe_hour = int(hour) % 24
        if 5 <= safe_hour <= 8:
            return "morning"
        if 8 <= safe_hour < 17:
            return "focus"
        if 17 <= safe_hour < 20:
            return "nature"
        if 20 <= safe_hour < 22:
            return "wind_down"
        return "sleep"
