"""Admin-only routes — migrated from web_server.py.

All endpoints require an authenticated admin session: the web panel's
sb_admin_token cookie, or a Bearer JWT carrying an admin role claim.
Login and /auth/me live in api/routers/auth.py (cookie-based).
Complex handlers are delegated to web_server functions as a
transitional step.

Routes:
  GET   /v1/admin/observability
  GET   /v1/admin/diagnostics
  GET   /v1/admin/overview
  GET   /v1/admin/incidents
  GET   /v1/admin/runtime
  GET   /v1/admin/fleet
  GET   /v1/admin/audit
  GET   /v1/admin/billing/timeline
  GET   /v1/admin/user-dashboard
  GET   /v1/admin/mobile/beta-acceptance
  GET   /v1/admin/mobile/beta-cohort
  POST  /v1/admin/mobile/beta-cohort/enroll
  POST  /v1/admin/actions
  POST  /v1/admin/voice/circuit-breaker/reset
  GET   /v1/admin/versions
  POST  /v1/admin/versions/app
  POST  /v1/admin/versions/firmware
  PATCH /v1/admin/versions/{version_id}
  GET   /v1/admin/feature-flags
  POST  /v1/admin/feature-flags
  PATCH /v1/admin/feature-flags/{flag_key}
  GET   /v1/admin/users/{user_id}/features
  POST  /v1/admin/users/{user_id}/features
  DELETE /v1/admin/users/{user_id}/features/{flag_key}
  GET   /v1/admin/users
  GET   /v1/admin/users/{user_id}/detail
  PATCH /v1/admin/users/{user_id}
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request


def require_admin_session(request: Request) -> dict[str, Any]:
    """Admin guard: cookie session (web panel) first, Bearer JWT role fallback.

    The panel sends the sb_admin_token cookie (credentials:"include"); JWTs
    carrying a role claim are accepted for non-browser API clients.
    """
    from web_server import _cookie_admin

    admin = _cookie_admin(request)
    if admin:
        return admin

    auth_header = str(request.headers.get("authorization", "") or "")
    if auth_header.lower().startswith("bearer "):
        from auth.jwt_handler import JWTError, decode_access_token

        try:
            claims = decode_access_token(auth_header[7:].strip())
        except JWTError:
            claims = {}
        if claims.get("type") == "access" and claims.get("role") in ("admin", "owner"):
            return {"user_id": str(claims.get("sub", "")), "role": str(claims.get("role"))}

    raise HTTPException(status_code=401, detail="Admin auth required")


# Every endpoint requires an authenticated admin session
router = APIRouter(
    prefix="/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_session)],
)


# ── Observability & diagnostics ──────────────────────────────────────────────


@router.get("/observability")
def admin_observability(request: Request) -> dict[str, Any]:
    from web_server import admin_observability as _ws

    return _ws(request=request)


@router.get("/diagnostics")
def admin_diagnostics(request: Request) -> dict[str, Any]:
    from web_server import admin_diagnostics as _ws

    return _ws(request=request)


# ── Dashboard ────────────────────────────────────────────────────────────────


@router.get("/overview")
def admin_overview(request: Request) -> dict[str, Any]:
    from web_server import admin_overview as _ws

    return _ws(request=request)


@router.get("/incidents")
def admin_incidents(request: Request) -> dict[str, Any]:
    from web_server import admin_incidents as _ws

    return _ws(request=request)


@router.get("/runtime")
def admin_runtime(request: Request) -> dict[str, Any]:
    from web_server import admin_runtime as _ws

    return _ws(request=request)


@router.get("/fleet")
def admin_fleet(request: Request) -> dict[str, Any]:
    from web_server import admin_fleet as _ws

    return _ws(request=request)


@router.get("/audit")
def admin_audit(request: Request) -> dict[str, Any]:
    from web_server import admin_audit as _ws

    return _ws(request=request)


@router.get("/billing/timeline")
def admin_billing_timeline(request: Request, limit: int = 50) -> dict[str, Any]:
    from web_server import admin_billing_timeline as _ws

    return _ws(request=request, limit=limit)


@router.get("/user-dashboard")
def admin_user_dashboard(request: Request) -> dict[str, Any]:
    from web_server import admin_user_dashboard as _ws

    return _ws(request=request)


# ── Beta management ──────────────────────────────────────────────────────────


@router.get("/mobile/beta-acceptance")
def beta_acceptance(request: Request, max_testers: int = 5) -> dict[str, Any]:
    from web_server import admin_mobile_beta_acceptance as _ws

    return _ws(request=request, max_testers=max_testers)


@router.get("/mobile/beta-cohort")
def beta_cohort(request: Request, cohort_key: str = "kuwait_beta") -> dict[str, Any]:
    from web_server import admin_mobile_beta_cohort as _ws

    return _ws(request=request, cohort_key=cohort_key)


@router.post("/mobile/beta-cohort/enroll")
async def beta_enroll(request: Request) -> dict[str, Any]:
    from web_server import BetaCohortEnrollRequest, admin_mobile_beta_cohort_enroll as _ws

    body = await request.json()
    payload = BetaCohortEnrollRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


# ── Admin actions ────────────────────────────────────────────────────────────


@router.post("/actions")
async def admin_actions(request: Request) -> dict[str, Any]:
    from web_server import AdminActionRequest, admin_actions as _ws

    body = await request.json()
    payload = AdminActionRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.post("/voice/circuit-breaker/reset")
def voice_cb_reset(request: Request) -> dict[str, Any]:
    from web_server import admin_voice_circuit_breaker_reset as _ws

    return _ws(request=request)


# ── Version management ───────────────────────────────────────────────────────


@router.get("/versions")
def list_versions(request: Request) -> dict[str, Any]:
    from web_server import admin_list_versions as _ws

    return _ws(request=request)


@router.post("/versions/app")
async def publish_app_version(request: Request) -> dict[str, Any]:
    from web_server import PublishAppVersionRequest, admin_publish_app_version as _ws

    body = await request.json()
    payload = PublishAppVersionRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.post("/versions/firmware")
async def publish_firmware_version(request: Request) -> dict[str, Any]:
    from web_server import PublishFirmwareVersionRequest, admin_publish_firmware_version as _ws

    body = await request.json()
    payload = PublishFirmwareVersionRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.patch("/versions/{version_id}")
async def patch_version(version_id: str, request: Request) -> dict[str, Any]:
    from web_server import PatchVersionRequest, admin_patch_version as _ws

    body = await request.json()
    payload = PatchVersionRequest(**body)
    return await asyncio.to_thread(_ws, version_id=version_id, payload=payload, request=request)


# ── Feature flags ────────────────────────────────────────────────────────────


@router.get("/feature-flags")
def list_feature_flags(request: Request) -> dict[str, Any]:
    from web_server import admin_list_feature_flags as _ws

    return _ws(request=request)


@router.post("/feature-flags")
async def upsert_feature_flag(request: Request) -> dict[str, Any]:
    from web_server import UpsertFeatureFlagRequest, admin_upsert_feature_flag as _ws

    body = await request.json()
    payload = UpsertFeatureFlagRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.patch("/feature-flags/{flag_key}")
async def patch_feature_flag(flag_key: str, request: Request) -> dict[str, Any]:
    from web_server import PatchFeatureFlagRequest, admin_patch_feature_flag as _ws

    body = await request.json()
    payload = PatchFeatureFlagRequest(**body)
    return await asyncio.to_thread(_ws, flag_key=flag_key, payload=payload, request=request)


# ── User feature overrides ───────────────────────────────────────────────────


@router.get("/users/{user_id}/features")
def get_user_features(user_id: str, request: Request) -> dict[str, Any]:
    from web_server import admin_get_user_features as _ws

    return _ws(user_id=user_id, request=request)


@router.post("/users/{user_id}/features")
async def set_user_feature(user_id: str, request: Request) -> dict[str, Any]:
    from web_server import SetUserFeatureOverrideRequest, admin_set_user_feature as _ws

    body = await request.json()
    payload = SetUserFeatureOverrideRequest(**body)
    return await asyncio.to_thread(_ws, user_id=user_id, payload=payload, request=request)


@router.delete("/users/{user_id}/features/{flag_key}")
def delete_user_feature(user_id: str, flag_key: str, request: Request) -> dict[str, Any]:
    from web_server import admin_delete_user_feature as _ws

    return _ws(user_id=user_id, flag_key=flag_key, request=request)


# ── User management ──────────────────────────────────────────────────────────


@router.get("/users")
def list_users(search: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    from services.user_service import get_user_service

    return get_user_service().list_users(search=search, limit=limit, offset=offset)


@router.get("/users/{user_id}/detail")
def get_user_detail(user_id: str) -> dict[str, Any]:
    from services.user_service import get_user_service

    user = get_user_service().get_user(user_id)
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "user": user}


@router.patch("/users/{user_id}")
async def patch_user(user_id: str, request: Request) -> dict[str, Any]:
    from services.user_service import get_user_service
    from fastapi import HTTPException

    body = await request.json()
    try:
        user = get_user_service().patch_user(user_id, **body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "user": user}
