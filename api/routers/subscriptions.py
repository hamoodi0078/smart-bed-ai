"""Subscription & billing routes — migrated from web_server.py.

Routes:
  POST /v1/subscriptions/trial/start
  GET  /v1/subscriptions/status
  GET  /v1/subscriptions/trial/status
  GET  /v1/mobile/subscription/status
  GET  /v1/mobile/subscription/history
  POST /v1/mobile/subscription/checkout
  POST /v1/mobile/subscription/capture
  POST /v1/mobile/subscription/cancel
  POST /v1/mobile/subscription/pause
  POST /v1/mobile/subscription/cancel-active
  GET  /billing/paypal/approve
  GET  /billing/paypal/cancel
  POST /v1/billing/paypal/webhook
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["subscriptions"])


@router.post("/v1/subscriptions/trial/start")
async def start_trial(request: Request) -> dict[str, Any]:
    from web_server import TrialStartRequest, start_trial_subscription as _ws
    body = await request.json()
    payload = TrialStartRequest(**body)
    return _ws(payload=payload, request=request)


@router.get("/v1/subscriptions/status")
def subscription_status(request: Request, user_id: str = "") -> dict[str, Any]:
    from web_server import subscription_status as _ws
    return _ws(request=request, user_id=user_id)


@router.get("/v1/subscriptions/trial/status")
def trial_status(request: Request, user_id: str = "") -> dict[str, Any]:
    from web_server import trial_subscription_status as _ws
    return _ws(request=request, user_id=user_id)


@router.get("/v1/mobile/subscription/status")
async def mobile_subscription_status(request: Request) -> dict[str, Any]:
    from web_server import mobile_subscription_status as _ws
    return await _ws(request=request)


@router.get("/v1/mobile/subscription/history")
def mobile_subscription_history(request: Request, limit: int = 12) -> dict[str, Any]:
    from web_server import mobile_subscription_history as _ws
    return _ws(request=request, limit=limit)


@router.post("/v1/mobile/subscription/checkout")
async def mobile_checkout(request: Request) -> dict[str, Any]:
    from web_server import MobileSubscriptionCheckoutRequest, mobile_subscription_checkout as _ws
    body = await request.json()
    payload = MobileSubscriptionCheckoutRequest(**body)
    return _ws(payload=payload, request=request)


@router.post("/v1/mobile/subscription/capture")
async def mobile_capture(request: Request) -> dict[str, Any]:
    from web_server import MobileSubscriptionCaptureRequest, mobile_subscription_capture as _ws
    body = await request.json()
    payload = MobileSubscriptionCaptureRequest(**body)
    return _ws(payload=payload, request=request)


@router.post("/v1/mobile/subscription/cancel")
async def mobile_cancel(request: Request) -> dict[str, Any]:
    from web_server import MobileSubscriptionCancelRequest, mobile_subscription_cancel as _ws
    body = await request.json()
    payload = MobileSubscriptionCancelRequest(**body)
    return _ws(payload=payload, request=request)


@router.post("/v1/mobile/subscription/pause")
async def mobile_pause(request: Request) -> dict[str, Any]:
    from web_server import MobileSubscriptionActionRequest, mobile_subscription_pause as _ws
    body = await request.json()
    payload = MobileSubscriptionActionRequest(**body)
    return _ws(payload=payload, request=request)


@router.post("/v1/mobile/subscription/cancel-active")
async def mobile_cancel_active(request: Request) -> dict[str, Any]:
    from web_server import MobileSubscriptionActionRequest, mobile_subscription_cancel_active as _ws
    body = await request.json()
    payload = MobileSubscriptionActionRequest(**body)
    return _ws(payload=payload, request=request)


@router.get("/billing/paypal/approve")
def paypal_approve(session_id: str = "", token: str = "") -> Any:
    from web_server import billing_paypal_approve as _ws
    return _ws(session_id=session_id, token=token)


@router.get("/billing/paypal/cancel")
def paypal_cancel(session_id: str = "") -> dict[str, Any]:
    from web_server import billing_paypal_cancel as _ws
    return _ws(session_id=session_id)


@router.post("/v1/billing/paypal/webhook")
async def paypal_webhook(request: Request) -> dict[str, Any]:
    from web_server import billing_paypal_webhook as _ws
    return await _ws(request=request)
