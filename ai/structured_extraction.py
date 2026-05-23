"""Structured LLM extraction via instructor + litellm (or Anthropic fallback).

Provides three extractors used by the smart bed AI pipeline:
  - analyze_journal_entry  → SleepJournalAnalysis
  - parse_bed_command      → BedCommand
  - generate_sleep_insight → SleepInsight

Priority order:
  1. litellm + instructor  — routes to any provider (Anthropic, OpenAI, Gemini, …)
     No explicit api_key needed: litellm reads ANTHROPIC_API_KEY / OPENAI_API_KEY
     from the environment.  Model string uses provider prefix: "anthropic/claude-opus-4-7".
  2. anthropic + instructor — direct Anthropic client; requires explicit api_key.
     Model string has no prefix: "claude-opus-4-7".
  3. Neither available     — every method returns None gracefully.

Requirements:
  Preferred:  litellm>=1.40.0  +  instructor>=1.4.0
  Fallback:   anthropic>=0.40.0  +  instructor>=1.4.0  +  ANTHROPIC_API_KEY
"""

from enum import Enum
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

try:
    import litellm as _litellm
    _LITELLM_AVAILABLE = True
except ImportError:
    _litellm = None  # type: ignore[assignment]
    _LITELLM_AVAILABLE = False

try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic = None  # type: ignore[assignment]
    _ANTHROPIC_AVAILABLE = False

try:
    import instructor as _instructor
    _INSTRUCTOR_AVAILABLE = True
except ImportError:
    _instructor = None  # type: ignore[assignment]
    _INSTRUCTOR_AVAILABLE = False

try:
    from langchain_core.output_parsers import PydanticOutputParser as _PydanticOutputParser
    from langchain_core.prompts import ChatPromptTemplate as _LCChatPromptTemplate
    _LANGCHAIN_CORE_AVAILABLE = True
except ImportError:
    _PydanticOutputParser = None  # type: ignore[assignment,misc]
    _LCChatPromptTemplate = None  # type: ignore[assignment]
    _LANGCHAIN_CORE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------

class SleepQuality(str, Enum):
    deep = "deep"
    moderate = "moderate"
    light = "light"
    restless = "restless"
    unknown = "unknown"


class SleepJournalAnalysis(BaseModel):
    """Structured analysis extracted from a free-text sleep journal entry."""

    sleep_quality: SleepQuality = Field(
        description="Overall sleep quality classification."
    )
    sleep_quality_score: int = Field(
        ge=1, le=10,
        description="Numeric score from 1 (terrible) to 10 (excellent).",
    )
    mood: str = Field(
        description="Single word capturing the user's morning mood, e.g. 'calm', 'groggy', 'energized'.",
    )
    sleep_issues: list[str] = Field(
        default_factory=list,
        description="Specific sleep problems mentioned, e.g. 'difficulty falling asleep', 'woke at 3 am'.",
    )
    positive_factors: list[str] = Field(
        default_factory=list,
        description="Anything the user mentioned that helped sleep.",
    )
    summary: str = Field(
        description="One-sentence plain-language summary of the night.",
    )


class BedCommandIntent(str, Enum):
    adjust_temperature = "adjust_temperature"
    control_lights = "control_lights"
    play_sounds = "play_sounds"
    stop_sounds = "stop_sounds"
    set_alarm = "set_alarm"
    cancel_alarm = "cancel_alarm"
    check_sleep_stats = "check_sleep_stats"
    general_question = "general_question"
    unknown = "unknown"


class BedCommand(BaseModel):
    """Structured intent parsed from a raw voice or text command."""

    intent: BedCommandIntent = Field(
        description="The primary action the user wants to perform."
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Intent-specific parameters. "
            "Examples: adjust_temperature → {'direction': 'up'|'down', 'degrees': int}; "
            "control_lights → {'action': 'on'|'off'|'dim', 'brightness': 0-100}; "
            "set_alarm → {'time': 'HH:MM'}."
        ),
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Model's confidence in the parsed intent (0.0–1.0).",
    )


