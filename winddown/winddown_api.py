from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from winddown.breathing_exercise import BreathingExercise
from winddown.led_scenes import WindDownLEDScenes
from winddown.winddown_session import WindDownSession


router = APIRouter(prefix="/v1/winddown", tags=["winddown"])

winddown_session = WindDownSession()
breathing = BreathingExercise()
led_scenes = WindDownLEDScenes()


class StartWindDownRequest(BaseModel):
    user_id: str


@router.post("/start")
def start_winddown(request: StartWindDownRequest) -> dict:
    session = winddown_session.start(request.user_id)
    step_info = winddown_session.get_current_step()
    led_scene = led_scenes.get_scene_for_step(1)
    breathing_steps = breathing.get_instruction_sequence(pattern_name="calm", cycles=3)
    return {
        "session": session,
        "step": step_info,
        "led_scene": led_scene,
        "breathing_instructions": breathing_steps,
    }


@router.post("/next")
def next_winddown_step() -> dict:
    step_result = winddown_session.next_step()
    if step_result == "completed":
        completed = winddown_session.complete()
        return {"status": "completed", "session": completed}
    if step_result is None:
        return {"status": "inactive", "message": "No active wind-down session."}

    step_info = winddown_session.get_current_step()
    led_scene = led_scenes.get_scene_for_step(int(step_result))
    return {
        "status": "active",
        "step": step_info,
        "led_scene": led_scene,
    }


@router.get("/current")
def get_current_step() -> dict:
    if not winddown_session.is_active():
        return {"active": False, "step": None}
    return {"active": True, "step": winddown_session.get_current_step()}


@router.post("/complete")
def complete_winddown() -> dict:
    completed = winddown_session.complete()
    if not completed:
        return {"completed": False, "message": "No active wind-down session."}
    return {"completed": True, "session": completed}


@router.get("/history/{user_id}")
def get_winddown_history(user_id: str) -> dict:
    return {"user_id": user_id, "history": winddown_session.get_history(user_id)}


@router.get("/breathing/{pattern}")
def get_breathing_pattern(pattern: str, cycles: int = 3) -> dict:
    return {
        "pattern": breathing.get_pattern(pattern),
        "sequence": breathing.get_instruction_sequence(pattern_name=pattern, cycles=cycles),
        "message": breathing.get_dana_breathing_message(pattern_name=pattern),
    }


@router.get("/led/{step}")
def get_led_scene(step: int) -> dict:
    return {
        "step": int(step),
        "scene": led_scenes.get_scene_for_step(step),
    }
