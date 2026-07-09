"""Scene routes — migrated from web_server.py.

Complex handlers are forwarded to web_server functions (transitional).
Pydantic bodies are lazily imported from web_server to avoid circular imports.

Routes:
  GET  /v1/mobile/scenes
  GET  /v1/scenes/templates
  POST /v1/scenes/compose
  POST /v1/mobile/scenes/preview
  POST /v1/mobile/scenes/save-tonight
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["scenes"])


@router.get("/v1/mobile/scenes")
def mobile_scenes(request: Request) -> dict[str, Any]:
    from web_server import mobile_scenes as _ws

    return _ws(request=request)


@router.get("/v1/scenes/templates")
def scene_templates(request: Request, premium_only: bool = False) -> dict[str, Any]:
    from web_server import scene_templates as _ws

    return _ws(request=request, premium_only=premium_only)


@router.post("/v1/scenes/compose")
async def compose_scene(request: Request) -> Any:
    from web_server import SceneComposeRequest, compose_scene as _ws

    body = await request.json()
    payload = SceneComposeRequest(**body)
    # _ws is sync monolith code — run it off the event loop (audit P1-7)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.post("/v1/mobile/scenes/preview")
async def mobile_scene_preview(request: Request) -> Any:
    from web_server import SceneSelectionRequest, mobile_scene_preview as _ws

    body = await request.json()
    payload = SceneSelectionRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.post("/v1/mobile/scenes/save-tonight")
async def mobile_scene_save_tonight(request: Request) -> Any:
    from web_server import SceneSelectionRequest, mobile_scene_save_tonight as _ws

    body = await request.json()
    payload = SceneSelectionRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)
