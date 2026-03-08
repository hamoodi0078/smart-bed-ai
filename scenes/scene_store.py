from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from Storage.io import atomic_write_json, locked_read_json
from scenes.default_scenes import get_default_scenes
from time_utils import to_iso, utcnow

SCENES_STORE_PATH = Path("data") / "scenes_store.json"
SCENES_STORE_VERSION = 1


class SceneStore:
    def __init__(self, path: str | Path = SCENES_STORE_PATH):
        self._path = Path(path)
        self._state = self._load_or_seed_state()

    def get_all_templates(self) -> list[dict]:
        return [self._normalize_scene_for_return(scene) for scene in self._state["scenes"]]

    def get_template_by_id(self, scene_id: str) -> dict | None:
        scene_key = str(scene_id or "").strip()
        if not scene_key:
            return None
        for scene in self._state["scenes"]:
            if str(scene.get("id", "")).strip() == scene_key:
                return self._normalize_scene_for_return(scene)
        return None

    def save_scene(self, scene: dict) -> dict:
        if not isinstance(scene, dict):
            raise ValueError("scene must be a dict")
        self._validate_required_fields(scene)

        normalized = self._normalize_scene(scene)
        scenes = self._state["scenes"]
        for idx, existing in enumerate(scenes):
            if str(existing.get("id", "")).strip() == normalized["id"]:
                scenes[idx] = normalized
                self._save_state()
                return self._normalize_scene_for_return(normalized)

        scenes.append(normalized)
        self._save_state()
        return self._normalize_scene_for_return(normalized)

    def increment_usage(self, scene_id: str) -> None:
        scene_key = str(scene_id or "").strip()
        if not scene_key:
            return

        for scene in self._state["scenes"]:
            if str(scene.get("id", "")).strip() != scene_key:
                continue
            try:
                current = int(scene.get("usage_count", 0))
            except Exception:
                current = 0
            scene["usage_count"] = max(0, current) + 1
            self._save_state()
            return

    def get_templates_for_api(self) -> list[dict]:
        rows: list[dict] = []
        for scene in self._state["scenes"]:
            tags = scene.get("tags", [])
            rows.append(
                {
                    "id": str(scene.get("id", "")).strip(),
                    "name": str(scene.get("name", "")).strip(),
                    "premium": bool(scene.get("premium", False)),
                    "category": str(scene.get("category", "")).strip(),
                    "tags": list(tags) if isinstance(tags, list) else [],
                    "thumbnail_url": None,
                    "usage_count": self._normalize_usage_count(scene.get("usage_count", 0)),
                }
            )
        return rows

    def _load_or_seed_state(self) -> dict[str, object]:
        if not self._path.exists():
            state = {
                "version": SCENES_STORE_VERSION,
                "scenes": [self._normalize_scene(scene) for scene in get_default_scenes()],
            }
            atomic_write_json(self._path, state)
            return state

        loaded = locked_read_json(self._path)
        if not isinstance(loaded, dict):
            loaded = {}

        raw_scenes = loaded.get("scenes", [])
        scenes: list[dict] = []
        if isinstance(raw_scenes, list):
            for row in raw_scenes:
                if isinstance(row, dict):
                    scenes.append(self._normalize_scene(row))

        return {"version": SCENES_STORE_VERSION, "scenes": scenes}

    def _save_state(self) -> None:
        atomic_write_json(self._path, self._state)

    @staticmethod
    def _validate_required_fields(scene: dict) -> None:
        name = str(scene.get("name", "")).strip()
        if not name:
            raise ValueError("scene name is required")
        if not isinstance(scene.get("light"), dict):
            raise ValueError("scene light is required")
        if not isinstance(scene.get("audio"), dict):
            raise ValueError("scene audio is required")

    @staticmethod
    def _normalize_usage_count(value: object) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = 0
        return max(0, parsed)

    def _normalize_scene(self, scene: dict) -> dict:
        out = deepcopy(scene)
        scene_id = str(out.get("id", "")).strip() or str(uuid4())
        created_at = str(out.get("created_at", "")).strip() or to_iso(utcnow().replace(microsecond=0))
        tags_raw = out.get("tags", [])
        tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []

        light_raw = out.get("light", {})
        audio_raw = out.get("audio", {})
        light = dict(light_raw) if isinstance(light_raw, dict) else {}
        audio = dict(audio_raw) if isinstance(audio_raw, dict) else {}

        return {
            "id": scene_id,
            "name": str(out.get("name", "")).strip(),
            "light": light,
            "audio": audio,
            "premium": bool(out.get("premium", False)),
            "category": str(out.get("category", "")).strip(),
            "tags": tags,
            "is_system_template": bool(out.get("is_system_template", False)),
            "usage_count": self._normalize_usage_count(out.get("usage_count", 0)),
            "created_at": created_at,
        }

    def _normalize_scene_for_return(self, scene: dict) -> dict:
        payload = self._normalize_scene(scene)
        payload["premium"] = bool(payload.get("premium", False))
        return payload
