from datetime import datetime


class EnvironmentOrchestrator:
    def ensure_shape(self, profile: dict):
        profile.setdefault("environment", {})
        env = profile["environment"]
        env.setdefault("last_scene_key", "")
        env.setdefault("last_scene_applied_at", "")
        env.setdefault("last_preload_phase", "")
        env.setdefault("last_preload_at", "")

    def choose_scene(
        self,
        emotion_state: str,
        recovery_mode: bool,
        challenge_level: int,
        personality: str,
    ) -> dict:
        emotion = (emotion_state or "neutral").lower().strip()
        persona = (personality or "therapist").lower().strip()

        if recovery_mode or emotion in ("distressed", "low_energy"):
            return {
                "key": "calm_recovery",
                "animation": "breathing",
                "color": "cyan",
                "brightness": 0.25,
                "line": "Environment scene: calm recovery.",
            }

        if emotion == "motivated":
            return {
                "key": "focus_momentum",
                "animation": "pulse",
                "color": "orange" if persona == "coach" else "green",
                "brightness": 0.45,
                "line": "Environment scene: focus momentum.",
            }

        if int(challenge_level) >= 4:
            return {
                "key": "discipline_night",
                "animation": "wave",
                "color": "blue",
                "brightness": 0.35,
                "line": "Environment scene: discipline night.",
            }

        return {
            "key": "balanced_default",
            "animation": "solid",
            "color": "white",
            "brightness": 0.4,
            "line": "Environment scene: balanced default.",
        }

    def apply_scene(self, led, profile: dict, scene: dict) -> str:
        self.ensure_shape(profile)
        if not scene:
            return ""

        led.set_user_animation(scene.get("animation", "solid"))
        led.set_color_value(scene.get("color", "white"))
        led.set_user_brightness(float(scene.get("brightness", 0.4)))

        profile["environment"]["last_scene_key"] = scene.get("key", "")
        profile["environment"]["last_scene_applied_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
        return scene.get("line", "")

    def status_line(self, profile: dict) -> str:
        self.ensure_shape(profile)
        env = profile.get("environment", {})
        key = env.get("last_scene_key", "none") or "none"
        ts = env.get("last_scene_applied_at", "")
        if ts:
            return f"Environment status: scene={key}, last_applied={ts}."
        return f"Environment status: scene={key}."

    def signature_scene(self, mode: str) -> dict:
        key = (mode or "").strip().lower()
        if key == "dana_deep_recovery":
            return {
                "key": "signature_dana_deep_recovery",
                "animation": "breathing",
                "color": "warmwhite",
                "brightness": 0.18,
                "line": "Environment scene: Dana Deep Recovery warm decompression.",
            }
        if key == "couple_harmony_wake":
            return {
                "key": "signature_couple_harmony_wake",
                "animation": "wave",
                "color": "cyan",
                "brightness": 0.32,
                "line": "Environment scene: Couple Harmony Wake balanced ramp.",
            }
        if key == "ninety_second_reset":
            return {
                "key": "signature_90_second_reset",
                "animation": "pulse",
                "color": "blue",
                "brightness": 0.24,
                "line": "Environment scene: 90-Second Reset focus safety.",
            }
        return {
            "key": "signature_default",
            "animation": "solid",
            "color": "white",
            "brightness": 0.35,
            "line": "Environment scene: signature default.",
        }

    @staticmethod
    def _phase_key(text: str) -> str:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return ""
        if any(
            token in normalized for token in ("sleep", "wind down", "wind-down", "bedtime", "night")
        ):
            return "sleep"
        if any(token in normalized for token in ("morning", "wake", "good morning", "sunrise")):
            return "morning"
        return ""

    def preload_transition_for_response(self, led, profile: dict, response_text: str) -> dict:
        self.ensure_shape(profile)
        phase = self._phase_key(response_text)
        if not phase:
            return {"started": False, "phase": "", "line": ""}

        if phase == "sleep":
            led.set_user_animation("breathing")
            led.set_color_value("warmwhite")
            led.set_user_brightness(0.22)
            line = "Hardware preload: started sleep transition ramp."
        else:
            led.set_user_animation("wave")
            led.set_color_value("cyan")
            led.set_user_brightness(0.34)
            line = "Hardware preload: started morning transition ramp."

        profile["environment"]["last_preload_phase"] = phase
        profile["environment"]["last_preload_at"] = datetime.now().isoformat(timespec="seconds")
        return {"started": True, "phase": phase, "line": line}
