"""Authentication routes — migrated from web_server.py.

Helpers still live in web_server and are lazily imported here as a
transitional step.  Once web_server.py is fully decomposed the lazy
imports will be replaced with direct service-layer calls.

Handles:
  Cookie-based (web / admin panel)
    POST /v1/auth/register
    POST /v1/auth/login
    POST /v1/admin/auth/login
    POST /v1/auth/logout
    POST /v1/auth/revoke-all-sessions
    POST /v1/auth/delete-data
    GET  /v1/auth/me
    GET  /v1/admin/auth/me

  Bearer-token (Flutter mobile)
    POST /v1/mobile/auth/register
    POST /v1/mobile/auth/login
    POST /v1/mobile/auth/otp/request
    POST /v1/mobile/auth/otp/verify
    POST /v1/mobile/auth/social
    POST /v1/mobile/auth/refresh
    POST /v1/mobile/auth/logout
    GET  /v1/mobile/auth/me
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from auth.middleware import get_current_user

router = APIRouter(tags=["auth"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    name: str = Field(default="", max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class MobileRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    name: str = Field(default="", max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileOtpRequestRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=32)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileOtpVerifyRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    phone_number: str = Field(min_length=7, max_length=32)
    otp_code: str = Field(min_length=4, max_length=8)
    name: str = Field(default="", max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileSocialLoginRequest(BaseModel):
    provider: Literal["google", "apple", "facebook"]
    provider_user_id: str = Field(default="", max_length=256)
    provider_access_token: str = Field(default="", max_length=4096)
    provider_id_token: str = Field(default="", max_length=4096)
    provider_auth_code: str = Field(default="", max_length=2048)
    email: str = Field(default="", max_length=254)
    name: str = Field(default="", max_length=256)
    client_name: str = Field(default="flutter_app", max_length=64)


class MobileRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class MobileLogoutRequest(BaseModel):
    refresh_token: str = Field(default="", max_length=2048)


# ── Password validation helper ────────────────────────────────────────────────


def _validate_password_strength(password: str, status: int = 400) -> None:
    if len(password) < 10:
        raise HTTPException(status_code=status, detail="Password must be at least 10 characters")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=status, detail="Password must contain at least one uppercase letter"
        )
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=status, detail="Password must contain at least one number")
    if len(password) > 128:
        raise HTTPException(status_code=status, detail="Password must be 128 characters or fewer")


# ── Cookie-based routes ───────────────────────────────────────────────────────


@router.post("/v1/auth/register")
def auth_register(payload: RegisterRequest, response: Response, request: Request) -> dict[str, Any]:
    from auth.cookie import enforce_same_origin, set_session_cookie
    from services.auth_service import get_auth_service
    from web_server import store

    enforce_same_origin(request)
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    name = (payload.name or "").strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Valid email address is required")
    if len(email) > 254:
        raise HTTPException(status_code=400, detail="Email address is too long")
    _validate_password_strength(password, status=400)
    try:
        user = get_auth_service().create_user_only(email=email, password=password, name=name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session = store.issue_user_token(user_id=user.get("user_id", ""))
    set_session_cookie(response, "sb_user_token", session["access_token"], 7 * 24 * 3600, request)
    return {
        "ok": True,
        "user": {
            "user_id": user.get("user_id", ""),
            "email": user.get("email", ""),
            "name": user.get("name", ""),
        },
        "expires_at": session.get("expires_at", ""),
    }


@router.post("/v1/auth/login")
def auth_login(payload: LoginRequest, response: Response, request: Request) -> dict[str, Any]:
    from auth.cookie import enforce_same_origin, set_session_cookie
    from services.auth_service import get_auth_service
    from web_server import store

    enforce_same_origin(request)
    email = str(payload.email or "").strip().lower()
    svc = get_auth_service()
    if svc.is_locked(email):
        raise HTTPException(
            status_code=429, detail="Account temporarily locked. Try again in 15 minutes."
        )
    user = svc.verify_user(email=email, password=payload.password or "")
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session = store.issue_user_token(user_id=user.get("user_id", ""))
    set_session_cookie(response, "sb_user_token", session["access_token"], 7 * 24 * 3600, request)
    return {
        "ok": True,
        "user": {
            "user_id": user.get("user_id", ""),
            "email": user.get("email", ""),
            "name": user.get("name", ""),
        },
        "expires_at": session.get("expires_at", ""),
    }


@router.post("/v1/admin/auth/login")
def admin_auth_login(payload: LoginRequest, response: Response, request: Request) -> dict[str, Any]:
    from auth.cookie import enforce_same_origin, set_session_cookie
    from services.auth_service import get_auth_service
    from web_server import store

    enforce_same_origin(request)
    email = str(payload.email or "").strip().lower()
    svc = get_auth_service()
    if svc.is_locked(email):
        raise HTTPException(
            status_code=429, detail="Account temporarily locked. Try again in 15 minutes."
        )
    user = svc.verify_user(email=email, password=payload.password or "")
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    admin_user = store.ensure_admin_for_login(user)
    role = (admin_user.get("role") or "viewer").strip().lower()
    if role == "viewer":
        raise HTTPException(status_code=403, detail="Viewer admin role cannot access admin panel")
    svc._guard.clear(email)
    session = store.issue_admin_token(user_id=user.get("user_id", ""), role=role)
    store.add_admin_audit_log(
        actor_user_id=user.get("user_id", ""),
        actor_role=role,
        action="admin_login",
        resource="auth",
        details={"email": user.get("email", "")},
    )
    set_session_cookie(response, "sb_admin_token", session["access_token"], 12 * 3600, request)
    return {
        "ok": True,
        "admin": {"user_id": user.get("user_id", ""), "email": user.get("email", ""), "role": role},
        "expires_at": session.get("expires_at", ""),
    }


@router.post("/v1/auth/logout")
def auth_logout(response: Response, request: Request) -> dict[str, Any]:
    from auth.cookie import enforce_same_origin, clear_session_cookies
    from web_server import store

    enforce_same_origin(request)
    user_token = str(request.cookies.get("sb_user_token", "") or "").strip()
    admin_token = str(request.cookies.get("sb_admin_token", "") or "").strip()
    sum(1 for t in {user_token, admin_token} if t and store.revoke_session(t))
    clear_session_cookies(response)
    return {"ok": True}


@router.post("/v1/auth/revoke-all-sessions")
def auth_revoke_all_sessions(response: Response, request: Request) -> dict[str, Any]:
    from auth.cookie import enforce_same_origin, clear_session_cookies
    from services.auth_service import get_auth_service
    from web_server import _require_user, store
    import logging

    enforce_same_origin(request)
    user = _require_user(request)
    user_id = str(user.get("user_id", "") or "").strip()
    if not user_id:
        raise HTTPException(
            status_code=400, detail="Unable to identify user for session revocation"
        )
    legacy_revoked = store.revoke_all_sessions_for_user(user_id)
    try:
        mobile_revoked = get_auth_service().revoke_all_for_user(user_id)
    except Exception as exc:
        logging.getLogger(__name__).warning("mobile revoke_all_for_user failed: %s", exc)
        mobile_revoked = 0
    clear_session_cookies(response)
    return {"ok": True, "legacy_revoked": legacy_revoked, "mobile_revoked": mobile_revoked}


@router.post("/v1/auth/delete-data")
def auth_delete_data(response: Response, request: Request) -> dict[str, Any]:
    from auth.cookie import enforce_same_origin, clear_session_cookies
    from web_server import (
        _cookie_user,
        _profile_rw,
        _safe_profile,
        _save_profile,
        _purge_profile_user_data,
        store,
    )

    enforce_same_origin(request)
    user = _cookie_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_token = str(request.cookies.get("sb_user_token", "") or "").strip()
    with _profile_rw():
        profile = _safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        profile_removed = _purge_profile_user_data(profile, user)
        _save_profile(profile)
    deleted = store.delete_user_data(user_id=str(user.get("user_id", "")))
    if user_token:
        store.revoke_session(user_token)
    clear_session_cookies(response)
    return {"ok": True, "deleted": deleted, "profile_sections_removed": profile_removed}


@router.get("/v1/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    from web_server import _cookie_user

    user = _cookie_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "ok": True,
        "user": {
            "user_id": user.get("user_id", ""),
            "email": user.get("email", ""),
            "name": user.get("name", ""),
        },
    }


@router.get("/v1/admin/auth/me")
def admin_auth_me(request: Request) -> dict[str, Any]:
    from web_server import _cookie_admin

    admin = _cookie_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"ok": True, "admin": admin}


# ── Mobile bearer-token routes ────────────────────────────────────────────────


@router.post("/v1/mobile/auth/register")
def mobile_auth_register(payload: MobileRegisterRequest) -> dict[str, Any]:
    from services.auth_service import get_auth_service

    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    name = (payload.name or "").strip()
    client_name = str(payload.client_name or "flutter_app").strip() or "flutter_app"
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="A valid email address is required")
    if len(email) > 254:
        raise HTTPException(status_code=422, detail="Email address is too long")
    _validate_password_strength(password, status=422)
    try:
        return get_auth_service().register(
            email=email, password=password, name=name, client_name=client_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/v1/mobile/auth/login")
def mobile_auth_login(payload: MobileLoginRequest) -> dict[str, Any]:
    from services.auth_service import get_auth_service

    email = str(payload.email or "").strip().lower()
    client_name = str(payload.client_name or "flutter_app").strip() or "flutter_app"
    svc = get_auth_service()
    if svc.is_locked(email):
        raise HTTPException(
            status_code=429, detail="Account temporarily locked. Try again in 15 minutes."
        )
    result = svc.login(email=email, password=payload.password or "", client_name=client_name)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@router.post("/v1/mobile/auth/otp/request")
def mobile_auth_request_otp(payload: MobileOtpRequestRequest, request: Request) -> dict[str, Any]:
    from web_server import mobile_auth_request_otp as _ws_handler

    return _ws_handler(payload=payload, request=request)  # type: ignore[arg-type]


@router.post("/v1/mobile/auth/otp/verify")
def mobile_auth_verify_otp(payload: MobileOtpVerifyRequest, request: Request) -> dict[str, Any]:
    from web_server import mobile_auth_verify_otp as _ws_handler

    return _ws_handler(payload=payload, request=request)  # type: ignore[arg-type]


@router.post("/v1/mobile/auth/social")
def mobile_auth_social_login(payload: MobileSocialLoginRequest, request: Request) -> dict[str, Any]:
    from web_server import mobile_auth_social_login as _ws_handler

    return _ws_handler(payload=payload, request=request)  # type: ignore[arg-type]


@router.post("/v1/mobile/auth/refresh")
def mobile_auth_refresh(payload: MobileRefreshRequest) -> dict[str, Any]:
    from services.auth_service import get_auth_service

    refresh_token = str(payload.refresh_token or "").strip()
    if not refresh_token:
        raise HTTPException(status_code=422, detail="refresh_token is required")
    result = get_auth_service().refresh(refresh_token)
    if result is None:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    return result


@router.post("/v1/mobile/auth/logout")
def mobile_auth_logout(payload: MobileLogoutRequest, request: Request) -> dict[str, Any]:
    from services.auth_service import get_auth_service

    auth_header = str(request.headers.get("Authorization", "") or "")
    access_token = auth_header.removeprefix("Bearer ").strip()
    refresh_token = str(payload.refresh_token or "").strip()
    revoked = get_auth_service().logout(access_token=access_token, refresh_token=refresh_token)
    return {"ok": True, "revoked": revoked}


@router.get("/v1/mobile/auth/me")
def mobile_auth_me(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from services.auth_service import get_auth_service

    # Access-token claims carry no email/name — resolve identity from the DB
    # (matches the web_server monolith's /me contract).
    user = get_auth_service().get_user_by_id(str(current_user.get("sub", "") or ""))
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {
        "ok": True,
        "user": {
            "user_id": str(user.get("user_id", "") or ""),
            "email": str(user.get("email", "") or ""),
            "name": str(user.get("name", "") or ""),
            "client_name": str(current_user.get("client", "") or ""),
        },
    }
