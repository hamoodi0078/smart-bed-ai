"""Device pairing and control routes — migrated from web_server.py.

Complex handlers are delegated to web_server functions as a transitional step.

Routes:
  GET  /v1/bed/state
  GET  /v1/device/status
  GET  /v1/mobile/device-controls
  POST /v1/mobile/device-controls
  GET  /v1/mobile/bed/pairing
  POST /v1/mobile/bed/pair
  POST /v1/mobile/bed/unpair
  GET  /v1/mobile/devices
  POST /v1/mobile/device-commands
  GET  /v1/mobile/device-commands/{command_id}
  POST /v1/mobile/device-commands/{command_id}/feedback
  GET  /v1/device/firmware-check
  GET  /v1/mobile/sensors/live
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request

from auth.middleware import get_current_device, get_current_user

router = APIRouter(tags=["devices"])


# ── Bed state & device status ────────────────────────────────────────────────


@router.get("/v1/bed/state")
@router.get("/v1/bedstate")
def bed_state(request: Request) -> dict[str, Any]:
    from web_server import bed_state_bridge as _ws

    return _ws(request=request)


@router.get("/v1/state")
def v1_state(request: Request) -> dict[str, Any]:
    from web_server import v1_state as _ws

    return _ws(request=request)


@router.get("/v2/bed/state")
def v2_bed_state(request: Request):
    from web_server import v2_bed_state as _ws

    return _ws(request=request)


@router.get("/v1/device/status")
def device_status(request: Request) -> dict[str, Any]:
    from web_server import device_status as _ws

    return _ws(request=request)


@router.get("/v1/device/firmware-check")
def firmware_check(
    request: Request, device_id: str = "", current_version: str = ""
) -> dict[str, Any]:
    from web_server import device_firmware_check as _ws

    return _ws(request=request, device_id=device_id, current_version=current_version)


# ── Device controls ──────────────────────────────────────────────────────────


@router.get("/v1/mobile/device-controls")
def get_device_controls(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_device_controls as _ws

    return _ws(request=request)


@router.post("/v1/mobile/device-controls")
async def upsert_device_controls(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import UserDeviceControlRequest, upsert_mobile_device_controls as _ws

    body = await request.json()
    payload = UserDeviceControlRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


# ── Bed pairing ──────────────────────────────────────────────────────────────


@router.get("/v1/mobile/bed/pairing")
def bed_pairing_status(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_bed_pairing_status as _ws

    return _ws(request=request)


@router.post("/v1/mobile/bed/pair")
async def bed_pair(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import MobileBedPairRequest, mobile_bed_pair as _ws

    body = await request.json()
    payload = MobileBedPairRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.post("/v1/mobile/bed/unpair")
async def bed_unpair(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import MobileBedUnpairRequest, mobile_bed_unpair as _ws

    body = await request.json()
    payload = MobileBedUnpairRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


# ── Mobile devices ───────────────────────────────────────────────────────────


@router.get("/v1/mobile/devices")
def list_devices(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_devices as _ws

    return _ws(request=request)


# ── Device commands ──────────────────────────────────────────────────────────


@router.post("/v1/mobile/device-commands")
async def create_device_command(
    request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import UserDeviceCommandRequest, create_mobile_device_command as _ws

    body = await request.json()
    payload = UserDeviceCommandRequest(**body)
    return await asyncio.to_thread(_ws, payload=payload, request=request)


@router.get("/v1/mobile/device-commands/{command_id}")
def device_command_status(
    command_id: str, request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import mobile_device_command_status as _ws

    return _ws(command_id=command_id, request=request)


@router.post("/v1/mobile/device-commands/{command_id}/feedback")
async def device_command_feedback(
    command_id: str, request: Request, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from web_server import DeviceCommandFeedbackRequest, mobile_device_command_feedback as _ws

    body = await request.json()
    payload = DeviceCommandFeedbackRequest(**body)
    return await asyncio.to_thread(_ws, command_id=command_id, payload=payload, request=request)


# ── Device bridge: auth (app→cloud→bed, Plan 6) ──────────────────────────────


@router.post("/v1/device/auth")
async def device_auth_route(request: Request) -> dict[str, Any]:
    from api.device_bridge import DeviceAuthRequest, device_auth as _bridge

    body = await request.json()
    payload = DeviceAuthRequest(**body)
    return await asyncio.to_thread(_bridge, payload)


@router.post("/v1/device/token/refresh")
async def device_token_refresh_route(request: Request) -> dict[str, Any]:
    from api.device_bridge import DeviceTokenRefreshRequest, device_token_refresh as _bridge

    body = await request.json()
    payload = DeviceTokenRefreshRequest(**body)
    return await asyncio.to_thread(_bridge, payload)


@router.get("/v1/device/sync")
async def device_sync_route(device: dict = Depends(get_current_device)) -> dict[str, Any]:
    from api.device_bridge import device_sync as _bridge

    return await asyncio.to_thread(_bridge, device)


@router.post("/v1/device/commands/{command_id}/result")
async def device_command_result_route(
    command_id: str, request: Request, device: dict = Depends(get_current_device)
) -> dict[str, Any]:
    from api.device_bridge import DeviceCommandResultRequest, device_command_result as _bridge

    body = await request.json()
    payload = DeviceCommandResultRequest(**body)
    return await asyncio.to_thread(_bridge, device, command_id, payload)


# ── Live sensor data ─────────────────────────────────────────────────────────


@router.get("/v1/mobile/sensors/live")
def live_sensor_data(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return live sensor readings (temperature, heart rate, pressure, motion)."""
    try:
        from ai.sensor_bridge import SensorBridge

        bridge = SensorBridge()
        return {"ok": True, **bridge.get_environment_summary()}
    except Exception:
        return {
            "ok": True,
            "temperature_c": None,
            "humidity_pct": None,
            "heart_rate_bpm": None,
            "spo2_pct": None,
            "pressure_active": False,
            "motion_active": False,
        }
