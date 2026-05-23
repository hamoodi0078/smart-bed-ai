"""AI chat routes — migrated from web_server.py.

Routes:
  POST /v1/ai/chat            — single-shot chat reply
  GET  /v1/ai/chat/stream     — SSE streaming chat
  POST /v1/command             — web/mobile command execution
  WS   /ws/chat               — persistent bidirectional chat
  WS   /ws/voice              — audio-in → transcript + streaming AI reply
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, WebSocket

from auth.middleware import get_current_user

router = APIRouter(tags=["chat"])


@router.post("/v1/ai/chat")
async def ai_chat(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from web_server import ChatRequest, ai_chat as _ws
    body = await request.json()
    payload = ChatRequest(**body)
    return await _ws(payload=payload, request=request)


@router.get("/v1/ai/chat/stream")
async def ai_chat_stream(message: str, request: Request, current_user: dict = Depends(get_current_user)):
    from web_server import ai_chat_stream as _ws
    return await _ws(message=message, request=request)


@router.post("/v1/command")
async def v1_command(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from web_server import CommandRequest, v1_command as _ws
    body = await request.json()
    payload = CommandRequest(**body)
    return _ws(payload=payload, request=request)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    from web_server import ws_chat as _ws
    await _ws(websocket)


@router.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket):
    from web_server import ws_voice as _ws
    await _ws(websocket)
