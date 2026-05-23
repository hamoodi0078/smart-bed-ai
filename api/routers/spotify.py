"""Spotify integration routes — migrated from web_server.py.

Routes:
  GET  /v1/mobile/spotify/auth-url
  GET  /v1/mobile/spotify/connect
  GET  /v1/mobile/spotify/callback
  GET  /v1/mobile/spotify/status
  POST /v1/mobile/spotify/disconnect
  GET  /v1/mobile/spotify/playback-status
  POST /v1/mobile/spotify/playback
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1/mobile/spotify", tags=["spotify"])


@router.get("/auth-url")
def spotify_auth_url(request: Request, done_uri: str = "") -> dict[str, Any]:
    from web_server import mobile_spotify_auth_url as _ws
    return _ws(request=request, done_uri=done_uri)


@router.get("/connect")
def spotify_connect(request: Request):
    from web_server import mobile_spotify_connect as _ws
    return _ws(request=request)


@router.get("/callback")
def spotify_callback(request: Request, code: str = "", state: str = ""):
    from web_server import mobile_spotify_callback as _ws
    return _ws(request=request, code=code, state=state)


@router.get("/status")
def spotify_status(request: Request) -> dict[str, Any]:
    from web_server import mobile_spotify_status as _ws
    return _ws(request=request)


@router.post("/disconnect")
def spotify_disconnect(request: Request) -> dict[str, Any]:
    from web_server import mobile_spotify_disconnect as _ws
    return _ws(request=request)


@router.get("/playback-status")
def spotify_playback_status(request: Request) -> dict[str, Any]:
    from web_server import mobile_spotify_playback_status as _ws
    return _ws(request=request)


@router.post("/playback")
async def spotify_playback(request: Request) -> dict[str, Any]:
    from web_server import SpotifyPlaybackRequest, mobile_spotify_playback as _ws
    body = await request.json()
    payload = SpotifyPlaybackRequest(**body)
    return _ws(payload=payload, request=request)
