import hashlib
import random
import sqlite3
import time
from pathlib import Path
from typing import Optional


DB_PATH = Path("data/cache.db")


class CacheManager:
    def __init__(self, ttl_seconds: int = 86400):
        self.ttl_seconds = ttl_seconds
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS response_cache (
                    id INTEGER PRIMARY KEY,
                    query_hash TEXT UNIQUE NOT NULL,
                    query_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    personality TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    last_accessed INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_response_cache_hash ON response_cache(query_hash)"
            )
            conn.commit()

    @staticmethod
    def _make_hash(query_text: str, personality: str) -> str:
        key = f"{personality.strip().lower()}::{query_text.strip().lower()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def get(self, query_text: str, personality: str) -> Optional[str]:
        query_hash = self._make_hash(query_text, personality)
        now = int(time.time())

        conn = sqlite3.connect(DB_PATH, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, response_text, created_at FROM response_cache WHERE query_hash = ?",
                (query_hash,),
            ).fetchone()

            if not row:
                conn.execute("COMMIT")
                return None

            record_id, response_text, created_at = row
            if now - created_at > self.ttl_seconds:
                conn.execute("DELETE FROM response_cache WHERE id = ?", (record_id,))
                conn.execute("COMMIT")
                return None

            conn.execute(
                "UPDATE response_cache SET hit_count = hit_count + 1, last_accessed = ? WHERE id = ?",
                (now, record_id),
            )
            conn.execute("COMMIT")
            return response_text
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def set(self, query_text: str, response_text: str, personality: str):
        query_hash = self._make_hash(query_text, personality)
        now = int(time.time())

        conn = sqlite3.connect(DB_PATH, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO response_cache (
                    query_hash, query_text, response_text, personality, created_at, last_accessed
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_hash) DO UPDATE SET
                    response_text = excluded.response_text,
                    last_accessed = excluded.last_accessed
                """,
                (query_hash, query_text, response_text, personality, now, now),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        # Probabilistic cleanup of expired entries to prevent unbounded growth.
        if random.random() < 0.01:
            self._cleanup_expired()

    def _cleanup_expired(self):
        cutoff = int(time.time()) - self.ttl_seconds
        conn = sqlite3.connect(DB_PATH, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM response_cache WHERE created_at < ?", (cutoff,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
        finally:
            conn.close()
