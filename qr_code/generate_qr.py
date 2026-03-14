from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

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


def generate_qr_code(device_id: str, output_path: str) -> str:
    deep_link = f"danah://connect?device_id={device_id}"
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


def register_device(device_id: str, bed_location: str = "Kuwait") -> dict:
    record = {
        "device_id": str(device_id),
        "bed_location": str(bed_location or "Kuwait"),
        "created_at": _utc_timestamp(),
        "paired": False,
    }
    devices = [item for item in load_registered_devices() if item.get("device_id") != device_id]
    devices.append(record)
    save_registered_devices(devices)
    return record


if __name__ == "__main__":
    sample_device_id = generate_device_id()
    sample_output = QR_CODE_DIR / "sample_qr.png"
    generate_qr_code(sample_device_id, str(sample_output))
    register_device(sample_device_id)
    print(f"Generated sample QR for {sample_device_id} at {sample_output}")
