"""Tests for ai/structured_extraction.py — litellm-first design.

All tests run offline.  Both litellm and anthropic are fully mocked so no
network calls or real API keys are needed.

Backend routing under test
--------------------------
  litellm path  : litellm + instructor available
                  client = instructor.from_litellm(litellm.completion)
                  call   = client(model=..., response_model=..., messages=[...])

  anthropic path: litellm NOT available, anthropic + instructor + api_key
                  client = instructor.from_anthropic(anthropic.Anthropic(...))
                  call   = client.messages.create(model=..., response_model=..., ...)

  unavailable   : neither stack complete → every method returns None
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _make_litellm_mock():
    mod = types.ModuleType("litellm")
    mod.completion = MagicMock()
    return mod


def _make_instructor_mock():
    mod = types.ModuleType("instructor")
    # litellm path: from_litellm returns a callable client
    _litellm_client = MagicMock()
    mod.from_litellm = MagicMock(return_value=_litellm_client)
    # anthropic path: from_anthropic returns object with .messages.create
    _anthropic_client = MagicMock()
    mod.from_anthropic = MagicMock(return_value=_anthropic_client)
    return mod


def _make_anthropic_mock():
    mod = types.ModuleType("anthropic")

    class _FakeClient:
        def __init__(self, **kw):
            pass

    mod.Anthropic = _FakeClient
    return mod


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load(
    monkeypatch,
    *,
    litellm: bool = True,
    anthropic: bool = True,
    instructor: bool = True,
):
    for key in list(sys.modules):
        if "structured_extraction" in key:
            del sys.modules[key]

    ll_mod = _make_litellm_mock() if litellm else None
    ant_mod = _make_anthropic_mock() if anthropic else None
    ins_mod = _make_instructor_mock() if instructor else None

    monkeypatch.setitem(sys.modules, "litellm", ll_mod)
    monkeypatch.setitem(sys.modules, "anthropic", ant_mod)
    monkeypatch.setitem(sys.modules, "instructor", ins_mod)

    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "structured_extraction",
        Path(__file__).parent.parent / "ai" / "structured_extraction.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Reflect the monkeypatched availability flags
    mod._LITELLM_AVAILABLE = litellm
    mod._ANTHROPIC_AVAILABLE = anthropic
    mod._INSTRUCTOR_AVAILABLE = instructor
    if litellm:
        mod._litellm = ll_mod
    if instructor:
        mod._instructor = ins_mod
    if anthropic:
        mod._anthropic = ant_mod

    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mod_full(monkeypatch):
    """litellm + anthropic + instructor — litellm path preferred."""
    return _load(monkeypatch, litellm=True, anthropic=True, instructor=True)


@pytest.fixture()
def mod_anthropic_only(monkeypatch):
    """No litellm — falls back to direct anthropic path."""
    return _load(monkeypatch, litellm=False, anthropic=True, instructor=True)


@pytest.fixture()
def mod_no_instructor(monkeypatch):
    """instructor absent — nothing works."""
    return _load(monkeypatch, litellm=True, anthropic=True, instructor=False)


@pytest.fixture()
def mod_neither(monkeypatch):
    return _load(monkeypatch, litellm=False, anthropic=False, instructor=False)


# Convenience: extractor with a mocked litellm client ready to return a value
def _extractor_litellm(mod, return_value):
    e = mod.InstructorExtractor()
    mod._instructor.from_litellm.return_value.return_value = return_value
    return e


def _extractor_anthropic(mod, return_value):
    e = mod.InstructorExtractor(api_key="real-key")
    mod._instructor.from_anthropic.return_value.messages.create.return_value = return_value
    return e


# ---------------------------------------------------------------------------
# Availability flags
# ---------------------------------------------------------------------------


class TestFlags:
    def test_litellm_flag_true(self, mod_full):
        assert mod_full._LITELLM_AVAILABLE is True

    def test_litellm_flag_false(self, mod_anthropic_only):
        assert mod_anthropic_only._LITELLM_AVAILABLE is False

    def test_instructor_flag_false(self, mod_no_instructor):
        assert mod_no_instructor._INSTRUCTOR_AVAILABLE is False


# ---------------------------------------------------------------------------
# Pydantic models — construction & validation
# ---------------------------------------------------------------------------


class TestSleepJournalAnalysis:
    def test_valid_construction(self, mod_full):
        obj = mod_full.SleepJournalAnalysis(
            sleep_quality="deep",
            sleep_quality_score=9,
            mood="calm",
            summary="Great night.",
        )
        assert obj.sleep_quality_score == 9

    def test_score_too_high_rejected(self, mod_full):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            mod_full.SleepJournalAnalysis(
                sleep_quality="deep", sleep_quality_score=11, mood="ok", summary="x"
            )

    def test_default_lists_empty(self, mod_full):
        obj = mod_full.SleepJournalAnalysis(
            sleep_quality="unknown", sleep_quality_score=5, mood="tired", summary="meh"
        )
        assert obj.sleep_issues == []
        assert obj.positive_factors == []


class TestBedCommand:
    def test_valid_construction(self, mod_full):
        obj = mod_full.BedCommand(
            intent="adjust_temperature",
            parameters={"direction": "up", "degrees": 2},
            confidence=0.95,
        )
        assert obj.intent == mod_full.BedCommandIntent.adjust_temperature

    def test_confidence_over_one_rejected(self, mod_full):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            mod_full.BedCommand(intent="unknown", parameters={}, confidence=1.5)

    def test_default_parameters(self, mod_full):
        obj = mod_full.BedCommand(intent="unknown", confidence=0.1)
        assert obj.parameters == {}


class TestSleepInsight:
    def test_valid_construction(self, mod_full):
        obj = mod_full.SleepInsight(
            headline="Sleep is short.",
            recommendations=["Bed earlier"],
            priority="medium",
            follow_up_question="How do you feel?",
        )
        assert obj.priority == "medium"

    def test_invalid_priority_rejected(self, mod_full):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            mod_full.SleepInsight(
                headline="x",
                recommendations=["y"],
                priority="urgent",
                follow_up_question="z",
            )


# ---------------------------------------------------------------------------
# InstructorExtractor construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_model_litellm_format(self, mod_full):
        e = mod_full.InstructorExtractor()
        assert e._model == mod_full.InstructorExtractor.DEFAULT_MODEL

    def test_custom_model(self, mod_full):
        e = mod_full.InstructorExtractor(model="gpt-4o")
        assert e._model == "gpt-4o"

    def test_api_key_optional_with_litellm(self, mod_full):
        e = mod_full.InstructorExtractor()
        assert e._api_key == ""

    def test_timeout_stored(self, mod_full):
        e = mod_full.InstructorExtractor(timeout_seconds=30)
        assert e._timeout_seconds == 30


# ---------------------------------------------------------------------------
# available property
# ---------------------------------------------------------------------------


class TestAvailableProperty:
    def test_available_with_litellm_no_key(self, mod_full):
        assert mod_full.InstructorExtractor().available is True

    def test_available_anthropic_with_key(self, mod_anthropic_only):
        assert mod_anthropic_only.InstructorExtractor(api_key="k").available is True

    def test_not_available_anthropic_no_key(self, mod_anthropic_only):
        assert mod_anthropic_only.InstructorExtractor(api_key="").available is False

    def test_not_available_no_instructor(self, mod_no_instructor):
        assert mod_no_instructor.InstructorExtractor(api_key="k").available is False

    def test_not_available_neither(self, mod_neither):
        assert mod_neither.InstructorExtractor(api_key="k").available is False


# ---------------------------------------------------------------------------
# active_backend property
# ---------------------------------------------------------------------------


class TestActiveBackend:
    def test_litellm_when_available(self, mod_full):
        assert mod_full.InstructorExtractor().active_backend == "litellm"

    def test_anthropic_fallback(self, mod_anthropic_only):
        assert mod_anthropic_only.InstructorExtractor(api_key="k").active_backend == "anthropic"

    def test_unavailable(self, mod_anthropic_only):
        assert mod_anthropic_only.InstructorExtractor(api_key="").active_backend == "unavailable"

    def test_unavailable_neither(self, mod_neither):
        assert mod_neither.InstructorExtractor().active_backend == "unavailable"


# ---------------------------------------------------------------------------
# _call_structured dispatch
# ---------------------------------------------------------------------------


class TestCallStructured:
    def test_uses_litellm_callable(self, mod_full):
        e = mod_full.InstructorExtractor()
        fake = MagicMock()
        mod_full._instructor.from_litellm.return_value.return_value = fake
        result = e._call_structured(mod_full.BedCommand, [{"role": "user", "content": "hi"}], 256)
        assert result is fake
        # from_litellm should have been called with litellm.completion
        mod_full._instructor.from_litellm.assert_called()

    def test_uses_anthropic_when_no_litellm(self, mod_anthropic_only):
        e = mod_anthropic_only.InstructorExtractor(api_key="real-key")
        fake = MagicMock()
        mod_anthropic_only._instructor.from_anthropic.return_value.messages.create.return_value = (
            fake
        )
        result = e._call_structured(
            mod_anthropic_only.BedCommand, [{"role": "user", "content": "hi"}], 256
        )
        assert result is fake

    def test_returns_none_when_no_instructor(self, mod_no_instructor):
        e = mod_no_instructor.InstructorExtractor(api_key="k")
        assert e._call_structured(MagicMock(), [], 256) is None

    def test_model_stripped_for_anthropic(self, mod_anthropic_only):
        e = mod_anthropic_only.InstructorExtractor(api_key="k", model="anthropic/claude-opus-4-7")
        mod_anthropic_only._instructor.from_anthropic.return_value.messages.create.return_value = (
            MagicMock()
        )
        e._call_structured(mod_anthropic_only.SleepInsight, [{"role": "user", "content": "x"}], 512)
        call_kwargs = (
            mod_anthropic_only._instructor.from_anthropic.return_value.messages.create.call_args[1]
        )
        assert call_kwargs["model"] == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# _get_anthropic_client caching
# ---------------------------------------------------------------------------


class TestAnthropicClientCaching:
    def test_client_cached_on_second_call(self, mod_anthropic_only):
        e = mod_anthropic_only.InstructorExtractor(api_key="k")
        c1 = e._get_anthropic_client()
        c2 = e._get_anthropic_client()
        assert c1 is c2
        assert mod_anthropic_only._instructor.from_anthropic.call_count == 1


# ---------------------------------------------------------------------------
# analyze_journal_entry — litellm path
# ---------------------------------------------------------------------------


class TestAnalyzeJournalLiteLLM:
    def _fake_analysis(self, mod):
        return mod.SleepJournalAnalysis(
            sleep_quality="deep",
            sleep_quality_score=9,
            mood="calm",
            summary="Great.",
            sleep_issues=[],
            positive_factors=[],
        )

    def test_returns_model(self, mod_full):
        fake = self._fake_analysis(mod_full)
        e = _extractor_litellm(mod_full, fake)
        assert e.analyze_journal_entry("Slept well.") is fake

    def test_response_model_kwarg_passed(self, mod_full):
        fake = self._fake_analysis(mod_full)
        e = _extractor_litellm(mod_full, fake)
        e.analyze_journal_entry("Slept well.")
        call_kwargs = mod_full._instructor.from_litellm.return_value.call_args[1]
        assert call_kwargs["response_model"] is mod_full.SleepJournalAnalysis

    def test_model_id_passed(self, mod_full):
        fake = self._fake_analysis(mod_full)
        e = _extractor_litellm(mod_full, fake)
        e.analyze_journal_entry("Test entry.")
        call_kwargs = mod_full._instructor.from_litellm.return_value.call_args[1]
        assert call_kwargs["model"] == mod_full.InstructorExtractor.DEFAULT_MODEL

    def test_returns_none_on_empty(self, mod_full):
        e = mod_full.InstructorExtractor()
        assert e.analyze_journal_entry("") is None

    def test_returns_none_on_api_error(self, mod_full):
        e = mod_full.InstructorExtractor()
        mod_full._instructor.from_litellm.return_value.side_effect = RuntimeError("API error")
        assert e.analyze_journal_entry("I slept 6 hours.") is None


# ---------------------------------------------------------------------------
# analyze_journal_entry — anthropic fallback path
# ---------------------------------------------------------------------------


class TestAnalyzeJournalAnthropic:
    def test_returns_model(self, mod_anthropic_only):
        fake = mod_anthropic_only.SleepJournalAnalysis(
            sleep_quality="moderate",
            sleep_quality_score=6,
            mood="tired",
            summary="Average.",
            sleep_issues=["woke twice"],
        )
        e = _extractor_anthropic(mod_anthropic_only, fake)
        assert e.analyze_journal_entry("Woke up twice.") is fake

    def test_messages_create_called(self, mod_anthropic_only):
        fake = mod_anthropic_only.SleepJournalAnalysis(
            sleep_quality="light", sleep_quality_score=4, mood="groggy", summary="Bad night."
        )
        e = _extractor_anthropic(mod_anthropic_only, fake)
        e.analyze_journal_entry("Rough night.")
        assert mod_anthropic_only._instructor.from_anthropic.return_value.messages.create.called

    def test_returns_none_without_key(self, mod_anthropic_only):
        e = mod_anthropic_only.InstructorExtractor(api_key="")
        assert e.analyze_journal_entry("Slept fine.") is None


# ---------------------------------------------------------------------------
# parse_bed_command
# ---------------------------------------------------------------------------


class TestParseBedCommand:
    def test_returns_command_litellm(self, mod_full):
        fake = mod_full.BedCommand(
            intent="control_lights", parameters={"action": "dim"}, confidence=0.9
        )
        e = _extractor_litellm(mod_full, fake)
        assert e.parse_bed_command("dim the lights") is fake

    def test_response_model_is_bed_command(self, mod_full):
        fake = mod_full.BedCommand(intent="unknown", confidence=0.5)
        e = _extractor_litellm(mod_full, fake)
        e.parse_bed_command("do something")
        call_kwargs = mod_full._instructor.from_litellm.return_value.call_args[1]
        assert call_kwargs["response_model"] is mod_full.BedCommand

    def test_returns_none_on_empty(self, mod_full):
        e = mod_full.InstructorExtractor()
        assert e.parse_bed_command("") is None

    def test_returns_none_on_error(self, mod_full):
        e = mod_full.InstructorExtractor()
        mod_full._instructor.from_litellm.return_value.side_effect = RuntimeError("timeout")
        assert e.parse_bed_command("turn off lights") is None

    def test_anthropic_fallback(self, mod_anthropic_only):
        fake = mod_anthropic_only.BedCommand(
            intent="set_alarm", parameters={"time": "07:00"}, confidence=0.95
        )
        e = _extractor_anthropic(mod_anthropic_only, fake)
        assert e.parse_bed_command("wake me at 7") is fake


# ---------------------------------------------------------------------------
# generate_sleep_insight
# ---------------------------------------------------------------------------


class TestGenerateSleepInsight:
    def _fake_insight(self, mod):
        return mod.SleepInsight(
            headline="Short sleep detected.",
            recommendations=["Sleep earlier"],
            priority="high",
            follow_up_question="Anything stressful?",
        )

    def test_returns_insight_litellm(self, mod_full):
        fake = self._fake_insight(mod_full)
        e = _extractor_litellm(mod_full, fake)
        assert e.generate_sleep_insight({"avg_sleep_hours": 5.5}) is fake

    def test_stats_serialized_into_prompt(self, mod_full):
        fake = self._fake_insight(mod_full)
        e = _extractor_litellm(mod_full, fake)
        e.generate_sleep_insight({"avg_sleep_hours": 7.2})
        call_kwargs = mod_full._instructor.from_litellm.return_value.call_args[1]
        assert "7.2" in call_kwargs["messages"][0]["content"]

    def test_returns_none_on_empty_dict(self, mod_full):
        e = mod_full.InstructorExtractor()
        assert e.generate_sleep_insight({}) is None

    def test_returns_none_on_non_dict(self, mod_full):
        e = mod_full.InstructorExtractor()
        assert e.generate_sleep_insight(None) is None  # type: ignore[arg-type]

    def test_returns_none_on_error(self, mod_full):
        e = mod_full.InstructorExtractor()
        mod_full._instructor.from_litellm.return_value.side_effect = RuntimeError("quota")
        assert e.generate_sleep_insight({"avg_sleep_hours": 6}) is None

    def test_anthropic_fallback(self, mod_anthropic_only):
        fake = self._fake_insight(mod_anthropic_only)
        e = _extractor_anthropic(mod_anthropic_only, fake)
        assert e.generate_sleep_insight({"avg_sleep_hours": 6.5}) is fake


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestEnums:
    @pytest.mark.parametrize(
        "intent",
        [
            "adjust_temperature",
            "control_lights",
            "play_sounds",
            "stop_sounds",
            "set_alarm",
            "cancel_alarm",
            "check_sleep_stats",
            "general_question",
            "unknown",
        ],
    )
    def test_bed_command_intent_values(self, mod_full, intent):
        obj = mod_full.BedCommand(intent=intent, confidence=0.5)
        assert obj.intent.value == intent

    @pytest.mark.parametrize("q", ["deep", "moderate", "light", "restless", "unknown"])
    def test_sleep_quality_values(self, mod_full, q):
        obj = mod_full.SleepJournalAnalysis(
            sleep_quality=q, sleep_quality_score=5, mood="ok", summary="x"
        )
        assert obj.sleep_quality.value == q
