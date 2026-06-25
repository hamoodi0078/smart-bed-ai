"""Smart Ring pairing and status routes.

Allows the mobile app to scan for nearby COLMI rings via the Pi's Bluetooth,
pair with a chosen ring, and query real-time ring status.

The phone never opens its own Bluetooth — it calls these HTTP endpoints and
the Raspberry Pi handles all BLE communication.

Routes:
  POST /v1/ring/scan     — scan for nearby COLMI rings (runs on Pi's BT adapter)
  POST /v1/ring/pair     — save ring address and reconnect client
  GET  /v1/ring/status   — current connection state + last biometric readings
  POST /v1/ring/unpair   — forget the ring address and stop the client
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.middleware import get_current_user

router = APIRouter(tags=["ring"])
logger = logging.getLogger("api.ring")

# Module-level reference to the running ring client, injected by app_entry.py
# at startup via `ring_router.set_ring_client(ring_client)`.
_ring_client: Any = None
_ring_automation: Any = None


def set_ring_client(client: Any, automation: Any = None) -> None:
    """Called by app_entry.py after ring_client is initialised."""
    global _ring_client, _ring_automation
    _ring_client = client
    _ring_automation = automation


# ── Request / Response models ─────────────────────────────────────────────────

class RingPairRequest(BaseModel):
    address: str = Field(..., description="BLE MAC address of the ring, e.g. 'AA:BB:CC:DD:EE:FF'")
    model: str = Field("colmi_r02", description="Ring model: colmi_r02 | colmi_r06 | colmi_r10")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client() -> Any:
    if _ring_client is None:
        raise HTTPException(status_code=503, detail="Ring client is not initialised. Restart the bed runtime.")
    return _ring_client


def _save_ring_address(address: str, model: str) -> None:
    """Persist ring address to user_profile.json so it survives reboots."""
    try:
        from Storage.user_profile import load_profile, save_profile
        profile = load_profile() or {}
        profile.setdefault("hardware", {})["ring_ble_address"] = address.strip().upper()
        profile["hardware"]["ring_model"] = model.strip()
        save_profile(profile)
        logger.info("Ring address saved to profile: %s (%s)", address, model)
    except Exception as exc:
        logger.warning("Could not persist ring address to profile: %s", exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/v1/ring/scan")
async def ring_scan(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger a BLE scan on the Pi and return discovered COLMI rings.

    The scan runs for up to 10 seconds. Returns an empty list if bleak is not
    installed or no rings are found nearby.
    """
    client = _get_client()

    if not getattr(client, "is_available", lambda: False)():
        return {
            "ok": True,
            "rings": [],
            "message": "BLE not available on this device. Install bleak: pip install bleak>=0.21.0",
        }

    try:
        rings = await asyncio.wait_for(client.scan(timeout=10.0), timeout=15.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="BLE scan timed out.")
    except Exception as exc:
        logger.error("BLE scan error: %s", exc)
        raise HTTPException(status_code=500, detail=f"BLE scan failed: {exc}")

    ring_list = [
        {
            "address": r.address,
            "name": r.name,
            "rssi": r.rssi,
            "model": getattr(r.model, "value", str(r.model)),
        }
        for r in rings
    ]

    return {
        "ok": True,
        "rings": ring_list,
        "count": len(ring_list),
        "message": f"Found {len(ring_list)} ring(s)." if ring_list else "No COLMI rings found nearby.",
    }


@router.post("/v1/ring/pair")
async def ring_pair(
    body: RingPairRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Pair with a specific ring by its BLE address.

    Saves the address to user_profile.json and reconnects the ring client.
    The ring will auto-reconnect on future reboots.
    """
    client = _get_client()

    address = body.address.strip().upper()
    if not address:
        raise HTTPException(status_code=422, detail="BLE address is required.")

    if not getattr(client, "is_available", lambda: False)():
        raise HTTPException(
            status_code=503,
            detail="BLE not available. Install bleak: pip install bleak>=0.21.0",
        )

    # Attempt BLE connection
    try:
        connected = await asyncio.wait_for(client.connect(address), timeout=20.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="BLE connection timed out.")
    except Exception as exc:
        logger.error("Ring pair error: %s", exc)
        raise HTTPException(status_code=500, detail=f"BLE connection failed: {exc}")

    if not connected:
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to ring at {address}. Make sure it is nearby and charged.",
        )

    # Persist for future reboots
    _save_ring_address(address, body.model)

    return {
        "ok": True,
        "status": "paired",
        "address": address,
        "model": body.model,
        "message": f"Ring paired successfully at {address}.",
    }


@router.get("/v1/ring/status")
def ring_status(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return current ring connection state and latest biometric readings."""
    client = _get_client()

    status = {}
    if hasattr(client, "get_status_dict"):
        try:
            status = client.get_status_dict() or {}
        except Exception as exc:
            logger.warning("ring.get_status_dict() failed: %s", exc)

    # Supplement with live readings if available
    hr_bpm: int | None = None
    spo2_pct: int | None = None
    battery_pct: int | None = None

    if hasattr(client, "last_hr"):
        hr = client.last_hr
        hr_bpm = getattr(hr, "heart_rate_bpm", None)
    if hasattr(client, "last_spo2"):
        spo2 = client.last_spo2
        spo2_pct = getattr(spo2, "spo2_pct", None)
    if hasattr(client, "battery_pct"):
        battery_pct = int(client.battery_pct or 0) or None

    return {
        "ok": True,
        "connected": bool(getattr(client, "is_connected", False)),
        "status_line": client.status_line() if hasattr(client, "status_line") else "unknown",
        "heart_rate_bpm": hr_bpm,
        "spo2_pct": spo2_pct,
        "battery_pct": battery_pct,
        **status,
    }


@router.post("/v1/ring/unpair")
def ring_unpair(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Forget the ring address and stop background BLE client."""
    client = _get_client()

    if hasattr(client, "stop_background"):
        try:
            client.stop_background()
        except Exception as exc:
            logger.warning("stop_background error: %s", exc)

    # Clear from profile
    try:
        from Storage.user_profile import load_profile, save_profile
        profile = load_profile() or {}
        hw = profile.get("hardware", {})
        hw.pop("ring_ble_address", None)
        hw.pop("ring_model", None)
        profile["hardware"] = hw
        save_profile(profile)
    except Exception as exc:
        logger.warning("Could not clear ring address from profile: %s", exc)

    return {"ok": True, "status": "unpaired", "message": "Ring disconnected and address forgotten."}
