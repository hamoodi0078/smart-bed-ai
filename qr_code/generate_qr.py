from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
import secrets
from urllib.parse import urlencode

import qrcode


QR_CODE_DIR = Path(__file__).resolve().parent
REGISTERED_DEVICES_PATH = QR_CODE_DIR / "registered_devices.json"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_registered_devices() -> list[dict]:
    if not REGISTERED_DEVICES_PATH.exists():
        return []
    try:
        payload = json.loads(REGISTERED_DEVICES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def save_registered_devices(devices: list[dict]) -> None:
    REGISTERED_DEVICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTERED_DEVICES_PATH.write_text(json.dumps(devices, indent=2), encoding="utf-8")


def generate_device_id() -> str:
    letters: list[str] = []
    while len(letters) < 4:
        letters.extend(char for char in uuid.uuid4().hex.upper() if char.isalpha())
    suffix = "".join(letters[:4])
    return f"DANA-KW-001-{suffix}"


def _new_claim_token() -> str:
    return secrets.token_urlsafe(18)


def _safe_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def generate_qr_code(device_id: str, output_path: str, *, claim_token: str = "") -> str:
    params = {"device_id": str(device_id)}
    token = str(claim_token or "").strip()
    if token:
        params["claim_token"] = token
    deep_link = f"danah://connect?{urlencode(params)}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return str(destination)


def register_device(device_id: str, bed_location: str = "Kuwait", *, claim_token: str = "") -> dict:
    normalized_device_id = str(device_id)
    existing: dict | None = None
    devices: list[dict] = []
    for item in load_registered_devices():
        if str(item.get("device_id", "")) == normalized_device_id and existing is None:
            existing = item
            continue
        devices.append(item)

    existing_claim = str((existing or {}).get("claim_token", "")).strip()
    resolved_claim = str(claim_token or "").strip() or existing_claim or _new_claim_token()
    previous_generation = _safe_int((existing or {}).get("pairing_generation", 0), 0)
    claim_changed = not existing or resolved_claim != existing_claim
    pairing_generation = previous_generation + (1 if claim_changed else 0)
    now_iso = _utc_timestamp()
    record = {
        "device_id": normalized_device_id,
        "bed_location": str(bed_location or "Kuwait"),
        "created_at": str((existing or {}).get("created_at", "") or now_iso),
        "paired": bool((existing or {}).get("paired", False)),
        "claim_token": resolved_claim,
        "claim_token_rotated_at": now_iso if claim_changed else str((existing or {}).get("claim_token_rotated_at", "") or now_iso),
        "pairing_generation": pairing_generation,
    }
    if bool(record.get("paired", False)):
        if isinstance(existing, dict):
            if "user_id" in existing:
                record["user_id"] = existing["user_id"]
            if "user_name" in existing:
                record["user_name"] = existing["user_name"]
            if "paired_at" in existing:
                record["paired_at"] = existing["paired_at"]
    devices.append(record)
    save_registered_devices(devices)
    return record


if __name__ == "__main__":
    sample_device_id = generate_device_id()
    sample_output = QR_CODE_DIR / "sample_qr.png"
    sample_record = register_device(sample_device_id)
    generate_qr_code(sample_device_id, str(sample_output), claim_token=str(sample_record.get("claim_token", "") or ""))
    print(f"Generated sample QR for {sample_device_id} at {sample_output}")
