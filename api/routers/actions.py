"""Undo-action routes — migrated from web_server.py.

Routes:
  POST /v1/actions/undo
  GET  /v1/actions/undo/status
  GET  /v1/mobile/actions/undo/status
  POST /v1/mobile/actions/undo
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from auth.middleware import get_current_user

router = APIRouter(tags=["actions"])


@router.post("/v1/actions/undo")
async def undo_last_action(request: Request, current_user: dict = Depends(get_current_user)) -> Any:
    from web_server import UndoActionRequest, undo_last_action as _ws
    body = await request.json()
    payload = UndoActionRequest(**body)
    return _ws(payload=payload, request=request)


@router.get("/v1/actions/undo/status")
def undo_action_status(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from web_server import undo_action_status as _ws
    return _ws(request=request)


@router.get("/v1/mobile/actions/undo/status")
def mobile_undo_status(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from web_server import mobile_undo_action_status as _ws
    return _ws(request=request)


@router.post("/v1/mobile/actions/undo")
async def mobile_undo_last_action(request: Request, current_user: dict = Depends(get_current_user)) -> Any:
    from web_server import mobile_undo_last_action as _ws
    return _ws(request=request)
