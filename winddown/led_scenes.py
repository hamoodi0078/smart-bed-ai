from __future__ import annotations


class WindDownLEDScenes:
    WINDDOWN_SCENES = {
        "step_1": {
            "color": "#FF8C42",
            "brightness": 60,
            "effect": "breathing_pulse",
            "transition_seconds": 5,
        },
        "step_2": {
            "color": "#FF6B35",
            "brightness": 30,
            "effect": "slow_dim",
            "transition_seconds": 10,
        },
        "step_3": {
            "color": "#8B4A2B",
            "brightness": 15,
            "effect": "steady",
            "transition_seconds": 15,
        },
        "step_4": {
            "color": "#000000",
            "brightness": 0,
            "effect": "fade_off",
            "transition_seconds": 30,
        },
        "prayer_mode": {
            "color": "#FFF5E0",
            "brightness": 40,
            "effect": "soft_glow",
            "transition_seconds": 5,
        },
        "morning_wake": {
            "color": "#FFD700",
            "brightness": 20,
            "effect": "sunrise_fade",
            "transition_seconds": 120,
        },
    }

    def get_scene_for_step(self, step: int) -> dict:
        scene_name = f"step_{int(step)}"
        return dict(self.WINDDOWN_SCENES.get(scene_name, self.WINDDOWN_SCENES["step_1"]))

    def get_prayer_scene(self) -> dict:
        return dict(self.WINDDOWN_SCENES["prayer_mode"])

    def get_morning_scene(self) -> dict:
        return dict(self.WINDDOWN_SCENES["morning_wake"])

    def get_scene_command(self, scene_name: str) -> dict:
        name = str(scene_name or "").strip()
        scene = self.WINDDOWN_SCENES.get(name, {})
        return {
            "command": "set_led_scene",
            "scene_name": name,
            "scene": dict(scene),
        }
