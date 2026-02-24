from ai.crisis_protocol import build_fast_protocol_message


class SignatureExperienceEngine:
    def detect_experience(self, user_text: str) -> str:
        text = (user_text or "").strip().lower()

        deep_recovery_phrases = (
            "start deep recovery",
            "i need deep reset tonight",
            "run dana deep recovery",
            "start dana deep recovery",
        )
        harmony_phrases = (
            "run couple harmony wake",
            "start partner harmony mode",
            "start couple harmony wake",
            "run partner harmony wake",
        )
        reset_phrases = (
            "90 second reset",
            "90-second reset",
            "reset me now",
            "start 90 second reset",
        )

        if any(p in text for p in deep_recovery_phrases):
            return "dana_deep_recovery"
        if any(p in text for p in harmony_phrases):
            return "couple_harmony_wake"
        if any(p in text for p in reset_phrases):
            return "ninety_second_reset"
        return ""

    def run(
        self,
        user_text: str,
        profile: dict,
        sleep_engine,
        environment_orchestrator,
        led,
        spotify,
        local_music,
    ) -> tuple[str, bool]:
        mode = self.detect_experience(user_text)
        if not mode:
            return "", False

        if mode == "dana_deep_recovery":
            protocol = sleep_engine.stress_decompression_protocol(profile, minutes=6)
            scene = environment_orchestrator.signature_scene("dana_deep_recovery")
            scene_line = environment_orchestrator.apply_scene(led, profile, scene)
            music_ok, music_msg = spotify.play_track_query("calm ambient sleep")
            if not music_ok:
                local_ok, local_msg = local_music.play_query("sleep")
                music_msg = local_msg if local_ok else "Audio unavailable right now."
            coaching = "You are safe here—small calm steps tonight will create deep recovery momentum by morning."
            return (
                f"Dana Deep Recovery™ activated. {scene_line} {protocol} {music_msg} {coaching}".strip(),
                True,
            )

        if mode == "couple_harmony_wake":
            scene = environment_orchestrator.signature_scene("couple_harmony_wake")
            scene_line = environment_orchestrator.apply_scene(led, profile, scene)
            routine = sleep_engine.partner_conflict_safe_routine(profile)
            wake_plan = sleep_engine.adaptive_wake_routine_plan(profile)
            return (
                f"Couple Harmony Wake™ is running. {scene_line} {routine} {wake_plan}"
                " I will keep the wake sequence conflict-safe and premium for both partners.",
                True,
            )

        scene = environment_orchestrator.signature_scene("ninety_second_reset")
        scene_line = environment_orchestrator.apply_scene(led, profile, scene)
        protocol = build_fast_protocol_message()
        return (
            f"90-Second Reset™ started. {scene_line} {protocol}"
            " Stay with my pacing for the next minute and a half.",
            True,
        )
