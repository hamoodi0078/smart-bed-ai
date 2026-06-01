"""Automation routes — single canonical router for all automation endpoints.

api/automation_routes.py is the legacy location; this module re-exports it so
app_factory.py has one clean import point.  New automation endpoints should be
added here directly.

TODO (migrate from web_server.py):
  POST /v1/actions/undo          (line 6013)
  GET  /v1/actions/undo/status   (line 6063)
  GET  /v1/mobile/actions/undo/status (line 6087)
  POST /v1/mobile/actions/undo   (line 6114)
  POST /v1/command               (line 10244)
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["automations"])

try:
    from api.automation_routes import router as _legacy_router
    router.include_router(_legacy_router)
except ImportError:
    pass
