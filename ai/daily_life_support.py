from datetime import datetime


class DailyLifeSupport:
    def ensure_shape(self, profile: dict):
        profile.setdefault("daily_life", {})
        dl = profile["daily_life"]
        dl.setdefault("overthinking_entries", [])
        dl.setdefault("last_mood_bundle", "")
        dl.setdefault("last_coaching_tone", "")

        profile.setdefault("preferences", {})
        profile["preferences"].setdefault("language", "auto")
        profile["preferences"].setdefault("sleep_target_hours", 8.0)

    def sleep_debt_summary(self, profile: dict) -> str:
        self.ensure_shape(profile)
        sleep = profile.get("sleep", {})
        bed_hist = sleep.get("bedtime_history", [])
        wake_hist = sleep.get("wake_history", [])
        if not bed_hist or not wake_hist:
            return "Sleep debt report: not enough sleep logs yet. Use 'log bedtime' and 'log wake'."

        target_hours = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)

        pairs = min(len(bed_hist), len(wake_hist))
        total_hours = 0.0
        nights = 0
        for idx in range(1, pairs + 1):
            try:
                bed = datetime.fromisoformat(str(bed_hist[-idx]))
                wake = datetime.fromisoformat(str(wake_hist[-idx]))
                if wake <= bed:
                    continue
                dur_h = (wake - bed).total_seconds() / 3600.0
                if 2.0 <= dur_h <= 16.0:
                    total_hours += dur_h
                    nights += 1
                if nights >= 7:
                    break
            except Exception:
                continue

        if nights == 0:
            return "Sleep debt report: not enough valid sleep intervals in recent logs."

        target_total = target_hours * nights
        delta = target_total - total_hours
        avg = total_hours / nights
        if delta <= 0:
            return (
                f"Sleep debt report: no debt in last {nights} night(s). "
                f"Average sleep={avg:.1f}h/night (target {target_hours:.1f}h)."
            )

        return (
            f"Sleep debt report: about {delta:.1f}h owed across last {nights} night(s). "
            f"Average sleep={avg:.1f}h/night (target {target_hours:.1f}h)."
        )

    def log_overthinking(self, profile: dict, text: str) -> str:
        self.ensure_shape(profile)
        clean = (text or "").strip()
        if not clean:
            return "Use: overthinking dump <what is on your mind>."

        entries = profile["daily_life"]["overthinking_entries"]
        entries.append(
            {
                "at": datetime.now().isoformat(timespec="seconds"),
                "text": clean,
            }
        )
        profile["daily_life"]["overthinking_entries"] = entries[-100:]
        return (
            "Dump saved. Breathe in for 4, out for 6 x5. "
            "When ready, ask: convert last worry to goal."
        )

    def overthinking_status(self, profile: dict) -> str:
        self.ensure_shape(profile)
        entries = profile.get("daily_life", {}).get("overthinking_entries", [])
        if not entries:
            return "Overthinking dump: no entries yet."
        last = entries[-1]
        return f"Overthinking dump: {len(entries)} entries. Last at {last.get('at', '')}."

    def convert_last_worry_to_goal_text(self, profile: dict) -> str:
        self.ensure_shape(profile)
        entries = profile.get("daily_life", {}).get("overthinking_entries", [])
        if not entries:
            return "No worry entry found yet."
        text = str(entries[-1].get("text", "")).strip()
        if not text:
            return "No worry text found in last entry."
        return f"Reduce worry around: {text}"

    @staticmethod
    def nightmare_recovery_message() -> str:
        return (
            "Nightmare recovery: you are safe now. "
            "Step 1: name 3 real objects in the room. "
            "Step 2: inhale 4s, exhale 6s for 5 rounds. "
            "Step 3: sip water and repeat: 'That dream has passed.'"
        )

    @staticmethod
    def mood_bundle(mood_text: str, personality: str) -> dict:
        mood = (mood_text or "").lower().strip()
        persona = (personality or "therapist").lower().strip()

        if mood in ("stressed", "anxious", "overwhelmed", "sad"):
            return {
                "scene": {
                    "animation": "breathing",
                    "color": "cyan",
                    "brightness": 0.25,
                    "key": "mood_calm_reset",
                },
                "spotify_query": "calm ambient focus",
                "local_query": "calm",
                "coaching": "Tone: gentle and grounding. Keep one next step only.",
                "label": "calm reset",
            }

        if mood in ("tired", "sleepy", "low"):
            return {
                "scene": {
                    "animation": "solid",
                    "color": "warmwhite",
                    "brightness": 0.2,
                    "key": "mood_soft_recovery",
                },
                "spotify_query": "soft piano sleep",
                "local_query": "sleep",
                "coaching": "Tone: slow and restorative. Prioritize sleep hygiene.",
                "label": "soft recovery",
            }

        if mood in ("focus", "work", "study"):
            return {
                "scene": {
                    "animation": "pulse",
                    "color": "green" if persona != "coach" else "orange",
                    "brightness": 0.42,
                    "key": "mood_focus_drive",
                },
                "spotify_query": "deep focus beats",
                "local_query": "focus",
                "coaching": "Tone: direct and structured. Set one 25-minute sprint.",
                "label": "focus drive",
            }

        if mood in ("motivated", "energized", "gym"):
            return {
                "scene": {
                    "animation": "wave",
                    "color": "orange",
                    "brightness": 0.5,
                    "key": "mood_momentum",
                },
                "spotify_query": "workout motivation",
                "local_query": "energy",
                "coaching": "Tone: high-energy and accountable.",
                "label": "momentum",
            }

        return {
            "scene": {
                "animation": "solid",
                "color": "white",
                "brightness": 0.35,
                "key": "mood_balanced",
            },
            "spotify_query": "chill mix",
            "local_query": "",
            "coaching": "Tone: balanced and practical.",
            "label": "balanced",
        }

    def set_last_mood_bundle(self, profile: dict, bundle: dict):
        self.ensure_shape(profile)
        daily = profile["daily_life"]
        daily["last_mood_bundle"] = str(bundle.get("label", "")).strip()
        daily["last_coaching_tone"] = str(bundle.get("coaching", "")).strip()
