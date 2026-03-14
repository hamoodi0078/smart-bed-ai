from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from spotify.prayer_pause import PrayerPauseManager
from spotify.sleep_playlists import SleepPlaylists
from spotify.spotify_client import SpotifyClient
from spotify.spotify_controls import SpotifyControls


router = APIRouter(prefix="/v1/spotify", tags=["spotify"])

spotify_client = SpotifyClient()
spotify_controls = SpotifyControls(spotify_client)
prayer_pause_manager = PrayerPauseManager(spotify_controls)
sleep_playlists = SleepPlaylists()


class VolumeRequest(BaseModel):
    volume: int


class FadeRequest(BaseModel):
    from_volume: int
    to_volume: int
    steps: int = 10
    delay_seconds: float = 3.0


class PrayerPauseRequest(BaseModel):
    prayer_name: str


class PlaylistPlayRequest(BaseModel):
    mood: str


@router.get("/auth-url")
def get_auth_url() -> dict:
    return {"auth_url": spotify_client.get_auth_url()}


@router.get("/callback")
def oauth_callback(code: str = Query(...)) -> dict:
    result = spotify_client.exchange_code_for_token(code)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "OAuth exchange failed."))
    return result


@router.get("/status")
def spotify_status() -> dict:
    connected = spotify_client.is_connected()
    if not connected:
        return {"connected": False, "current_track": {"playing": False}}
    track = spotify_controls.get_current_track()
    if "track_name" in track:
        return {"connected": True, "current_track": track}
    return {"connected": True, "current_track": {"playing": False}}


@router.post("/pause")
def pause_playback() -> dict:
    return spotify_controls.pause()


@router.post("/play")
def play_playback() -> dict:
    return spotify_controls.play()


@router.post("/volume")
def set_volume(request: VolumeRequest) -> dict:
    return spotify_controls.set_volume(request.volume)


@router.post("/fade-down")
def fade_down(request: FadeRequest) -> dict:
    return spotify_controls.fade_volume_down(
        from_volume=request.from_volume,
        to_volume=request.to_volume,
        steps=request.steps,
        delay_seconds=request.delay_seconds,
    )


@router.post("/fade-up")
def fade_up(request: FadeRequest) -> dict:
    return spotify_controls.fade_volume_up(
        from_volume=request.from_volume,
        to_volume=request.to_volume,
        steps=request.steps,
        delay_seconds=request.delay_seconds,
    )


@router.post("/prayer-pause")
def prayer_pause(request: PrayerPauseRequest) -> dict:
    return prayer_pause_manager.pause_for_prayer(request.prayer_name)


@router.get("/playlist/recommend")
def recommend_playlist(hour: int | None = None) -> dict:
    current_hour = datetime.datetime.now().hour if hour is None else int(hour)
    mood = sleep_playlists.get_recommended_mood(current_hour)
    options = sleep_playlists.search_playlist(mood, spotify_client)
    return {"hour": current_hour, "recommended_mood": mood, "playlists": options}


@router.post("/playlist/play")
def play_playlist(request: PlaylistPlayRequest) -> dict:
    return sleep_playlists.play_mood_playlist(
        mood=request.mood,
        controls=spotify_controls,
        client=spotify_client,
    )
