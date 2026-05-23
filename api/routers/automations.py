"""Automation routes stub.

Most automation routes already live in api/automation_routes.py —
this stub imports that existing router and re-exports it.
Add additional automation-adjacent routes here as you migrate from web_server.py.

Routes already in api/automation_routes.py — wire them in app_factory.py.
Additional routes to migrate from web_server.py:
  POST /v1/actions/undo          (line 6013)
  GET  /v1/actions/undo/status   (line 6063)
  GET  /v1/mobile/actions/undo/status (line 6087)
  POST /v1/mobile/actions/undo   (line 6114)
  POST /v1/command               (line 10244)
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["automations"])

# Wire in existing automation routes
try:
    from api.automation_routes import router as _existing_automation_router
    router.include_router(_existing_automation_router)
except ImportError:
    pass

# NOTE: Additional automation routes are served via the legacy web_server.py mount.
# They will be migrated here incrementally as individual features stabilize.
