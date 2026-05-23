"""Shared text-processing utilities used across the codebase.

Previously duplicated in voice_handler.py, scene_manager.py, and app_entry.py.
"""

from __future__ import annotations

import re


def normalize_for_intent(text: str) -> str:
    """Lower-case, strip non-alphanumeric (preserving Arabic), collapse whitespace."""
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-z0-9#(),\s'\u0600-\u06ff]+", " ", (text or "").lower()),
    ).strip()


def has_any(text: str, words: tuple[str, ...] | list[str]) -> bool:
    """Return True if *text* contains any of the given *words*."""
    return any(w in text for w in words)
