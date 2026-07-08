"""Alarm routes — DB-backed, speaking the Flutter app's contract.

Contract (mobile_app/lib/src/core/models.dart AlarmSchedule):
  fields: alarm_id, time, days (ISO 1=Mon…7=Sun), enabled, label, sound,
  vibrate; POST is an upsert and returns the full refreshed alarm list
  (api_client.dart upsertAlarm reads json["alarms"]).

Routes:
  GET    /v1/mobile/alarms
  POST   /v1/mobile/alarms                     (upsert)
  POST   /v1/mobile/alarms/{alarm_id}/toggle
  DELETE /v1/mobile/alarms/{alarm_id}
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth.middleware import get_current_user

router = APIRouter(prefix="/v1/mobile/alarms", tags=["alarms"])

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class AlarmUpsertRequest(BaseModel):
    alarm_id: str = Field(default="", max_length=36)
    time: str = Field(default="07:00", max_length=5)
    label: str = Field(default="", max_length=100)
    enabled: bool = True
    days: list[int] = Field(default_factory=list)  # ISO weekdays 1=Mon … 7=Sun
    sound: str = Field(default="default", max_length=64)
    vibrate: bool = True

    @field_validator("time")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("time must be HH:MM")
        h, m = int(v[:2]), int(v[3:])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("time is out of range")
        return v

    @field_validator("days")
    @classmethod
    def _validate_days(cls, v: list[int]) -> list[int]:
        if any(d not in range(1, 8) for d in v):
            raise ValueError("days values must be 1–7 (ISO weekday, Monday=1)")
        return sorted(set(v))


class AlarmToggleRequest(BaseModel):
    enabled: bool


def _next_trigger_at_utc(time_str: str, days: list[int]) -> str:
    """Next UTC instant matching HH:MM on one of the ISO weekdays (any day if empty)."""
    from time_utils import to_iso

    now = datetime.now(timezone.utc)
    hour, minute = int(time_str[:2]), int(time_str[3:])
    for offset in range(0, 8):
        candidate = (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= now:
            continue
        if not days or candidate.isoweekday() in days:
            return to_iso(candidate)
    return ""


def _alarm_to_dict(alarm: Any) -> dict[str, Any]:
    from time_utils import to_iso, ensure_utc

    days = sorted(d + 1 for d in (alarm.days_of_week or []))  # DB 0–6 → ISO 1–7
    return {
        "alarm_id": alarm.id,
        "time": alarm.time,
        "label": alarm.label,
        "enabled": alarm.enabled,
        "days": days,
        "sound": alarm.sound,
        "vibrate": alarm.vibrate,
        "created_at": to_iso(ensure_utc(alarm.created_at)) if alarm.created_at else "",
        "updated_at": to_iso(ensure_utc(alarm.updated_at)) if alarm.updated_at else "",
        "next_trigger_at_utc": _next_trigger_at_utc(alarm.time, days) if alarm.enabled else "",
    }


def _alarm_list(repo: Any, user_id: str) -> dict[str, Any]:
    return {"ok": True, "alarms": [_alarm_to_dict(a) for a in repo.list_alarms(user_id)]}


@router.get("")
def list_alarms(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from database import AlarmRepository

    return _alarm_list(AlarmRepository(), current_user["sub"])


@router.post("")
def upsert_alarm(
    payload: AlarmUpsertRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from database import AlarmRepository

    user_id: str = current_user["sub"]
    repo = AlarmRepository()
    days_db = [d - 1 for d in payload.days]  # ISO 1–7 → DB 0–6
    if payload.alarm_id:
        alarm = repo.update_alarm(
            alarm_id=payload.alarm_id,
            user_id=user_id,
            time=payload.time,
            label=payload.label,
            enabled=payload.enabled,
            days_of_week=days_db,
            sound=payload.sound,
            vibrate=payload.vibrate,
        )
        if alarm is None:
            raise HTTPException(status_code=404, detail="Alarm not found")
    else:
        try:
            repo.create_alarm(
                user_id=user_id,
                time=payload.time,
                label=payload.label,
                enabled=payload.enabled,
                days_of_week=days_db,
                sound=payload.sound,
                vibrate=payload.vibrate,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _alarm_list(repo, user_id)


@router.post("/{alarm_id}/toggle")
def toggle_alarm(
    alarm_id: str, payload: AlarmToggleRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from database import AlarmRepository

    alarm = AlarmRepository().update_alarm(
        alarm_id=alarm_id, user_id=current_user["sub"], enabled=payload.enabled
    )
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return {"ok": True, "alarm_id": alarm_id, "enabled": payload.enabled}


@router.delete("/{alarm_id}")
def delete_alarm(alarm_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from database import AlarmRepository

    deleted = AlarmRepository().delete_alarm(alarm_id=alarm_id, user_id=current_user["sub"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return {"ok": True, "deleted_alarm_id": alarm_id}
