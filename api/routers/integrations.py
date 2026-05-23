"""External integration routes — migrated from web_server.py.

Routes:
  POST /v1/garmin/sync
  GET  /v1/garmin/status
  GET  /v1/fitbit/auth-url
  GET  /v1/fitbit/callback
  POST /v1/fitbit/sync
  POST /v1/calendar/google/sync
  GET  /v1/calendar/schedule
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["integrations"])


# ── Garmin ───────────────────────────────────────────────────────────────────

@router.post("/v1/garmin/sync")
async def garmin_sync(request: Request) -> dict[str, Any]:
    from web_server import GarminSyncRequest, garmin_sync as _ws
    body = await request.json()
    payload = GarminSyncRequest(**body)
    return await _ws(payload=payload, request=request)


@router.get("/v1/garmin/status")
def garmin_status(request: Request) -> dict[str, Any]:
    from web_server import garmin_status as _ws
    return _ws(request=request)


# ── Fitbit ───────────────────────────────────────────────────────────────────

@router.get("/v1/fitbit/auth-url")
def fitbit_auth_url(request: Request) -> dict[str, Any]:
    from web_server import fitbit_auth_url as _ws
    return _ws(request=request)


@router.get("/v1/fitbit/callback")
async def fitbit_callback(code: str, request: Request) -> dict[str, Any]:
    from web_server import fitbit_callback as _ws
    return await _ws(code=code, request=request)


@router.post("/v1/fitbit/sync")
async def fitbit_sync(request: Request) -> dict[str, Any]:
    from web_server import FitbitSyncRequest, fitbit_sync as _ws
    body = await request.json()
    payload = FitbitSyncRequest(**body)
    return await _ws(payload=payload, request=request)


# ── Google Calendar ──────────────────────────────────────────────────────────

@router.post("/v1/calendar/google/sync")
async def calendar_google_sync(request: Request) -> dict[str, Any]:
    from web_server import GoogleCalendarSyncRequest, calendar_google_sync as _ws
    body = await request.json()
    payload = GoogleCalendarSyncRequest(**body)
    return await _ws(payload=payload, request=request)


@router.get("/v1/calendar/schedule")
async def calendar_schedule(request: Request, days_ahead: int = 1) -> dict[str, Any]:
    from web_server import calendar_schedule as _ws
    return await _ws(request=request, days_ahead=days_ahead)
