"""Remaining mobile feature routes — migrated from web_server.py.

Islamic routes live in islamic.py.

Routes:
  GET  /v1/mobile/plan
  POST /v1/mobile/push-token
  GET  /v1/mobile/timeline
  GET  /v1/mobile/first-3-nights
  POST /v1/mobile/first-3-nights/complete
  POST /v1/mobile/nightly-summary/feedback
  GET  /v1/mobile/beta/metrics
  POST /v1/mobile/user-actions
  GET  /v1/mobile/version-check
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from auth.middleware import get_current_user

router = APIRouter(tags=["mobile"])


# ── Subscription plan ─────────────────────────────────────────────────────────


@router.get("/v1/mobile/plan")
def mobile_plan(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from web_server import mobile_plan as _ws

    return _ws(request=request)


# ── Push tokens ───────────────────────────────────────────────────────────────


@router.post("/v1/mobile/push-token")
async def register_push_token(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import RegisterPushTokenRequest, register_push_token as _ws

    body = await request.json()
    payload = RegisterPushTokenRequest(**body)
    return _ws(payload=payload, request=request)


# ── Timeline ──────────────────────────────────────────────────────────────────


@router.get("/v1/mobile/timeline")
def mobile_timeline(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_timeline as _ws

    return _ws(request=request)


# ── First-3-nights onboarding checklist ──────────────────────────────────────


@router.get("/v1/mobile/first-3-nights")
def first_3_nights(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_first_3_nights as _ws

    return _ws(request=request)


@router.post("/v1/mobile/first-3-nights/complete")
async def first_3_nights_complete(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import FirstThreeNightsStepRequest, mobile_first_3_nights_complete as _ws

    body = await request.json()
    payload = FirstThreeNightsStepRequest(**body)
    return _ws(payload=payload, request=request)


# ── Feedback ──────────────────────────────────────────────────────────────────


@router.post("/v1/mobile/nightly-summary/feedback")
async def nightly_summary_feedback(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import NightlySummaryFeedbackRequest, mobile_nightly_summary_feedback as _ws

    body = await request.json()
    payload = NightlySummaryFeedbackRequest(**body)
    return _ws(payload=payload, request=request)


# ── Beta metrics ──────────────────────────────────────────────────────────────


@router.get("/v1/mobile/beta/metrics")
def beta_metrics(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_beta_metrics as _ws

    return _ws(request=request)


# ── User actions (alias for device-commands) ──────────────────────────────────


@router.post("/v1/mobile/user-actions")
async def mobile_user_actions(
    request: Request, current_user: dict = Depends(get_current_user)
) -> Any:
    from web_server import UserActionRequest, mobile_user_actions as _ws

    body = await request.json()
    payload = UserActionRequest(**body)
    return _ws(payload=payload, request=request)


# ── App version check ─────────────────────────────────────────────────────────


@router.get("/v1/mobile/version-check")
def mobile_version_check(request: Request, platform: str = "android") -> dict[str, Any]:
    from web_server import mobile_version_check as _ws

    return _ws(request=request, platform=platform)
