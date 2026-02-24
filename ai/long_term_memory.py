import json
import re
from datetime import datetime
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
                return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"entries": []}

    def _save(self, payload: dict):
        try:
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return

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
