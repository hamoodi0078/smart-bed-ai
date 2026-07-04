"""PostgreSQL + pgvector async memory index.

Same upsert / query / delete / count interface as ChromaMemoryIndex but
stores vectors inside PostgreSQL using the pgvector extension — no extra
process, no extra disk directory, full ACID guarantees.

The table ``user_memory_embeddings`` is created automatically on first use.

Requirements:
  - PostgreSQL with the ``vector`` extension installed  (pgvector >= 0.5)
  - asyncpg  (project dependency)
  - ai.embedding_service / sentence-transformers  (for encoding)

Priority in long_term_memory.py:
  pgvector  >  ChromaDB  >  in-memory sentence-transformer  >  token match
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from database.connection import AsyncDatabaseConnection

_EMBEDDING_DIMS = 384  # all-MiniLM-L6-v2 output dimensionality


class PgVectorMemoryIndex:
    """Async pgvector-backed memory index scoped per user.

    Parameters
    ----------
    db:
        An initialised ``AsyncDatabaseConnection`` instance.  The pool must
        already be open (i.e. ``await db.initialize()`` must have been called).
    """

    TABLE = "user_memory_embeddings"
    DIMS = _EMBEDDING_DIMS

    def __init__(self, db: "AsyncDatabaseConnection") -> None:
        self._db = db
        self._ready = False

    # ------------------------------------------------------------------
    # Setup — runs once on first use
    # ------------------------------------------------------------------

    async def _ensure_ready(self) -> bool:
        if self._ready:
            return True
        try:
            async with self._db.acquire() as conn:
                # Enable the pgvector extension (idempotent)
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE} (
                        id        TEXT PRIMARY KEY,
                        user_id   TEXT NOT NULL,
                        text      TEXT NOT NULL,
                        embedding vector({self.DIMS}),
                        metadata  JSONB NOT NULL DEFAULT '{{}}',
                        ts        TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                """)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_ume_user_ts
                    ON {self.TABLE} (user_id, ts)
                """)
                # IVFFlat approximate-nearest-neighbour index.
                # Silently skipped when the table is still empty — PostgreSQL
                # requires at least one row to choose cluster centres.
                try:
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_ume_embedding
                        ON {self.TABLE}
                        USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = 50)
                    """)
                except Exception:
                    pass

            self._ready = True
            logger.debug("PgVectorMemoryIndex ready (table={})", self.TABLE)
            return True
        except Exception as exc:
            logger.debug("PgVectorMemoryIndex setup failed: {}", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vec_str(vec: list[float]) -> str:
        """Serialise a float list to pgvector literal format: '[x, y, …]'."""
        return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    # ------------------------------------------------------------------
    # Public API  (mirrors ChromaMemoryIndex)
    # ------------------------------------------------------------------

    async def upsert(
        self,
        doc_id: str,
        user_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Encode *text* and insert/update the row. Returns True on success."""
        if not await self._ensure_ready():
            return False
        try:
            from ai.embedding_service import encode

            vec = self._vec_str(encode(text).tolist())
            meta_json = json.dumps(metadata or {})
            async with self._db.acquire() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO {self.TABLE} (id, user_id, text, embedding, metadata)
                    VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                    ON CONFLICT (id) DO UPDATE
                        SET text      = EXCLUDED.text,
                            embedding = EXCLUDED.embedding,
                            metadata  = EXCLUDED.metadata
                    """,
                    doc_id,
                    user_id,
                    text[:2000],
                    vec,
                    meta_json,
                )
            return True
        except Exception as exc:
            logger.debug("PgVectorMemoryIndex.upsert failed doc_id={}: {}", doc_id, exc)
            return False

    async def query(
        self,
        user_id: str,
        text: str,
        n_results: int = 3,
        min_similarity: float = 0.25,
    ) -> list[dict[str, Any]]:
        """Return the *n_results* entries most similar to *text* for *user_id*.

        Result dicts: {id, document, metadata, similarity}.
        """
        if not await self._ensure_ready():
            return []
        try:
            from ai.embedding_service import encode

            vec = self._vec_str(encode(text).tolist())
            async with self._db.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT id,
                           text,
                           metadata,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM   {self.TABLE}
                    WHERE  user_id = $2
                    ORDER  BY embedding <=> $1::vector
                    LIMIT  $3
                    """,
                    vec,
                    user_id,
                    int(n_results),
                )
            hits: list[dict[str, Any]] = []
            for row in rows:
                sim = float(row["similarity"])
                if sim >= min_similarity:
                    hits.append(
                        {
                            "id": row["id"],
                            "document": row["text"],
                            "metadata": dict(row["metadata"] or {}),
                            "similarity": round(sim, 4),
                        }
                    )
            return hits
        except Exception as exc:
            logger.debug("PgVectorMemoryIndex.query failed: {}", exc)
            return []

    async def delete(self, doc_id: str) -> bool:
        """Remove an entry by its primary-key ID."""
        if not await self._ensure_ready():
            return False
        try:
            async with self._db.acquire() as conn:
                await conn.execute(f"DELETE FROM {self.TABLE} WHERE id = $1", doc_id)
            return True
        except Exception as exc:
            logger.debug("PgVectorMemoryIndex.delete failed doc_id={}: {}", doc_id, exc)
            return False

    async def count(self, user_id: str | None = None) -> int:
        """Row count, optionally filtered by *user_id*."""
        if not await self._ensure_ready():
            return 0
        try:
            async with self._db.acquire() as conn:
                if user_id:
                    return int(
                        await conn.fetchval(
                            f"SELECT COUNT(*) FROM {self.TABLE} WHERE user_id = $1",
                            user_id,
                        )
                    )
                return int(await conn.fetchval(f"SELECT COUNT(*) FROM {self.TABLE}"))
        except Exception:
            return 0

    @property
    def available(self) -> bool:
        """True once the table has been created successfully."""
        return self._ready
