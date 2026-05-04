from loguru import logger as _log
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from config import LONG_TERM_MEMORY_PATH
from Storage.io import atomic_write_json, locked_read_json

if TYPE_CHECKING:
    from database.connection import DatabaseConnection


class LongTermMemoryStore:
    """Simple JSON-backed memory for week-over-week conversational continuity."""

    def __init__(self, path: str | Path = LONG_TERM_MEMORY_PATH, max_items: int = 400):
        self.path = Path(path)
        self.max_items = max(50, int(max_items))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from ai.chroma_memory_index import ChromaMemoryIndex
        chroma_dir = self.path.parent / "chroma"
        self._chroma = ChromaMemoryIndex(persist_dir=chroma_dir)

    def _load(self) -> dict:
        try:
            payload = locked_read_json(self.path)
            if isinstance(payload, dict) and payload:
                payload.setdefault("entries", [])
                payload.setdefault("external_daily_events", [])
                return payload
        except Exception as exc:
            bak = self.path.with_suffix(".bak")
            try:
                import shutil
                shutil.copy2(str(self.path), str(bak))
            except Exception:
                pass
            _log.warning("long_term_memory _load failed; backup written to %s error=%s", bak, exc)
        return {"entries": [], "external_daily_events": []}

    def _save(self, payload: dict):
        try:
            atomic_write_json(self.path, payload if isinstance(payload, dict) else {})
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
        # Persist embedding to ChromaDB for semantic retrieval
        ts = entries[-1]["ts"]
        doc_id = f"{ts}-{len(entries)}"
        combined = f"{user} {assistant}"
        self._chroma.upsert(
            doc_id=doc_id,
            text=combined,
            metadata={"emotion": str(emotion_state or "neutral"), "personality": str(personality or "guide"), "ts": ts},
        )

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-zA-Z0-9\u0600-\u06FF']+", str(text or "").lower()) if len(w) >= 3}

    def retrieve_relevant(self, user_text: str, max_items: int = 2) -> list[dict]:
        payload = self._load()
        entries = payload.get("entries", [])
        if not entries:
            return []

        k = max(1, int(max_items))

        # ChromaDB vector search (best: persisted embeddings, sub-ms query)
        try:
            chroma_hits = self._chroma.query(str(user_text or ""), n_results=k)
            if chroma_hits:
                hit_docs = {h["document"][:100] for h in chroma_hits}
                matched = [
                    item for item in entries
                    if f"{item.get('user', '')} {item.get('assistant', '')}"[:100] in hit_docs
                ]
                if matched:
                    return matched[:k]
        except Exception as exc:
            _log.debug("ChromaDB retrieval failed, falling back: {}", exc)

        # In-memory semantic retrieval via sentence-transformers (preferred over token match)
        try:
            from ai.embedding_service import cosine_similarity, encode, is_available
            if is_available():
                query_vec = encode(str(user_text or ""))
                scored = []
                for item in entries:
                    combined = f"{item.get('user', '')} {item.get('assistant', '')}"
                    sim = cosine_similarity(query_vec, encode(combined))
                    scored.append((sim, item))
                scored.sort(key=lambda p: p[0], reverse=True)
                top = [x[1] for x in scored[:k] if x[0] > 0.25]
                if top:
                    return top
        except Exception as exc:
            _log.debug("Semantic retrieval unavailable, falling back to token match: {}", exc)

        # Token-based fallback
        query_tokens = self._tokenize(user_text)
        ranked = []
        for item in entries:
            combined = f"{item.get('user', '')} {item.get('assistant', '')}"
            score = len(query_tokens.intersection(self._tokenize(combined)))
            if score > 0:
                ranked.append((score, item))

        ranked.sort(key=lambda pair: (pair[0], str(pair[1].get("ts", ""))), reverse=True)
        if ranked:
            return [x[1] for x in ranked[:k]]

        # last resort: most recent entries
        return entries[-k:]

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


