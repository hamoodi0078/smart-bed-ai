from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dana.dana_core import DanaCore
from dana.personality import DanaPersonality, PERSONALITY_CONFIGS
from dana.therapist import DanaTherapist
from dana.coach import DanaCoach
from dana.guide import DanaGuide


router = APIRouter(prefix="/v1/dana", tags=["dana"])

_sessions: dict[str, DanaCore] = {}
_therapist = DanaTherapist()
_coach = DanaCoach()
_guide = DanaGuide()


class SwitchPersonalityRequest(BaseModel):
    personality: str
    user_id: str
    user_name: str = "Hamoud"


class StressRequest(BaseModel):
    stress_level: int


def _parse_personality(value: str) -> DanaPersonality:
    try:
        return DanaPersonality(str(value or "").strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid personality. Use coach, guide, or therapist.",
        ) from exc


@router.get("/personalities")
def list_personalities() -> dict:
    return {
        personality.value: {
            "name": config.name,
            "tagline": config.tagline,
            "emoji": config.emoji,
            "color_hex": config.color_hex,
        }
        for personality, config in PERSONALITY_CONFIGS.items()
    }


@router.post("/personality/switch")
def switch_personality(request: SwitchPersonalityRequest) -> dict:
    personality = _parse_personality(request.personality)
    core = _sessions.get(request.user_id)
    if core is None:
        core = DanaCore(personality=personality, user_name=request.user_name)
        _sessions[request.user_id] = core
    else:
        core.user_name = request.user_name
    confirmation = core.switch_personality(personality)
    return {
        "success": True,
        "user_id": request.user_id,
        "personality": personality.value,
        "message": confirmation,
    }


@router.get("/greeting/{personality}")
def get_greeting(personality: str, user_name: str = "Hamoud") -> dict:
    parsed = _parse_personality(personality)
    core = DanaCore(personality=parsed, user_name=user_name)
    return {"personality": parsed.value, "greeting": core.get_greeting()}


@router.get("/message/bedtime/{personality}")
def get_bedtime_message(personality: str, hour: int = 22, user_name: str = "Hamoud") -> dict:
    parsed = _parse_personality(personality)
    core = DanaCore(personality=parsed, user_name=user_name)
    return {
        "personality": parsed.value,
        "hour": hour,
        "message": core.get_bedtime_message(hour),
    }


@router.get("/message/windown/{step}")
def get_windown_message(step: int) -> dict:
    return {"step": step, "message": _guide.get_wind_down_message(step)}


@router.get("/checkin/questions")
def get_checkin_questions() -> dict:
    return {"questions": _therapist.get_checkin_questions()}


@router.post("/checkin/stress")
def get_stress_response(request: StressRequest) -> dict:
    level = max(1, min(10, int(request.stress_level)))
    return {"stress_level": level, "message": _therapist.get_stress_response(level)}


@router.get("/streak/{days}")
def get_streak_message(days: int) -> dict:
    safe_days = max(0, int(days))
    return {"days": safe_days, "message": _coach.get_streak_message(safe_days)}
