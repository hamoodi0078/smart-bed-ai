"""Sleep and dashboard routes — migrated from web_server.py.

Complex helpers are lazily imported from web_server as a transitional step.

Routes:
  GET  /v1/mobile/dashboard
  GET  /v1/sleep/overview

Note: /v1/mobile/routine (GET + POST) is owned by api/routers/profile.py
  which uses ProfileRepository directly.  Duplicate routes were removed.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request

from auth.middleware import get_current_user

router = APIRouter(tags=["sleep"])


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/v1/mobile/dashboard")
def mobile_dashboard(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_dashboard as _ws_handler

    return _ws_handler(request=request)


@router.get("/v1/sleep/overview")
async def sleep_overview(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import (
        _sleep_readiness_score,
        _sleep_readiness_explanation,
        _recommended_scene_for_sleep_overview,
        _sleep_quick_actions,
    )
    from time_utils import to_iso
    from time_utils import utcnow

    now_utc = utcnow().replace(microsecond=0)
    readiness_score = await asyncio.to_thread(_sleep_readiness_score, now_utc)
    return {
        "ok": True,
        "readiness_score": readiness_score,
        "readiness_explanation": _sleep_readiness_explanation(readiness_score),
        "recommended_scene": _recommended_scene_for_sleep_overview(now_utc),
        "pending_reminders": 0,
        "sensor_confidence": 100,
        "quick_actions": _sleep_quick_actions(now_utc),
        "last_updated": to_iso(now_utc),
    }
