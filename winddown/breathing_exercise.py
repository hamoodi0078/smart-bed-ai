from __future__ import annotations


class BreathingExercise:
    PATTERNS = {
        "box": {
            "inhale": 4,
            "hold_in": 4,
            "exhale": 4,
            "hold_out": 4,
            "name": "Box Breathing",
        },
        "478": {
            "inhale": 4,
            "hold_in": 7,
            "exhale": 8,
            "hold_out": 0,
            "name": "4-7-8 Technique",
        },
        "calm": {
            "inhale": 5,
            "hold_in": 2,
            "exhale": 6,
            "hold_out": 0,
            "name": "Calm Breathing",
        },
    }

    def get_pattern(self, pattern_name: str = "calm") -> dict:
        key = str(pattern_name or "calm").strip().lower()
        selected = self.PATTERNS.get(key, self.PATTERNS["calm"])
        return dict(selected)

    def get_instruction_sequence(self, pattern_name: str = "calm", cycles: int = 3) -> list[dict]:
        pattern = self.get_pattern(pattern_name)
        total_cycles = max(1, int(cycles))
        sequence: list[dict] = []

        for cycle in range(1, total_cycles + 1):
            sequence.append({"action": "Inhale", "seconds": int(pattern["inhale"]), "cycle": cycle})
            if int(pattern["hold_in"]) > 0:
                sequence.append(
                    {"action": "Hold", "seconds": int(pattern["hold_in"]), "cycle": cycle}
                )
            sequence.append({"action": "Exhale", "seconds": int(pattern["exhale"]), "cycle": cycle})
            if int(pattern["hold_out"]) > 0:
                sequence.append(
                    {"action": "Hold Out", "seconds": int(pattern["hold_out"]), "cycle": cycle}
                )

        return sequence

    def get_dana_breathing_message(self, pattern_name: str = "calm") -> str:
        pattern = self.get_pattern(pattern_name)
        return (
            "Let's begin. "
            f"Breathe in slowly for {pattern['inhale']} counts... "
            f"hold... and release for {pattern['exhale']} counts. "
            "Let your body relax."
        )
