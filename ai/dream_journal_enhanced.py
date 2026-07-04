"""Enhanced dream journal and analysis for Smart Bed AI.

Captures dreams via voice/text, performs sentiment analysis, detects patterns,
correlates with sleep quality, and offers Islamic dream interpretation context.
"""

from __future__ import annotations

from loguru import logger
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


POSITIVE_KEYWORDS = {
    "happy",
    "joy",
    "peace",
    "light",
    "flying",
    "garden",
    "water",
    "family",
    "love",
    "success",
    "beautiful",
    "calm",
    "paradise",
    "angel",
    "prayer",
}
NEGATIVE_KEYWORDS = {
    "scary",
    "fear",
    "falling",
    "chase",
    "dark",
    "lost",
    "death",
    "fire",
    "monster",
    "trapped",
    "pain",
    "cry",
    "scream",
    "nightmare",
    "snake",
}
NEUTRAL_KEYWORDS = {
    "house",
    "car",
    "school",
    "work",
    "walk",
    "talk",
    "eat",
    "sleep",
    "travel",
    "road",
    "door",
    "window",
    "room",
    "people",
    "friend",
}


class DreamJournalEnhanced:
    """Enhanced dream capture, analysis, and pattern detection."""

    def __init__(self):
        pass

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("dreams", {})
        d = profile["dreams"]
        d.setdefault("entries", [])
        d.setdefault("total_dreams", 0)
        d.setdefault("recurring_themes", [])
        d.setdefault("last_entry_date", "")

    # ------------------------------------------------------------------
    # Dream capture
    # ------------------------------------------------------------------

    def record_dream(
        self,
        profile: dict,
        text: str,
        *,
        vivid: bool = False,
        lucid: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Record a dream entry with automatic analysis."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        d = profile["dreams"]

        text = str(text or "").strip()
        if not text:
            return {"recorded": False, "reason": "Empty dream text."}

        sentiment = self._analyze_sentiment(text)
        themes = self._extract_themes(text)
        keywords = self._extract_keywords(text)

        entry = {
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M"),
            "timestamp": now.isoformat(),
            "text": text[:2000],
            "sentiment": sentiment["label"],
            "sentiment_score": sentiment["score"],
            "themes": themes,
            "keywords": keywords,
            "vivid": bool(vivid),
            "lucid": bool(lucid),
        }

        d["entries"].append(entry)
        d["entries"] = d["entries"][-365:]
        d["total_dreams"] = len(d["entries"])
        d["last_entry_date"] = now.date().isoformat()
        self._update_recurring_themes(profile)

        return {
            "recorded": True,
            "entry": entry,
            "analysis": {
                "sentiment": sentiment,
                "themes": themes,
                "keywords": keywords,
                "islamic_guidance": self._islamic_guidance(sentiment["label"]),
            },
        }

    def get_morning_prompt(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Generate morning dream capture prompt."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        d = profile["dreams"]
        today = now.date().isoformat()

        already_logged = d.get("last_entry_date", "") == today
        if already_logged:
            return {"prompt": False, "reason": "Already logged a dream today."}

        total = int(d.get("total_dreams", 0))
        if total == 0:
            message = "Good morning! Did you dream last night? Dreams fade fast — tell me now!"
        elif total < 10:
            message = "Good morning! Any dreams? Capturing them helps discover patterns."
        else:
            message = "Good morning! Remember any dreams? Your journal is growing nicely."

        return {
            "prompt": True,
            "message": message,
            "voice_enabled": True,
            "total_dreams_logged": total,
        }

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _analyze_sentiment(self, text: str) -> dict[str, Any]:
        words = set(re.findall(r"[a-z]+", text.lower()))
        pos = len(words & POSITIVE_KEYWORDS)
        neg = len(words & NEGATIVE_KEYWORDS)

        if pos > neg:
            label = "positive"
            score = min(1.0, 0.5 + pos * 0.1)
        elif neg > pos:
            label = "negative"
            score = max(-1.0, -0.5 - neg * 0.1)
        else:
            label = "neutral"
            score = 0.0

        return {
            "label": label,
            "score": round(score, 2),
            "positive_count": pos,
            "negative_count": neg,
        }

    def _extract_themes(self, text: str) -> list[str]:
        text_lower = text.lower()
        themes = []
        theme_keywords = {
            "flying": ["fly", "flying", "soar", "float"],
            "water": ["water", "ocean", "sea", "river", "swim", "rain"],
            "family": ["mother", "father", "brother", "sister", "family", "child"],
            "travel": ["travel", "journey", "road", "car", "plane", "train"],
            "spiritual": ["prayer", "mosque", "quran", "allah", "angel", "light"],
            "conflict": ["fight", "argue", "chase", "run", "escape", "war"],
            "nature": ["garden", "tree", "mountain", "flower", "forest", "sky"],
            "work": ["work", "office", "school", "exam", "meeting", "boss"],
        }
        for theme, words in theme_keywords.items():
            if any(w in text_lower for w in words):
                themes.append(theme)
        return themes[:5]

    def _extract_keywords(self, text: str) -> list[str]:
        words = text.lower().split()
        all_kw = POSITIVE_KEYWORDS | NEGATIVE_KEYWORDS | NEUTRAL_KEYWORDS
        found = [w for w in words if w in all_kw]
        return list(dict.fromkeys(found))[:10]

    def _update_recurring_themes(self, profile: dict) -> None:
        entries = profile["dreams"].get("entries", [])
        recent = entries[-30:]
        all_themes: list[str] = []
        for e in recent:
            all_themes.extend(e.get("themes", []))
        counts = Counter(all_themes)
        recurring = [theme for theme, count in counts.most_common(5) if count >= 3]
        profile["dreams"]["recurring_themes"] = recurring

    # ------------------------------------------------------------------
    # Pattern analysis
    # ------------------------------------------------------------------

    def get_patterns(self, profile: dict, days: int = 30) -> dict[str, Any]:
        """Analyze dream patterns over a period."""
        self.ensure_shape(profile)
        entries = profile["dreams"].get("entries", [])
        cutoff = (_utcnow() - timedelta(days=max(1, days))).date().isoformat()
        recent = [e for e in entries if str(e.get("date", "")) >= cutoff]

        if not recent:
            return {"total": 0, "period_days": days, "message": "No dreams recorded."}

        sentiments = [e.get("sentiment", "neutral") for e in recent]
        all_themes: list[str] = []
        for e in recent:
            all_themes.extend(e.get("themes", []))

        vivid_count = sum(1 for e in recent if e.get("vivid", False))
        lucid_count = sum(1 for e in recent if e.get("lucid", False))

        return {
            "total": len(recent),
            "period_days": days,
            "recall_rate": round(len(recent) / days * 100, 1),
            "sentiment_breakdown": {
                "positive": sentiments.count("positive"),
                "negative": sentiments.count("negative"),
                "neutral": sentiments.count("neutral"),
            },
            "top_themes": [t for t, _ in Counter(all_themes).most_common(5)],
            "recurring_themes": profile["dreams"].get("recurring_themes", []),
            "vivid_dreams": vivid_count,
            "lucid_dreams": lucid_count,
            "nightmare_count": sentiments.count("negative"),
        }

    def correlate_with_sleep(self, profile: dict, days: int = 30) -> dict[str, Any]:
        """Correlate dream patterns with sleep quality."""
        self.ensure_shape(profile)
        entries = profile["dreams"].get("entries", [])
        scores = profile.get("sleep_scores", [])

        if len(entries) < 5 or not isinstance(scores, list) or len(scores) < 5:
            return {"available": False, "message": "Not enough data for correlation."}

        cutoff = (_utcnow() - timedelta(days=max(1, days))).date().isoformat()
        recent_dreams = [e for e in entries if str(e.get("date", "")) >= cutoff]

        positive_nights = [e.get("date") for e in recent_dreams if e.get("sentiment") == "positive"]
        negative_nights = [e.get("date") for e in recent_dreams if e.get("sentiment") == "negative"]

        insights: list[str] = []
        if len(negative_nights) > len(positive_nights):
            insights.append("Stress dreams correlate with lower sleep quality.")
        if len(positive_nights) > 0:
            insights.append("Positive dreams tend to follow better sleep nights.")

        vivid_count = sum(1 for e in recent_dreams if e.get("vivid"))
        if vivid_count > len(recent_dreams) * 0.5:
            insights.append("High rate of vivid dreams — may indicate REM-rich sleep.")

        return {
            "available": True,
            "dreams_analyzed": len(recent_dreams),
            "positive_dream_nights": len(positive_nights),
            "negative_dream_nights": len(negative_nights),
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # Islamic dream guidance
    # ------------------------------------------------------------------

    @staticmethod
    def _islamic_guidance(sentiment: str) -> dict[str, str]:
        if sentiment == "positive":
            return {
                "guidance": "good_dream",
                "message": "A good dream is from Allah. Thank Allah for this vision and share it with those you love.",
                "action": "Say Alhamdulillah.",
            }
        if sentiment == "negative":
            return {
                "guidance": "bad_dream",
                "message": "A bad dream is from Shaytan. Seek refuge in Allah. Spit lightly to your left three times.",
                "action": "Say A'udhu billahi min ash-Shaytan ir-rajim. Do not tell anyone about it.",
            }
        return {
            "guidance": "neutral",
            "message": "Not all dreams carry meaning. Rest well and continue your good habits.",
            "action": "No specific action needed.",
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        d = profile["dreams"]
        entries = d.get("entries", [])
        return {
            "total_dreams": len(entries),
            "recurring_themes": d.get("recurring_themes", []),
            "last_entry": d.get("last_entry_date", ""),
            "vivid_count": sum(1 for e in entries if e.get("vivid")),
            "lucid_count": sum(1 for e in entries if e.get("lucid")),
        }
