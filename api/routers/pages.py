"""HTML page serving and static assets.

Routes:
  GET  /
  GET  /login
  GET  /user-dashboard
  GET  /admin-panel
  GET  /admin-billing
  GET  /admin
  GET  /assets/{asset_name}

Health and metrics endpoints live in health.py and metrics.py respectively.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["pages"])


# ── Redirect root ─────────────────────────────────────────────────────────────

@router.get("/")
def root() -> RedirectResponse:
    from web_server import root as _ws
    return _ws()


# ── HTML page routes ──────────────────────────────────────────────────────────

@router.get("/login")
def login_page():
    from web_server import login_page as _ws
    return _ws()


@router.get("/user-dashboard")
def user_dashboard(request: Request):
    from web_server import user_dashboard as _ws
    return _ws(request=request)


@router.get("/admin-panel")
def admin_panel(request: Request):
    from web_server import admin_panel as _ws
    return _ws(request=request)


@router.get("/admin-billing")
def admin_billing(request: Request):
    from web_server import admin_billing as _ws
    return _ws(request=request)


@router.get("/admin")
def admin_page(request: Request):
    from web_server import admin_v2 as _ws
    return _ws(request=request)


# ── Static assets ─────────────────────────────────────────────────────────────

@router.get("/assets/{asset_name}")
def asset_file(asset_name: str):
    from web_server import asset_file as _ws
    return _ws(asset_name=asset_name)


