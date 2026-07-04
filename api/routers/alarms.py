"""Alarm routes — backed by the new Alarm SQLAlchemy model.

Replaces the profile-JSON-based storage in web_server.py.

Routes:
  GET    /v1/mobile/alarms
  POST   /v1/mobile/alarms
  PUT    /v1/mobile/alarms/{alarm_id}
  POST   /v1/mobile/alarms/{alarm_id}/toggle
  DELETE /v1/mobile/alarms/{alarm_id}
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth.middleware import get_current_user

router = APIRouter(prefix="/v1/mobile/alarms", tags=["alarms"])

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class AlarmUpsertRequest(BaseModel):
    time: str = Field(default="07:00", max_length=5)
    label: str = Field(default="", max_length=100)
    enabled: bool = True
    days_of_week: list[int] = Field(default_factory=list)
    wake_style: str = Field(default="gentle_light", max_length=30)
    smart_window_minutes: int = Field(default=0, ge=0, le=90)

    @field_validator("time")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("time must be HH:MM")
        h, m = int(v[:2]), int(v[3:])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("time is out of range")
        return v

    @field_validator("days_of_week")
    @classmethod
    def _validate_days(cls, v: list[int]) -> list[int]:
        if any(d not in range(7) for d in v):
            raise ValueError("days_of_week values must be 0–6")
        return sorted(set(v))


class AlarmToggleRequest(BaseModel):
    enabled: bool


# ── Helpers ───────────────────────────────────────────────────────────────────


def _alarm_to_dict(alarm: Any) -> dict[str, Any]:
    from time_utils import to_iso, ensure_utc

    return {
        "id": alarm.id,
        "time": alarm.time,
        "label": alarm.label,
        "enabled": alarm.enabled,
        "days_of_week": alarm.days_of_week or [],
        "wake_style": alarm.wake_style,
        "smart_window_minutes": alarm.smart_window_minutes,
        "created_at": to_iso(ensure_utc(alarm.created_at)) if alarm.created_at else "",
        "updated_at": to_iso(ensure_utc(alarm.updated_at)) if alarm.updated_at else "",
    }


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("")
def list_alarms(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from database import AlarmRepository

    user_id: str = current_user["sub"]
    repo = AlarmRepository()
    alarms = repo.list_alarms(user_id)
    return {"ok": True, "alarms": [_alarm_to_dict(a) for a in alarms]}


@router.post("")
def create_alarm(
    payload: AlarmUpsertRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from database import AlarmRepository

    user_id: str = current_user["sub"]
    repo = AlarmRepository()
    try:
        alarm = repo.create_alarm(
            user_id=user_id,
            time=payload.time,
            label=payload.label,
            enabled=payload.enabled,
            days_of_week=payload.days_of_week,
            wake_style=payload.wake_style,
            smart_window_minutes=payload.smart_window_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "alarm": _alarm_to_dict(alarm)}


@router.put("/{alarm_id}")
def update_alarm(
    alarm_id: str, payload: AlarmUpsertRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from database import AlarmRepository

    user_id: str = current_user["sub"]
    repo = AlarmRepository()
    alarm = repo.update_alarm(
        alarm_id=alarm_id,
        user_id=user_id,
        time=payload.time,
        label=payload.label,
        enabled=payload.enabled,
        days_of_week=payload.days_of_week,
        wake_style=payload.wake_style,
        smart_window_minutes=payload.smart_window_minutes,
    )
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return {"ok": True, "alarm": _alarm_to_dict(alarm)}


@router.post("/{alarm_id}/toggle")
def toggle_alarm(
    alarm_id: str, payload: AlarmToggleRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from database import AlarmRepository

    user_id: str = current_user["sub"]
    repo = AlarmRepository()
    alarm = repo.update_alarm(alarm_id=alarm_id, user_id=user_id, enabled=payload.enabled)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return {"ok": True, "alarm_id": alarm_id, "enabled": payload.enabled}


@router.delete("/{alarm_id}")
def delete_alarm(alarm_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from database import AlarmRepository

    user_id: str = current_user["sub"]
    repo = AlarmRepository()
    deleted = repo.delete_alarm(alarm_id=alarm_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return {"ok": True, "deleted_alarm_id": alarm_id}