class SleepInsight(BaseModel):
    """Actionable insight generated from a user's sleep statistics."""

    headline: str = Field(
        description="One concise sentence summarising the key finding.",
    )
    recommendations: list[str] = Field(
        min_length=1, max_length=3,
        description="Two or three short, actionable recommendations.",
    )
    priority: Literal["low", "medium", "high"] = Field(
        description="How urgently the user should act on these recommendations.",
    )
    follow_up_question: str = Field(
        description="One natural follow-up question to ask the user.",
    )


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class InstructorExtractor:
    """Structured extraction with automatic provider routing via litellm.

    Tries litellm first (supports any provider), then falls back to a direct
    Anthropic client when litellm is not installed.

    Parameters
    ----------
    api_key:
        Anthropic API key — only required for the anthropic fallback path.
        When litellm is installed, the key is read from ``ANTHROPIC_API_KEY``
        (or the relevant provider env var) automatically.
    model:
        LiteLLM-format model string, e.g. ``"anthropic/claude-opus-4-7"``,
        ``"gpt-4o"``, ``"gemini/gemini-1.5-pro"``.
        The provider prefix is stripped when falling back to the direct
        Anthropic client.
    timeout_seconds:
        HTTP timeout forwarded to the underlying HTTP client.
    """

    DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"

    def __init__(
        self,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = 20,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        self._model = str(model or self.DEFAULT_MODEL).strip()
        self._timeout_seconds = int(timeout_seconds)
        self._anthropic_client: Any = None  # cached only for the fallback path

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when at least one complete extraction stack is usable."""
        if _LITELLM_AVAILABLE and _INSTRUCTOR_AVAILABLE:
            return True
        return _ANTHROPIC_AVAILABLE and _INSTRUCTOR_AVAILABLE and bool(self._api_key)

    @property
    def active_backend(self) -> str:
        """Human-readable name of the backend that will be used."""
        if _LITELLM_AVAILABLE and _INSTRUCTOR_AVAILABLE:
            return "litellm"
        if _ANTHROPIC_AVAILABLE and _INSTRUCTOR_AVAILABLE and self._api_key:
            return "anthropic"
        return "unavailable"

    # ------------------------------------------------------------------
    # Internal client helpers
    # ------------------------------------------------------------------

    def _get_litellm_client(self) -> Any:
        """Return an instructor-patched litellm.completion callable."""
        return _instructor.from_litellm(_litellm.completion)

    def _get_anthropic_client(self) -> Any:
        """Return a cached instructor-patched Anthropic client."""
        if self._anthropic_client is None:
            self._anthropic_client = _instructor.from_anthropic(
                _anthropic.Anthropic(
                    api_key=self._api_key,
                    timeout=float(self._timeout_seconds),
                )
            )
        return self._anthropic_client

    # ------------------------------------------------------------------
    # Unified dispatch
    # ------------------------------------------------------------------

    @staticmethod
    def _lc_format_instructions(response_model: type) -> str:
        """Return JSON schema format instructions via langchain-core PydanticOutputParser."""
        if not _LANGCHAIN_CORE_AVAILABLE or _PydanticOutputParser is None:
            return ""
        try:
            parser = _PydanticOutputParser(pydantic_object=response_model)
            return "\n\n" + parser.get_format_instructions()
        except Exception:
            return ""

    @staticmethod
    def _lc_parse(text: str, response_model: type) -> Any:
        """Parse a JSON string into *response_model* via langchain-core PydanticOutputParser."""
        if not _LANGCHAIN_CORE_AVAILABLE or _PydanticOutputParser is None:
            return None
        try:
            parser = _PydanticOutputParser(pydantic_object=response_model)
            return parser.parse(text)
        except Exception:
            return None

    def _call_structured(
        self,
        response_model: type,
        messages: list[dict],
        max_tokens: int,
    ) -> Any:
        """Route an extraction call through instructor → litellm/anthropic,
        with a langchain-core PydanticOutputParser fallback when instructor
        is unavailable but litellm is present.
        """
        # ── Primary path: instructor (best structured-output support) ──────
        if _INSTRUCTOR_AVAILABLE:
            if _LITELLM_AVAILABLE:
                client = self._get_litellm_client()
                return client(
                    model=self._model,
                    response_model=response_model,
                    max_tokens=max_tokens,
                    messages=messages,
                )
            if _ANTHROPIC_AVAILABLE and self._api_key:
                client = self._get_anthropic_client()
                model = self._model.split("/")[-1]
                return client.messages.create(
                    model=model,
                    response_model=response_model,
                    max_tokens=max_tokens,
                    messages=messages,
                )

        # ── Fallback: langchain-core format instructions + litellm raw call ─
        if _LANGCHAIN_CORE_AVAILABLE and _LITELLM_AVAILABLE and _litellm is not None:
            import json as _json
            format_hint = self._lc_format_instructions(response_model)
            augmented = list(messages)
            if augmented and format_hint:
                last = dict(augmented[-1])
                last["content"] = str(last.get("content", "")) + format_hint
                augmented[-1] = last
            try:
                response = _litellm.completion(
                    model=self._model,
                    messages=augmented,
                    max_tokens=max_tokens,
                    drop_params=True,
                )
                raw = str(
                    (response.choices[0].message.content or "") if response.choices else ""
                ).strip()
                return self._lc_parse(raw, response_model)
            except Exception as exc:
                logger.debug("LangChain-core fallback extraction error: {}", exc)

        return None

    # ------------------------------------------------------------------
    # Public extractors
    # ------------------------------------------------------------------

    def analyze_journal_entry(self, text: str) -> SleepJournalAnalysis | None:
        """Extract structured analysis from a free-text sleep journal entry.

        Returns ``None`` when unavailable or the API call fails.
        """
        if not str(text or "").strip():
            return None
        try:
            return self._call_structured(
                response_model=SleepJournalAnalysis,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Analyse the following sleep journal entry and extract "
                            "structured information about sleep quality, mood, issues, "
                            "and positive factors.\n\nJournal entry:\n"
                            + text.strip()
                        ),
                    }
                ],
                max_tokens=512,
            )
        except Exception as exc:
            logger.debug("analyze_journal_entry error: {}", exc)
            return None

    def parse_bed_command(self, voice_text: str) -> BedCommand | None:
        """Parse a raw voice or text command into a structured BedCommand.

        Returns ``None`` when unavailable or the parse fails.
        """
        if not str(voice_text or "").strip():
            return None
        try:
            return self._call_structured(
                response_model=BedCommand,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Parse the following smart bed voice command into a structured intent.\n\n"
                            "Command: " + voice_text.strip()
                        ),
                    }
                ],
                max_tokens=256,
            )
        except Exception as exc:
            logger.debug("parse_bed_command error: {}", exc)
            return None

    def generate_sleep_insight(self, sleep_stats: dict) -> SleepInsight | None:
        """Generate an actionable insight from a sleep statistics dict.

        *sleep_stats* should contain keys such as ``avg_sleep_hours``,
        ``bedtime_consistency_score``, ``trend``, ``short_sleep_count``, etc.
        Returns ``None`` when unavailable or the generation fails.
        """
        if not isinstance(sleep_stats, dict) or not sleep_stats:
            return None
        import json
        try:
            return self._call_structured(
                response_model=SleepInsight,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Based on the following sleep statistics, generate a concise "
                            "actionable insight for the user.\n\nSleep statistics:\n"
                            + json.dumps(sleep_stats, indent=2)
                        ),
                    }
                ],
                max_tokens=512,
            )
        except Exception as exc:
            logger.debug("generate_sleep_insight error: {}", exc)
            return None