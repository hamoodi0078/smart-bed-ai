"""ChromaDB-backed persistent vector index for long-term memory retrieval.

Provides a thin wrapper around a ChromaDB collection so that
LongTermMemoryStore can persist embeddings between restarts and query them
via cosine similarity without loading all entries into RAM.

Usage:
    index = ChromaMemoryIndex(persist_dir="runtime_data/chroma")
    index.upsert(doc_id="entry-uuid", text="I can't sleep well lately", metadata={...})
    results = index.query("having trouble sleeping", n_results=3)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


class ChromaMemoryIndex:
    """Persistent ChromaDB collection for memory entry embeddings."""

    COLLECTION_NAME = "long_term_memory"

    def __init__(self, persist_dir: str | Path = "runtime_data/chroma") -> None:
        self._persist_dir = str(Path(persist_dir).resolve())
        self._client = None
        self._collection = None

    def _ensure_ready(self) -> bool:
        """Lazily initialise the ChromaDB client + collection."""
        if self._collection is not None:
            return True
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.debug(
                "ChromaDB collection '{}' ready at {}", self.COLLECTION_NAME, self._persist_dir
            )
            return True
        except Exception as exc:
            logger.debug("ChromaDB unavailable: {}", exc)
            return False

    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> bool:
        """Add or update a document by ID. Returns True on success."""
        if not self._ensure_ready():
            return False
        try:
            from ai.embedding_service import encode

            vec = encode(text).tolist()
            self._collection.upsert(
                ids=[doc_id],
                embeddings=[vec],
                documents=[text[:2000]],
                metadatas=[metadata or {}],
            )
            return True
        except Exception as exc:
            logger.debug("ChromaDB upsert failed doc_id={}: {}", doc_id, exc)
            return False

    def query(
        self, text: str, n_results: int = 3, min_similarity: float = 0.25
    ) -> list[dict[str, Any]]:
        """Return up to n_results entries most similar to text.

        Each result dict contains: id, document, metadata, distance, similarity.
        """
        if not self._ensure_ready():
            return []
        try:
            from ai.embedding_service import encode

            vec = encode(text).tolist()
            results = self._collection.query(
                query_embeddings=[vec],
                n_results=min(n_results, max(1, self._collection.count())),
                include=["documents", "metadatas", "distances"],
            )
            hits = []
            ids = (results.get("ids") or [[]])[0]
            docs = (results.get("documents") or [[]])[0]
            metas = (results.get("metadatas") or [[]])[0]
            dists = (results.get("distances") or [[]])[0]
            for doc_id, doc, meta, dist in zip(ids, docs, metas, dists):
                sim = 1.0 - float(dist)  # cosine distance → similarity
                if sim >= min_similarity:
                    hits.append(
                        {
                            "id": doc_id,
                            "document": doc,
                            "metadata": meta,
                            "similarity": round(sim, 4),
                        }
                    )
            hits.sort(key=lambda h: h["similarity"], reverse=True)
            return hits
        except Exception as exc:
            logger.debug("ChromaDB query failed: {}", exc)
            return []

    def delete(self, doc_id: str) -> bool:
        """Remove a document by ID."""
        if not self._ensure_ready():
            return False
        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception as exc:
            logger.debug("ChromaDB delete failed doc_id={}: {}", doc_id, exc)
            return False

    def count(self) -> int:
        if not self._ensure_ready():
            return 0
        try:
            return int(self._collection.count())
        except Exception:
            return 0