class DBLongTermMemoryStore:
    """Database-backed long-term memory store (per-user, multi-tenant safe).

    Replaces the per-user JSON file approach used by the web API layer.
    The original ``LongTermMemoryStore`` remains for backwards-compat with
    the voice handler and test suite.
    """

    MAX_ENTRIES = 400
    MAX_DAILY_EVENTS = 120

    def __init__(self, user_id: str, db_connection: "DatabaseConnection"):
        self._user_id = str(user_id or "").strip()
        self._db = db_connection

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def record_turn(self, user_text: str, assistant_text: str, emotion_state: str, personality: str) -> None:
        user = str(user_text or "").strip()
        if not user or not self._user_id:
            return
        from database.models import UserMemoryEntry
        try:
            with self._db.get_session() as session:
                entry = UserMemoryEntry(
                    user_id=self._user_id,
                    ts=self._utcnow(),
                    user_text=user[:2000],
                    assistant_text=str(assistant_text or "").strip()[:2000],
                    emotion=str(emotion_state or "neutral").strip().lower()[:40],
                    personality=str(personality or "guide").strip().lower()[:40],
                )
                session.add(entry)
                # Prune oldest rows beyond MAX_ENTRIES to keep the table lean
                from sqlalchemy import delete, select, func
                count = session.execute(
                    select(func.count()).select_from(UserMemoryEntry).where(
                        UserMemoryEntry.user_id == self._user_id
                    )
                ).scalar_one()
                if count > self.MAX_ENTRIES:
                    excess = count - self.MAX_ENTRIES
                    oldest_ids = session.execute(
                        select(UserMemoryEntry.id)
                        .where(UserMemoryEntry.user_id == self._user_id)
                        .order_by(UserMemoryEntry.ts.asc())
                        .limit(excess)
                    ).scalars().all()
                    if oldest_ids:
                        session.execute(
                            delete(UserMemoryEntry).where(UserMemoryEntry.id.in_(oldest_ids))
                        )
        except Exception:
            _log.exception("DBLongTermMemoryStore.record_turn failed")

    def inject_daily_events(self, events: list, source: str = "manual") -> int:
        if not self._user_id:
            return 0
        from database.models import UserDailyEvent
        count = 0
        try:
            with self._db.get_session() as session:
                for row in (events or []):
                    if isinstance(row, dict):
                        title = str(row.get("title", "") or "").strip()[:120]
                        summary = str(row.get("summary", "") or "").strip()[:220]
                        stress = str(row.get("stress_level", "") or "").strip().lower()
                        src = str(row.get("source", source) or source).strip().lower()
                    else:
                        title = str(row or "").strip()[:120]
                        summary = ""
                        stress = ""
                        src = str(source or "manual").strip().lower()
                    if not title:
                        continue
                    if stress not in {"low", "moderate", "high"}:
                        stress = ""
                    session.add(UserDailyEvent(
                        user_id=self._user_id,
                        ts=self._utcnow(),
                        title=title,
                        summary=summary,
                        stress_level=stress,
                        source=src or "manual",
                    ))
                    count += 1
        except Exception:
            _log.exception("DBLongTermMemoryStore.inject_daily_events failed")
        return count

    # ------------------------------------------------------------------
    # Read operations (mirror the JSON-based API)
    # ------------------------------------------------------------------

    def _recent_entries(self, limit: int = 5):
        from database.models import UserMemoryEntry
        from sqlalchemy import select
        try:
            with self._db.get_session() as session:
                rows = session.execute(
                    select(UserMemoryEntry)
                    .where(UserMemoryEntry.user_id == self._user_id)
                    .order_by(UserMemoryEntry.ts.desc())
                    .limit(limit)
                ).scalars().all()
                return list(reversed(rows))
        except Exception:
            _log.exception("DBLongTermMemoryStore._recent_entries failed")
            return []

    def latest_memory_context(self) -> str:
        entries = self._recent_entries(limit=1)
        if not entries:
            return self.latest_daily_events_summary()
        last = entries[-1]
        memory_line = (
            f"Last memory turn: user='{last.user_text[:120]}' "
            f"emotion={last.emotion} personality={last.personality}."
        )
        events_line = self.latest_daily_events_summary()
        return f"{memory_line} {events_line}".strip()

    def memory_prompt_line(self, user_text: str) -> str:
        from database.models import UserMemoryEntry
        from sqlalchemy import select

        clean_query = str(user_text or "").strip()
        if not clean_query:
            return ""

        try:
            with self._db.get_session() as session:
                rows = session.execute(
                    select(UserMemoryEntry)
                    .where(UserMemoryEntry.user_id == self._user_id)
                    .order_by(UserMemoryEntry.ts.desc())
                    .limit(50)
                ).scalars().all()
        except Exception:
            return ""

        if not rows:
            return ""

        # Semantic scoring (preferred) \u2014 falls back to token-match if unavailable
        try:
            from ai.embedding_service import cosine_similarity, encode, is_available
            if is_available():
                query_vec = encode(clean_query)
                scored = []
                for row in rows:
                    combined = f"{row.user_text} {row.assistant_text}"
                    sim = cosine_similarity(query_vec, encode(combined))
                    scored.append((sim, row))
                scored.sort(key=lambda p: p[0], reverse=True)
                top = [r.user_text[:120] for _, r in scored[:2] if _ > 0.25 and r.user_text.strip()]
                if top:
                    return "Continuity memory: In prior sessions user mentioned -> " + " | ".join(top)
        except Exception as exc:
            _log.debug("Semantic memory_prompt_line unavailable: {}", exc)

        # Token-based fallback
        query_tokens = {
            w for w in re.findall(r"[a-zA-Z0-9\u0600-\u06FF']+", clean_query.lower())
            if len(w) >= 3
        }
        ranked = []
        for row in rows:
            combined = f"{row.user_text} {row.assistant_text}"
            score = len(query_tokens.intersection(
                {w for w in re.findall(r"[a-zA-Z0-9\u0600-\u06FF']+", combined.lower()) if len(w) >= 3}
            ))
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda p: p[0], reverse=True)
        top = [r.user_text[:120] for _, r in ranked[:2] if r.user_text.strip()]
        if not top:
            return ""
        return "Continuity memory: In prior sessions user mentioned -> " + " | ".join(top)

    def latest_daily_events_summary(self, hours: int = 24, max_items: int = 3) -> str:
        from database.models import UserDailyEvent
        from sqlalchemy import select
        cutoff = self._utcnow() - timedelta(hours=max(1, int(hours)))
        try:
            with self._db.get_session() as session:
                rows = session.execute(
                    select(UserDailyEvent)
                    .where(
                        UserDailyEvent.user_id == self._user_id,
                        UserDailyEvent.ts >= cutoff,
                    )
                    .order_by(UserDailyEvent.ts.desc())
                    .limit(max_items)
                ).scalars().all()
        except Exception:
            return ""
        lines = []
        for row in rows:
            if not row.title.strip():
                continue
            hint = []
            if row.stress_level:
                hint.append(f"stress={row.stress_level}")
            if row.source:
                hint.append(f"source={row.source}")
            suffix = f" ({', '.join(hint)})" if hint else ""
            lines.append(f"{row.title}{suffix}")
        if not lines:
            return ""
        return "Daily events context: " + " | ".join(lines)
