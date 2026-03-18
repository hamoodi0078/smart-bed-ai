from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from qr_code.generate_qr import generate_device_id, generate_qr_code, register_device
from qr_code.pair_device import get_device_status, pair_device, unpair_device


router = APIRouter(prefix="/v1/qr", tags=["qr"])


class PairDeviceRequest(BaseModel):
    device_id: str
    user_id: str
    user_name: str


class UnpairDeviceRequest(BaseModel):
    device_id: str


class GenerateQRRequest(BaseModel):
    bed_location: str = "Kuwait"


@router.post("/generate")
def generate_qr(request: GenerateQRRequest | None = None) -> dict:
    bed_location = request.bed_location if request else "Kuwait"
    device_id = generate_device_id()
    qr_output = Path(__file__).resolve().parent / f"{device_id}.png"
    record = register_device(device_id, bed_location=bed_location)
    claim_token = str(record.get("claim_token", "") or "")
    qr_image_path = generate_qr_code(device_id, str(qr_output), claim_token=claim_token)
    return {
        "device_id": device_id,
        "qr_image_path": qr_image_path,
        "claim_token": claim_token,
        "pairing_generation": int(record.get("pairing_generation", 1) or 1),
    }


@router.post("/pair")
def pair_qr_device(request: PairDeviceRequest) -> dict:
    return pair_device(
        device_id=request.device_id,
        user_id=request.user_id,
        user_name=request.user_name,
    )


@router.post("/unpair")
def unpair_qr_device(request: UnpairDeviceRequest) -> dict:
    return unpair_device(request.device_id)


@router.get("/status/{device_id}")
def qr_status(device_id: str) -> dict:
    return get_device_status(device_id)
