from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from Storage.io import atomic_write_json, locked_read_json

WINDDOWN_SESSION_PATH = Path("data") / "winddown_session.json"


class WindDownModel:
    def __init__(self, path: str | Path = WINDDOWN_SESSION_PATH):
        self._path = Path(path)

    def create_session(self, duration_minutes: int = 10) -> dict:
        session = {
            "flow_id": str(uuid4()),
            "user_id": "default_user",
            "status": "idle",
            "duration_minutes": int(duration_minutes),
            "started_at": None,
            "completed_at": None,
            "current_step": 0,
            "interrupted": False,
            "steps": self._default_steps(),
        }
        atomic_write_json(self._path, session)
        return deepcopy(session)

    def get_current_session(self) -> dict | None:
        data = locked_read_json(self._path)
        if not isinstance(data, dict) or not data:
            return None
        flow_id = str(data.get("flow_id", "")).strip()
        if not flow_id:
            return None
        return deepcopy(data)

    def get_step(self, step_number: int) -> dict | None:
        session = self.get_current_session()
        if not isinstance(session, dict):
            return None
        steps = session.get("steps", [])
        if not isinstance(steps, list):
            return None

        for step in steps:
            if not isinstance(step, dict):
                continue
            if int(step.get("step", 0) or 0) == int(step_number):
                return deepcopy(step)
        return None

    def get_breathing_timings(self) -> list[dict]:
        session = self.get_current_session()
        steps = session.get("steps", []) if isinstance(session, dict) else self._default_steps()
        if not isinstance(steps, list):
            return []

        timings: list[dict] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            prompt = str(step.get("prompt", "")).strip()
            if not prompt:
                continue
            timings.append(
                {
                    "minute": int(step.get("start_minute", 0) or 0),
                    "prompt": prompt,
                }
            )
        return timings

    @staticmethod
    def _default_steps() -> list[dict]:
        return [
            {
                "step": 1,
                "name": "breathing",
                "start_minute": 0,
                "end_minute": 2,
                "prompt": "Breathe in... hold... breathe out...",
                "light": {"color": "#FF8C42", "intensity": 60},
                "audio": {"type": "none", "volume": 0},
            },
            {
                "step": 2,
                "name": "dim_lights",
                "start_minute": 2,
                "end_minute": 5,
                "prompt": "Relax your body... let go of the day...",
                "light": {"color": "#FF6B35", "intensity": 30},
                "audio": {"type": "fireplace", "volume": 20},
            },
            {
                "step": 3,
                "name": "ambient_audio",
                "start_minute": 5,
                "end_minute": 8,
                "prompt": "You are safe. You are at peace.",
                "light": {"color": "#FF4500", "intensity": 15},
                "audio": {"type": "ocean_waves", "volume": 25},
            },
            {
                "step": 4,
                "name": "final_dim",
                "start_minute": 8,
                "end_minute": 10,
                "prompt": "Sleep well. Goodnight.",
                "light": {"color": "#1A0033", "intensity": 5},
                "audio": {"type": "none", "volume": 0},
            },
        ]
