from datetime import datetime, timedelta
from typing import Dict, List, Tuple


class PersonalityRuntimeOrchestrator:
    def ensure_shape(self, profile: dict):
        profile.setdefault("personality_runtime", {})
        pr = profile["personality_runtime"]
        pr.setdefault("emotion_history", [])
        pr.setdefault("priority_reminder_last_date", "")
        pr.setdefault("wake_phrases", [])
        pr.setdefault("interrupt_count_today", 0)
        pr.setdefault("interrupt_count_date", "")
        pr.setdefault("quality_samples", 0)
        pr.setdefault("quality_running_avg", 0.0)
        pr.setdefault("continuity_by_personality", {})
        pr.setdefault("last_voice_pacing", "balanced")
        pr.setdefault("cognitive_load_samples", [])
        pr.setdefault("brevity_mode", "normal")
        pr.setdefault("phrase_history", [])

    @staticmethod
    def _normalize_phrase(text: str) -> str:
        return " ".join(str(text or "").strip().lower().split())

    @staticmethod
    def _safe_parse_ts(value: str) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None

    def choose_unique_phrase(
        self,
        profile: dict,
        candidates: List[str],
        phrase_kind: str,
        within_hours: int = 48,
        now: datetime | None = None,
    ) -> str:
        self.ensure_shape(profile)
        now = now or datetime.now()
        cutoff = now - timedelta(hours=max(1, int(within_hours)))

        history = profile["personality_runtime"].get("phrase_history", [])
        recent_keys: set[str] = set()
        for item in history:
            if str(item.get("kind", "")).strip().lower() != str(phrase_kind or "").strip().lower():
                continue
            ts = self._safe_parse_ts(item.get("ts", ""))
            if not ts or ts < cutoff:
                continue
            normalized = self._normalize_phrase(item.get("text", ""))
            if normalized:
                recent_keys.add(normalized)

        clean_candidates = [str(x or "").strip() for x in candidates if str(x or "").strip()]
        for phrase in clean_candidates:
            if self._normalize_phrase(phrase) not in recent_keys:
                self.record_phrase_usage(profile, phrase, phrase_kind=phrase_kind, now=now)
                return phrase

        # All candidates were used recently; pick the first to keep output deterministic.
        if not clean_candidates:
            return "I'm here whenever you need me."
        fallback = clean_candidates[0]
        self.record_phrase_usage(profile, fallback, phrase_kind=phrase_kind, now=now)
        return fallback

    def record_phrase_usage(
        self,
        profile: dict,
        phrase: str,
        phrase_kind: str = "generic",
        now: datetime | None = None,
    ):
        self.ensure_shape(profile)
        text = str(phrase or "").strip()
        if not text:
            return
        now = now or datetime.now()
        items = profile["personality_runtime"].get("phrase_history", [])
        items.append(
            {
                "ts": now.isoformat(timespec="seconds"),
                "kind": str(phrase_kind or "generic").strip().lower(),
                "text": text[:180],
            }
        )
        profile["personality_runtime"]["phrase_history"] = items[-220:]

    def record_cognitive_load_signal(
        self, profile: dict, user_text: str, speech_seconds: float | None = None
    ):
        self.ensure_shape(profile)
        text = str(user_text or "").strip()
        if not text:
            return
        words = [w for w in text.split() if w]
        word_count = len(words)
        avg_word_len = (sum(len(w) for w in words) / word_count) if word_count else 0.0

        speech_duration = float(speech_seconds or 0.0)
        words_per_second = (word_count / speech_duration) if speech_duration > 0.2 else 0.0
        terse_phrase = word_count <= 4
        slow_delivery = speech_duration > 0 and words_per_second < 1.45
        fatigue_signal = terse_phrase or slow_delivery or (avg_word_len <= 3.6 and word_count <= 6)

        sample = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "word_count": word_count,
            "speech_seconds": round(speech_duration, 2),
            "wps": round(words_per_second, 2),
            "fatigue_signal": bool(fatigue_signal),
        }
        samples = profile["personality_runtime"].get("cognitive_load_samples", [])
        samples.append(sample)
        profile["personality_runtime"]["cognitive_load_samples"] = samples[-40:]

    def cognitive_load_mode(self, profile: dict, lookback: int = 6) -> str:
        self.ensure_shape(profile)
        samples = profile["personality_runtime"].get("cognitive_load_samples", [])[
            -max(2, int(lookback)) :
        ]
        if not samples:
            return "normal"
        fatigue_hits = sum(1 for x in samples if bool(x.get("fatigue_signal", False)))
        if fatigue_hits >= max(2, int(len(samples) * 0.6)):
            return "exhausted"
        if fatigue_hits >= 1:
            return "reduced"
        return "normal"

    def apply_cognitive_brevity(
        self, profile: dict, response_text: str, emotion_state: str
    ) -> tuple[str, str]:
        self.ensure_shape(profile)
        text = str(response_text or "").strip()
        if not text:
            return "", ""

        mode = self.cognitive_load_mode(profile)
        emotion = str(emotion_state or "neutral").strip().lower()
        if mode == "normal" and emotion not in ("low_energy", "distressed", "dream_negative"):
            profile["personality_runtime"]["brevity_mode"] = "normal"
            return text, ""

        reduction_ratio = 0.66 if mode == "exhausted" else 0.6
        hard_limit = 160 if mode == "exhausted" else 190
        target_len = max(70, int(len(text) * (1.0 - reduction_ratio)))
        target_len = min(target_len, hard_limit)

        clipped = text[:target_len].strip()
        split_idx = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
        if split_idx >= 40:
            clipped = clipped[: split_idx + 1].strip()
        elif len(text) > target_len:
            clipped = clipped.rstrip(" ,;:") + "..."

        profile["personality_runtime"]["brevity_mode"] = "cognitive_load"
        return clipped, "brevity_cognitive_load"

    def record_emotion_state(self, profile: dict, state: str):
        self.ensure_shape(profile)
        now = datetime.now().isoformat(timespec="seconds")
        items = profile["personality_runtime"]["emotion_history"]
        items.append({"ts": now, "state": state})
        profile["personality_runtime"]["emotion_history"] = items[-120:]

    def latest_emotion_state(self, profile: dict) -> str:
        self.ensure_shape(profile)
        items = profile["personality_runtime"].get("emotion_history", [])
        if not items:
            return "neutral"
        return str(items[-1].get("state", "neutral"))

    def emotion_trend_summary(self, profile: dict, last_n: int = 12) -> str:
        self.ensure_shape(profile)
        items = profile["personality_runtime"].get("emotion_history", [])[-last_n:]
        if not items:
            return "Emotion trend: neutral baseline."

        counts: Dict[str, int] = {}
        for item in items:
            state = str(item.get("state", "neutral"))
            counts[state] = counts.get(state, 0) + 1

        dominant = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[0][0]
        return f"Emotion trend: dominant={dominant}, samples={len(items)}."

    def choose_dynamic_intervention(
        self, personality: str, emotion_state: str, level: str = "beginner"
    ) -> str:
        personality = (personality or "therapist").lower().strip()
        level = (level or "beginner").lower().strip()

        if personality == "therapist":
            if emotion_state == "distressed":
                return (
                    "Therapist intervention: 60-second grounding. Name 5 things you see, 4 you feel, 3 you hear, "
                    "2 you smell, 1 you taste. Then exhale slowly for 6 seconds."
                )
            if emotion_state == "low_energy":
                return "Therapist intervention: sleep-anxiety offload. Write 3 worries and one controllable action for tomorrow."
            return "Therapist intervention: cognitive reframing. Replace one harsh thought with a balanced evidence-based version."

        if personality == "coach":
            if emotion_state == "low_energy":
                return "Coach intervention: 10-minute micro-sprint. Start one tiny task now, then stop and review progress."
            return "Coach intervention: accountability. Define one measurable target for today and commit to a check-in time."

        # guide
        if level == "advanced":
            return "Guide intervention (advanced): compare two strategies, list trade-offs, then choose one by clear criteria."
        if level == "intermediate":
            return "Guide intervention (intermediate): quick explanation + practical example + one self-check question."
        return "Guide intervention (beginner): simple explanation in one step, then do one easy practice action now."

    def record_continuity_hint(self, profile: dict, personality: str, user_text: str):
        self.ensure_shape(profile)
        text = (user_text or "").strip()
        if not text:
            return
        lowered = text.lower()
        signal_words = (
            "problem",
            "issue",
            "stuck",
            "struggling",
            "anxious",
            "overwhelmed",
            "cannot",
            "can't",
            "need help",
        )
        if not any(w in lowered for w in signal_words):
            return

        summary = text[:140]
        key = (personality or "therapist").lower().strip() or "therapist"
        profile["personality_runtime"].setdefault("continuity_by_personality", {})
        profile["personality_runtime"]["continuity_by_personality"][key] = {
            "summary": summary,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def continuity_line(self, profile: dict, personality: str) -> str:
        self.ensure_shape(profile)
        key = (personality or "therapist").lower().strip() or "therapist"
        item = profile["personality_runtime"].get("continuity_by_personality", {}).get(key, {})
        summary = str(item.get("summary", "")).strip()
        if not summary:
            return "Session continuity: no unresolved issue stored yet."
        return f"Session continuity for {key}: last unresolved issue -> {summary}"

    def continuity_callback_line(self, profile: dict, personality: str) -> str:
        self.ensure_shape(profile)
        key = (personality or "therapist").lower().strip() or "therapist"
        item = profile["personality_runtime"].get("continuity_by_personality", {}).get(key, {})
        summary = str(item.get("summary", "")).strip()
        if not summary:
            return ""
        return f"Quick callback from last session: you mentioned '{summary}'."

    def _is_in_quiet_window(self, quiet_window: str, now: datetime) -> bool:
        text = (quiet_window or "").strip()
        if not text or "-" not in text:
            return False
        try:
            left, right = [p.strip() for p in text.split("-", 1)]
            sh, sm = [int(x) for x in left.split(":", 1)]
            eh, em = [int(x) for x in right.split(":", 1)]
            start_m = sh * 60 + sm
            end_m = eh * 60 + em
            now_m = now.hour * 60 + now.minute
            if start_m == end_m:
                return False
            if start_m < end_m:
                return start_m <= now_m < end_m
            return now_m >= start_m or now_m < end_m
        except Exception:
            return False

    def should_send_priority_reminder(
        self, profile: dict, active_goals: List[dict], emotion_state: str
    ) -> bool:
        self.ensure_shape(profile)
        if not active_goals:
            return False

        now = datetime.now()
        if now.hour < 9 or now.hour > 22:
            return False

        quiet_window = profile.get("preferences", {}).get("quiet_window", "")
        if self._is_in_quiet_window(quiet_window, now):
            return False

        if emotion_state == "low_energy":
            return False

        today = now.date().isoformat()
        last = profile["personality_runtime"].get("priority_reminder_last_date", "")
        if last == today:
            return False

        has_tonight = any(
            (g.get("scope", "") == "tonight" and g.get("status") == "active") for g in active_goals
        )
        return has_tonight or len(active_goals) >= 2

    def build_priority_reminder(self, active_goals: List[dict]) -> str:
        critical = [
            g for g in active_goals if g.get("scope") == "tonight" and g.get("status") == "active"
        ]
        pick = critical[0] if critical else (active_goals[0] if active_goals else None)
        if not pick:
            return ""
        return f"Priority reminder: focus now on '{pick.get('title', 'your top goal')}'. One small step is enough."

    def mark_priority_reminder_sent(self, profile: dict):
        self.ensure_shape(profile)
        profile["personality_runtime"]["priority_reminder_last_date"] = (
            datetime.now().date().isoformat()
        )

    def record_wake_phrase(self, profile: dict, wake_text: str):
        self.ensure_shape(profile)
        items = profile["personality_runtime"].get("wake_phrases", [])
        items.append(
            {"ts": datetime.now().isoformat(timespec="seconds"), "text": (wake_text or "")[:80]}
        )
        profile["personality_runtime"]["wake_phrases"] = items[-40:]

    def record_interrupt(self, profile: dict):
        self.ensure_shape(profile)
        pr = profile["personality_runtime"]
        today = datetime.now().date().isoformat()
        if pr.get("interrupt_count_date") != today:
            pr["interrupt_count_date"] = today
            pr["interrupt_count_today"] = 0
        pr["interrupt_count_today"] = int(pr.get("interrupt_count_today", 0)) + 1

    def current_interrupt_count(self, profile: dict, now: datetime | None = None) -> int:
        self.ensure_shape(profile)
        now = now or datetime.now()
        pr = profile["personality_runtime"]
        today = now.date().isoformat()
        if pr.get("interrupt_count_date") != today:
            return 0
        return int(pr.get("interrupt_count_today", 0) or 0)

    def proactive_prompt_level(self, profile: dict, now: datetime | None = None) -> str:
        interrupts = self.current_interrupt_count(profile, now=now)
        if interrupts >= 4:
            return "minimal"
        if interrupts >= 2:
            return "reduced"
        return "normal"

    def wake_quality_state(self, profile: dict) -> str:
        self.ensure_shape(profile)
        pr = profile["personality_runtime"]
        interrupts = int(pr.get("interrupt_count_today", 0))
        recent_phrases = [str(x.get("text", "")).lower() for x in pr.get("wake_phrases", [])[-5:]]
        stressed_phrase = any(
            ("still awake" in t or "tired" in t or "again" in t) for t in recent_phrases
        )
        if interrupts >= 3 or stressed_phrase:
            return "fragile"
        return "stable"

    def determine_voice_pacing(
        self, emotion_state: str, wake_quality: str
    ) -> Tuple[str, float, str]:
        emotion = (emotion_state or "neutral").lower().strip()
        quality = (wake_quality or "stable").lower().strip()
        if quality == "fragile" or emotion in ("distressed", "low_energy"):
            return "slow_calm", 0.92, "Voice pacing: slow and calm for emotional safety."
        if emotion == "motivated":
            return "energetic", 1.08, "Voice pacing: concise and energetic to keep momentum."
        return "balanced", 1.0, "Voice pacing: balanced."

    def set_last_voice_pacing(self, profile: dict, pacing: str):
        self.ensure_shape(profile)
        profile["personality_runtime"]["last_voice_pacing"] = (
            pacing or "balanced"
        ).strip() or "balanced"

    def voice_pacing_status(self, profile: dict) -> str:
        self.ensure_shape(profile)
        pacing = profile["personality_runtime"].get("last_voice_pacing", "balanced")
        return f"Voice pacing status: {pacing}."

    def enforce_conversation_quality(
        self,
        profile: dict,
        response_text: str,
        personality: str,
        emotion_state: str,
    ) -> Tuple[str, str]:
        self.ensure_shape(profile)
        text = (response_text or "").strip()
        if not text:
            return text, ""

        empathy = (
            1.0
            if any(x in text.lower() for x in ("i hear", "that sounds", "understand", "you can"))
            else 0.4
        )
        clarity = 1.0 if len(text) <= 360 else 0.6
        actionability = (
            1.0 if any(x in text.lower() for x in ("try", "next", "step", "do", "plan")) else 0.5
        )
        score = (empathy + clarity + actionability) / 3.0

        pr = profile["personality_runtime"]
        samples = int(pr.get("quality_samples", 0)) + 1
        avg = float(pr.get("quality_running_avg", 0.0))
        pr["quality_running_avg"] = ((avg * (samples - 1)) + score) / samples
        pr["quality_samples"] = samples

        if score >= 0.62:
            return text, ""

        tuned = text
        if not any(x in tuned.lower() for x in ("next step", "try", "do this")):
            tuned += " Next step: choose one small action you can do in 10 minutes."
        if emotion_state == "distressed" and "breathe" not in tuned.lower():
            tuned += " Take one slow breath in for 4 and out for 6."
        if "?" not in tuned:
            tuned += " What feels most doable right now?"
        return tuned, "quality_tuned"

    def build_weekly_adaptive_plan(self, profile: dict, active_goals: List[dict]) -> str:
        self.ensure_shape(profile)
        progress = profile.get("progress", {})
        created = max(1, int(progress.get("goals_created", 0)))
        completed = max(0, int(progress.get("goals_completed", 0)))
        rate = completed / created * 100.0
        emotion = self.latest_emotion_state(profile)

        if rate < 40:
            intensity = "light"
        elif rate < 70:
            intensity = "medium"
        else:
            intensity = "high"

        top = ", ".join(g.get("title", "") for g in active_goals[:2]) or "sleep consistency"
        return (
            f"Adaptive weekly plan ({intensity}): keep focus on {top}. "
            f"Set 1 must-do nightly action, 1 weekly milestone, and 1 recovery block. "
            f"Current emotional baseline looks {emotion}."
        )
