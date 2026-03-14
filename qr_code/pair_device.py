from __future__ import annotations

from datetime import datetime, timezone

from qr_code.generate_qr import load_registered_devices, save_registered_devices


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pair_device(device_id: str, user_id: str, user_name: str) -> dict:
    devices = load_registered_devices()
    for device in devices:
        if str(device.get("device_id")) != str(device_id):
            continue
        if bool(device.get("paired")):
            return {"success": False, "message": "Bed already paired to another user"}
        device["paired"] = True
        device["user_id"] = str(user_id)
        device["user_name"] = str(user_name)
        device["paired_at"] = _utc_timestamp()
        save_registered_devices(devices)
        return {"success": True, "message": f"Bed successfully paired to {user_name}"}
    return {"success": False, "message": "Device not found"}


def unpair_device(device_id: str) -> dict:
    devices = load_registered_devices()
    for device in devices:
        if str(device.get("device_id")) != str(device_id):
            continue
        device["paired"] = False
        device.pop("user_id", None)
        device.pop("user_name", None)
        device.pop("paired_at", None)
        save_registered_devices(devices)
        return {"success": True, "message": "Bed successfully unpaired"}
    return {"success": False, "message": "Device not found"}


def get_device_status(device_id: str) -> dict:
    devices = load_registered_devices()
    for device in devices:
        if str(device.get("device_id")) != str(device_id):
            continue
        return {
            "success": True,
            "device_id": str(device.get("device_id", "")),
            "paired": bool(device.get("paired", False)),
            "bed_location": str(device.get("bed_location", "")),
            "created_at": device.get("created_at"),
            "user_id": device.get("user_id"),
            "user_name": device.get("user_name"),
            "paired_at": device.get("paired_at"),
        }
    return {"success": False, "message": "Device not found"}
