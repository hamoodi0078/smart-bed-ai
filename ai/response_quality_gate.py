from __future__ import annotations

import re


DEFAULT_SAFE_FALLBACK_RESPONSE = (
    "I am here to help in a calm and safe way. Please try again with a simple request."
)

_UNSAFE_PATTERNS = [
    re.compile(r"\bkill yourself\b", re.IGNORECASE),
    re.compile(r"\bgo die\b", re.IGNORECASE),
    re.compile(r"\bhurt yourself\b", re.IGNORECASE),
    re.compile(r"\bself[- ]harm\b", re.IGNORECASE),
    re.compile(r"\bhow to (kill|harm|poison)\b", re.IGNORECASE),
    re.compile(r"\b(build|make)\s+(a\s+)?bomb\b", re.IGNORECASE),
]

_NON_CALM_PATTERNS = [
    re.compile(r"\bidiot\b", re.IGNORECASE),
    re.compile(r"\bstupid\b", re.IGNORECASE),
    re.compile(r"\bdumb\b", re.IGNORECASE),
    re.compile(r"\bpathetic\b", re.IGNORECASE),
    re.compile(r"\bshut up\b", re.IGNORECASE),
    re.compile(r"\bhate you\b", re.IGNORECASE),
    re.compile(r"\bwhat is wrong with you\b", re.IGNORECASE),
    re.compile(r"[!?]{4,}", re.IGNORECASE),
]


class ResponseQualityGate:
    def __init__(
        self,
        *,
        max_chars: int = 500,
        safe_fallback: str = DEFAULT_SAFE_FALLBACK_RESPONSE,
    ):
        self.max_chars = max(50, int(max_chars))
        self.safe_fallback = self._normalize_text(safe_fallback)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _trim_to_limit(self, text: str) -> tuple[str, bool]:
        if len(text) <= self.max_chars:
            return text, False

        suffix = "..."
        budget = max(1, self.max_chars - len(suffix))
        clipped = text[:budget]
        split = clipped.rfind(" ")
        if split >= int(budget * 0.6):
            clipped = clipped[:split]
        clipped = clipped.rstrip(" ,;:")
        return f"{clipped}{suffix}", True

    @staticmethod
    def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
        return any(pattern.search(text) for pattern in patterns)

    def apply(self, response_text: str) -> tuple[str, dict]:
        normalized = self._normalize_text(response_text)
        original_len = len(normalized)

        if not normalized:
            fallback = self.safe_fallback
            return fallback, {
                "used_fallback": True,
                "trimmed": False,
                "reason": "empty_response",
                "original_length": 0,
                "final_length": len(fallback),
            }

        if self._matches_any(normalized, _UNSAFE_PATTERNS):
            fallback = self.safe_fallback
            return fallback, {
                "used_fallback": True,
                "trimmed": False,
                "reason": "unsafe_content",
                "original_length": original_len,
                "final_length": len(fallback),
            }

        if self._matches_any(normalized, _NON_CALM_PATTERNS):
            fallback = self.safe_fallback
            return fallback, {
                "used_fallback": True,
                "trimmed": False,
                "reason": "non_calm_tone",
                "original_length": original_len,
                "final_length": len(fallback),
            }

        final_text, trimmed = self._trim_to_limit(normalized)
        return final_text, {
            "used_fallback": False,
            "trimmed": bool(trimmed),
            "reason": "ok",
            "original_length": original_len,
            "final_length": len(final_text),
        }
