from __future__ import annotations

import datetime
import json
import os

from fastapi import APIRouter
from pydantic import BaseModel

from sleep_tracking.sleep_score import SleepScoreCalculator
from sleep_tracking.sleep_session import SleepSession
from sleep_tracking.weekly_report import WeeklyReportGenerator


router = APIRouter(prefix="/v1/sleep", tags=["sleep"])

sleep_session_service = SleepSession()
sleep_score_calculator = SleepScoreCalculator()
weekly_report_generator = WeeklyReportGenerator()


class SleepStartRequest(BaseModel):
    user_id: str


class SleepEndRequest(BaseModel):
    user_id: str
    quality_rating: int | None = None


def _parse_hour(timestamp: str, default_hour: int) -> int:
    try:
        return datetime.datetime.fromisoformat(str(timestamp)).hour
    except ValueError:
        return int(default_hour)


def _update_log_score(session_id: str, score: int) -> None:
    log_file = os.path.join(os.path.dirname(__file__), "sessions_log.json")
    if not os.path.exists(log_file):
        return
    try:
        with open(log_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, list):
        return

    updated = False
    for item in reversed(payload):
        if not isinstance(item, dict):
            continue
        if str(item.get("session_id", "")) == str(session_id):
            item["sleep_score"] = int(score)
            updated = True
            break
    if not updated:
        return
    with open(log_file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


@router.post("/start")
def start_sleep(request: SleepStartRequest) -> dict:
    session = sleep_session_service.start_session(user_id=request.user_id)
    return {"started": True, "session": session}


@router.post("/end")
def end_sleep(request: SleepEndRequest) -> dict:
    active = sleep_session_service.get_active_session()
    if not active:
        return {"ended": False, "message": "No active sleep session."}
    if str(active.get("user_id")) != str(request.user_id):
        return {"ended": False, "message": "Active session belongs to another user."}

    quality = request.quality_rating
    if quality is not None:
        quality = max(1, min(5, int(quality)))

    completed = sleep_session_service.end_session(quality_rating=quality)
    if not completed:
        return {"ended": False, "message": "No active sleep session."}

    score = sleep_score_calculator.calculate_score(
        total_hours=float(completed.get("total_hours", 0.0) or 0.0),
        quality_rating=int(completed.get("quality_rating") or 3),
        sleep_hour=_parse_hour(completed.get("sleep_start", ""), default_hour=23),
        wake_hour=_parse_hour(completed.get("sleep_end", ""), default_hour=7),
    )
    _update_log_score(session_id=str(completed.get("session_id", "")), score=score)
    label = sleep_score_calculator.get_score_label(score)
    advice = sleep_score_calculator.get_score_advice(score, float(completed.get("total_hours", 0.0) or 0.0))
    completed["sleep_score"] = score

    return {
        "ended": True,
        "session": completed,
        "score": score,
        "label": label,
        "advice": advice,
    }


@router.get("/active/{user_id}")
def get_active_sleep(user_id: str) -> dict:
    active = sleep_session_service.get_active_session()
    if not active:
        return {"active": None}
    if str(active.get("user_id")) != str(user_id):
        return {"active": None}
    return {"active": active}


@router.get("/history/{user_id}")
def get_sleep_history(user_id: str, limit: int = 30) -> dict:
    history = sleep_session_service.get_session_history(user_id=user_id, limit=limit)
    return {"user_id": user_id, "history": history}


@router.get("/score/{user_id}")
def get_latest_sleep_score(user_id: str) -> dict:
    history = sleep_session_service.get_session_history(user_id=user_id, limit=1)
    if not history:
        return {"found": False, "message": "No completed sleep session found."}
    latest = history[-1]
    score = sleep_score_calculator.calculate_score(
        total_hours=float(latest.get("total_hours", 0.0) or 0.0),
        quality_rating=int(latest.get("quality_rating") or 3),
        sleep_hour=_parse_hour(latest.get("sleep_start", ""), default_hour=23),
        wake_hour=_parse_hour(latest.get("sleep_end", ""), default_hour=7),
    )
    return {
        "found": True,
        "score": score,
        "label": sleep_score_calculator.get_score_label(score),
        "advice": sleep_score_calculator.get_score_advice(score, float(latest.get("total_hours", 0.0) or 0.0)),
        "session_id": latest.get("session_id"),
    }


@router.get("/report/weekly/{user_id}")
def get_weekly_report(user_id: str) -> dict:
    report = weekly_report_generator.generate_report(user_id=user_id)
    return {"user_id": user_id, "report": report}


@router.get("/report/summary/{user_id}")
def get_weekly_summary(user_id: str) -> dict:
    report = weekly_report_generator.generate_report(user_id=user_id)
    summary = weekly_report_generator.get_report_summary_text(report)
    return {"user_id": user_id, "summary": summary}
