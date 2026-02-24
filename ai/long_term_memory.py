import json
import re
from datetime import datetime, timedelta
from pathlib import Path


class LongTermMemoryStore:
    """Simple JSON-backed memory for week-over-week conversational continuity."""

    def __init__(self, path: str = "data/long_term_memory.json", max_items: int = 400):
        self.path = Path(path)
        self.max_items = max(50, int(max_items))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    payload.setdefault("entries", [])
                    payload.setdefault("external_daily_events", [])
                    return payload
        except Exception:
            pass
        return {"entries": [], "external_daily_events": []}

    def _save(self, payload: dict):
        try:
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return

    @staticmethod
    def _normalize_daily_event(entry: dict | str, source: str = "manual") -> dict:
        if isinstance(entry, dict):
            title = str(entry.get("title", "") or "").strip()
            summary = str(entry.get("summary", "") or "").strip()
            stress_level = str(entry.get("stress_level", "") or "").strip().lower()
            event_source = str(entry.get("source", source) or source).strip().lower() or "manual"
        else:
            title = str(entry or "").strip()
            summary = ""
            stress_level = ""
            event_source = str(source or "manual").strip().lower() or "manual"

        if stress_level not in {"low", "moderate", "high"}:
            stress_level = ""

        return {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "title": title[:120],
            "summary": summary[:220],
            "stress_level": stress_level,
            "source": event_source,
        }

    def inject_daily_events(self, events: list[dict | str], source: str = "manual") -> int:
        clean_items = []
        for row in (events or []):
            item = self._normalize_daily_event(row, source=source)
            if item.get("title"):
                clean_items.append(item)
        if not clean_items:
            return 0

        payload = self._load()
        history = payload.get("external_daily_events", [])
        history.extend(clean_items)
        payload["external_daily_events"] = history[-120:]
        self._save(payload)
        return len(clean_items)

    def latest_daily_events_summary(self, hours: int = 24, max_items: int = 3) -> str:
        payload = self._load()
        events = payload.get("external_daily_events", [])
        if not events:
            return ""

        now = datetime.now()
        cutoff = now - timedelta(hours=max(1, int(hours)))
        lines = []
        for item in reversed(events):
            ts = self._parse_ts(item.get("ts", ""))
            if ts and ts < cutoff:
                continue
            title = str(item.get("title", "") or "").strip()
            if not title:
                continue
            stress = str(item.get("stress_level", "") or "").strip().lower()
            source = str(item.get("source", "") or "").strip().lower()
            hint = []
            if stress:
                hint.append(f"stress={stress}")
            if source:
                hint.append(f"source={source}")
            suffix = f" ({', '.join(hint)})" if hint else ""
            lines.append(f"{title}{suffix}")
            if len(lines) >= max(1, int(max_items)):
                break

        if not lines:
            return ""
        return "Daily events context: " + " | ".join(lines)

    def latest_memory_context(self) -> str:
        payload = self._load()
        entries = payload.get("entries", [])
        if not entries:
            return self.latest_daily_events_summary()

        last = entries[-1]
        user_line = str(last.get("user", "") or "").strip()
        emotion = str(last.get("emotion", "neutral") or "neutral").strip().lower()
        personality = str(last.get("personality", "guide") or "guide").strip().lower()
        memory_line = f"Last memory turn: user='{user_line[:120]}' emotion={emotion} personality={personality}."
        events_line = self.latest_daily_events_summary()
        return f"{memory_line} {events_line}".strip()

    def record_turn(self, user_text: str, assistant_text: str, emotion_state: str, personality: str):
        user = str(user_text or "").strip()
        assistant = str(assistant_text or "").strip()
        if not user:
            return

        payload = self._load()
        entries = payload.get("entries", [])
        entries.append(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "user": user,
                "assistant": assistant,
                "emotion": str(emotion_state or "neutral").strip().lower(),
                "personality": str(personality or "guide").strip().lower(),
            }
        )
        payload["entries"] = entries[-self.max_items :]
        self._save(payload)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-zA-Z0-9\u0600-\u06FF']+", str(text or "").lower()) if len(w) >= 3}

    def retrieve_relevant(self, user_text: str, max_items: int = 2) -> list[dict]:
        payload = self._load()
        entries = payload.get("entries", [])
        if not entries:
            return []

        query_tokens = self._tokenize(user_text)
        ranked = []
        for item in entries:
            combined = f"{item.get('user', '')} {item.get('assistant', '')}"
            score = len(query_tokens.intersection(self._tokenize(combined)))
            if score > 0:
                ranked.append((score, item))

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        if ranked:
            return [x[1] for x in ranked[: max(1, int(max_items))]]

        # fallback: latest relevant emotional note
        return entries[-max(1, int(max_items)) :]

    def memory_prompt_line(self, user_text: str) -> str:
        items = self.retrieve_relevant(user_text=user_text, max_items=2)
        if not items:
            return ""
        snippets = []
        for item in items:
            previous = str(item.get("user", "")).strip()
            if previous:
                snippets.append(previous[:120])
        if not snippets:
            return ""
        return "Continuity memory: In prior sessions user mentioned -> " + " | ".join(snippets)

    @staticmethod
    def _parse_ts(value: str) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None

    @staticmethod
    def _is_guide_start_phrase(text: str) -> bool:
        lowered = str(text or "").lower()
        if not lowered:
            return False
        guide_tokens = (
            "guide",
            "start guide",
            "guide session",
            "start session",
            "breathing guide",
        )
        return any(token in lowered for token in guide_tokens)

    def _entries_for_days(self, days: int = 7, now: datetime | None = None) -> list[dict]:
        payload = self._load()
        entries = payload.get("entries", [])
        if not entries:
            return []
        now = now or datetime.now()
        cutoff = now - timedelta(days=max(1, int(days)))
        recent = []
        for item in entries:
            ts = self._parse_ts(item.get("ts", ""))
            if ts and ts >= cutoff:
                recent.append(item)
        return recent

    def infer_invisible_routine(self, now: datetime | None = None, days: int = 7) -> dict:
        now = now or datetime.now()
        recent_entries = self._entries_for_days(days=days, now=now)
        if not recent_entries:
            return {}

        guide_hits: list[datetime] = []
        for item in recent_entries:
            if not self._is_guide_start_phrase(item.get("user", "")):
                continue
            ts = self._parse_ts(item.get("ts", ""))
            if ts:
                guide_hits.append(ts)

        if len(guide_hits) < 3:
            return {}

        buckets: dict[int, list[datetime]] = {}
        for ts in guide_hits:
            buckets.setdefault(ts.hour, []).append(ts)
        dominant_hour, dominant_items = sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)[0]
        if len(dominant_items) < 3:
            return {}

        minute_values = sorted([x.minute for x in dominant_items])
        median_minute = minute_values[len(minute_values) // 2]
        prep_minute_total = dominant_hour * 60 + median_minute - 5
        prep_hour = (prep_minute_total // 60) % 24
        prep_minute = prep_minute_total % 60
        target_minute_total = dominant_hour * 60 + median_minute

        now_total = now.hour * 60 + now.minute
        minutes_until_target = target_minute_total - now_total
        if minutes_until_target < -5:
            minutes_until_target += 24 * 60

        return {
            "pattern": "guide_session",
            "sample_count": len(guide_hits),
            "dominant_sample_count": len(dominant_items),
            "target_time": f"{dominant_hour:02d}:{median_minute:02d}",
            "prep_time": f"{prep_hour:02d}:{prep_minute:02d}",
            "minutes_until_target": int(minutes_until_target),
            "prep_window_active": -2 <= minutes_until_target <= 6,
            "offer_line": "I prepared your guide setup quietly. Would you like to begin your Guide session now?",
        }
