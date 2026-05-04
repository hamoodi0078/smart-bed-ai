"""Shared sentence-transformer embedding service with lazy loading and text-hash cache."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: "SentenceTransformer | None" = None


def _get_model() -> "SentenceTransformer":
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading sentence-transformer model: {}", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Sentence-transformer model loaded.")
    return _model


@lru_cache(maxsize=512)
def _cached_encode(text_hash: str, text: str) -> tuple:
    """Encode text to embedding, cached by content hash. Returns tuple for hashability."""
    vec = _get_model().encode(text, normalize_embeddings=True, show_progress_bar=False)
    return tuple(vec.tolist())


def encode(text: str) -> np.ndarray:
    """Return a unit-norm embedding vector for the given text."""
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return np.array(_cached_encode(key, text), dtype=float)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two unit-norm vectors."""
    return float(np.dot(a, b))


def is_available() -> bool:
    """Return True if sentence-transformers is importable."""
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False