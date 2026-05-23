"""Tests for LiteLLMConversationEngine in ai/conversation_engine.py.

All tests run offline — litellm is fully mocked; no network calls or real
API keys are needed.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock factory
# ---------------------------------------------------------------------------

def _make_litellm_mock(chunks=("Hello", " there")):
    """Return a minimal litellm module mock."""
    mod = types.ModuleType("litellm")

    class _Delta:
        def __init__(self, text):
            self.content = text

    class _StreamChoice:
        def __init__(self, text):
            self.delta = _Delta(text)

    class _StreamChunk:
        def __init__(self, text):
            self.choices = [_StreamChoice(text)]

    class _Message:
        def __init__(self, text):
            self.content = text

    class _Choice:
        def __init__(self, text):
            self.message = _Message(text)

    class _Response:
        def __init__(self, text):
            self.choices = [_Choice(text)]

    def _completion(**kwargs):
        if kwargs.get("stream"):
            return iter([_StreamChunk(c) for c in chunks])
        return _Response("".join(chunks))

    mod.completion = MagicMock(side_effect=_completion)
    return mod


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

def _load_mod(monkeypatch, litellm_available=True):
    for key in list(sys.modules):
        if "conversation_engine" in key and "test" not in key:
            del sys.modules[key]

    # Silence core.http_client
    fake_core = types.ModuleType("core")
    fake_http = types.ModuleType("core.http_client")
    fake_http.http = MagicMock()
    fake_core.http_client = fake_http
    monkeypatch.setitem(sys.modules, "core", fake_core)
    monkeypatch.setitem(sys.modules, "core.http_client", fake_http)

    ll_mod = _make_litellm_mock() if litellm_available else None
    monkeypatch.setitem(sys.modules, "litellm", ll_mod)
    monkeypatch.setitem(sys.modules, "anthropic", None)

    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "conversation_engine_ll",
        Path(__file__).parent.parent / "ai" / "conversation_engine.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._LITELLM_AVAILABLE = litellm_available
    if litellm_available:
        mod._litellm = ll_mod
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mod(monkeypatch):
    return _load_mod(monkeypatch, litellm_available=True)


@pytest.fixture()
def mod_unavailable(monkeypatch):
    return _load_mod(monkeypatch, litellm_available=False)


# ---------------------------------------------------------------------------
# Module-level flag
# ---------------------------------------------------------------------------

class TestFlag:
    def test_litellm_available_flag_true(self, mod):
        assert mod._LITELLM_AVAILABLE is True

    def test_litellm_available_flag_false(self, mod_unavailable):
        assert mod_unavailable._LITELLM_AVAILABLE is False


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_default_model(self, mod):
        e = mod.LiteLLMConversationEngine()
        assert e._model == "anthropic/claude-opus-4-7"

    def test_custom_model(self, mod):
        e = mod.LiteLLMConversationEngine(model="gpt-4o")
        assert e._model == "gpt-4o"

    def test_api_key_none_when_empty(self, mod):
        e = mod.LiteLLMConversationEngine()
        assert e._api_key is None

    def test_api_key_stored_when_provided(self, mod):
        e = mod.LiteLLMConversationEngine(api_key="sk-test")
        assert e._api_key == "sk-test"

    def test_history_starts_empty(self, mod):
        e = mod.LiteLLMConversationEngine()
        assert e.history == []

    def test_timeout_stored(self, mod):
        e = mod.LiteLLMConversationEngine(timeout_seconds=45)
        assert e._timeout_seconds == 45


# ---------------------------------------------------------------------------
# System prompt construction
# ---------------------------------------------------------------------------

class TestBuildSystemText:
    def _engine(self, mod):
        return mod.LiteLLMConversationEngine()

    def test_persona_text_included(self, mod):
        e = self._engine(mod)
        text = e._build_system_text("therapist", "", "neutral", "normal")
        assert "calm" in text.lower() or "therapeutic" in text.lower() or "empathy" in text.lower() or "professional" in text.lower()

    def test_temporal_grounding_included(self, mod):
        e = self._engine(mod)
        text = e._build_system_text("guide", "", "neutral", "normal")
        assert "runtime" in text.lower() or "temporal" in text.lower()

    def test_mood_distressed_included(self, mod):
        e = self._engine(mod)
        text = e._build_system_text("therapist", "", "distressed", "normal")
        assert "distressed" in text.lower()

    def test_cognitive_exhausted_included(self, mod):
        e = self._engine(mod)
        text = e._build_system_text("guide", "", "neutral", "exhausted")
        assert "exhausted" in text.lower()

    def test_user_context_appended(self, mod):
        e = self._engine(mod)
        text = e._build_system_text("coach", "Prefers bullet points", "neutral", "normal")
        assert "Prefers bullet points" in text


# ---------------------------------------------------------------------------
# Message list construction
# ---------------------------------------------------------------------------

class TestBuildMessages:
    def test_first_message_is_system(self, mod):
        e = mod.LiteLLMConversationEngine()
        msgs = e._build_messages("Hi", "therapist", "", "", "neutral", "normal")
        assert msgs[0]["role"] == "system"

    def test_last_message_is_user(self, mod):
        e = mod.LiteLLMConversationEngine()
        msgs = e._build_messages("Good morning", "guide", "", "", "neutral", "normal")
        assert msgs[-1] == {"role": "user", "content": "Good morning"}

    def test_realtime_context_prepended_to_user(self, mod):
        e = mod.LiteLLMConversationEngine()
        msgs = e._build_messages("What time?", "guide", "time=08:00", "", "neutral", "normal")
        assert "time=08:00" in msgs[-1]["content"]
        assert "What time?" in msgs[-1]["content"]

    def test_history_included_between_system_and_user(self, mod):
        e = mod.LiteLLMConversationEngine()
        e.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        msgs = e._build_messages("How are you?", "guide", "", "", "neutral", "normal")
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "user", "assistant", "user"]


# ---------------------------------------------------------------------------
# generate_response — fallback
# ---------------------------------------------------------------------------

class TestGenerateResponseFallback:
    def test_fallback_when_unavailable(self, mod_unavailable):
        e = mod_unavailable.LiteLLMConversationEngine()
        result = e.generate_response("Hi")
        assert "fallback" in result.lower()

    def test_fallback_includes_personality(self, mod_unavailable):
        e = mod_unavailable.LiteLLMConversationEngine()
        result = e.generate_response("Hi", personality="coach")
        assert "coach" in result.lower()

    def test_fallback_on_litellm_error(self, mod):
        e = mod.LiteLLMConversationEngine()
        mod._litellm.completion.side_effect = RuntimeError("API down")
        result = e.generate_response("Hi")
        assert "fallback" in result.lower()


# ---------------------------------------------------------------------------
# generate_response — success
# ---------------------------------------------------------------------------

class TestGenerateResponseSuccess:
    def test_returns_text(self, mod):
        e = mod.LiteLLMConversationEngine()
        result = e.generate_response("Good morning")
        assert result == "Hello there"

    def test_history_updated(self, mod):
        e = mod.LiteLLMConversationEngine()
        e.generate_response("Good morning")
        assert len(e.history) == 2
        assert e.history[0]["role"] == "user"
        assert e.history[1]["role"] == "assistant"

    def test_model_passed_to_litellm(self, mod):
        e = mod.LiteLLMConversationEngine(model="gpt-4o")
        e.generate_response("Hi")
        call_kwargs = mod._litellm.completion.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    def test_stream_false_for_non_streaming(self, mod):
        e = mod.LiteLLMConversationEngine()
        e.generate_response("Hi")
        call_kwargs = mod._litellm.completion.call_args[1]
        assert call_kwargs.get("stream") is not True

    def test_api_key_passed_when_set(self, mod):
        e = mod.LiteLLMConversationEngine(api_key="sk-abc")
        e.generate_response("Hi")
        call_kwargs = mod._litellm.completion.call_args[1]
        assert call_kwargs.get("api_key") == "sk-abc"

    def test_api_key_omitted_when_empty(self, mod):
        e = mod.LiteLLMConversationEngine()
        e.generate_response("Hi")
        call_kwargs = mod._litellm.completion.call_args[1]
        assert "api_key" not in call_kwargs

    def test_min_max_tokens_40(self, mod):
        e = mod.LiteLLMConversationEngine()
        e.generate_response("Hi", max_response_tokens=5)
        call_kwargs = mod._litellm.completion.call_args[1]
        assert call_kwargs["max_tokens"] >= 40


# ---------------------------------------------------------------------------
# generate_response_stream — fallback
# ---------------------------------------------------------------------------

class TestGenerateResponseStreamFallback:
    def test_fallback_when_unavailable(self, mod_unavailable):
        e = mod_unavailable.LiteLLMConversationEngine()
        chunks = list(e.generate_response_stream("Hi"))
        assert any("fallback" in c.lower() for c in chunks)

    def test_fallback_on_litellm_error(self, mod):
        e = mod.LiteLLMConversationEngine()
        mod._litellm.completion.side_effect = RuntimeError("timeout")
        chunks = list(e.generate_response_stream("Hi"))
        assert chunks
        assert any("fallback" in c.lower() for c in chunks)


# ---------------------------------------------------------------------------
# generate_response_stream — success
# ---------------------------------------------------------------------------

class TestGenerateResponseStreamSuccess:
    def test_yields_chunks(self, mod):
        e = mod.LiteLLMConversationEngine()
        chunks = list(e.generate_response_stream("Good morning"))
        assert chunks == ["Hello", " there"]

    def test_history_updated_after_stream(self, mod):
        e = mod.LiteLLMConversationEngine()
        list(e.generate_response_stream("Good morning"))
        assert len(e.history) == 2
        assert e.history[1]["content"] == "Hello there"

    def test_stream_true_passed_to_litellm(self, mod):
        e = mod.LiteLLMConversationEngine()
        list(e.generate_response_stream("Hi"))
        call_kwargs = mod._litellm.completion.call_args[1]
        assert call_kwargs["stream"] is True

    def test_model_passed_to_litellm(self, mod):
        e = mod.LiteLLMConversationEngine(model="gemini/gemini-1.5-pro")
        list(e.generate_response_stream("Hi"))
        call_kwargs = mod._litellm.completion.call_args[1]
        assert call_kwargs["model"] == "gemini/gemini-1.5-pro"


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

class TestHistoryManagement:
    def test_appends_two_entries(self, mod):
        e = mod.LiteLLMConversationEngine()
        e._append_history("Q", "A")
        assert len(e.history) == 2

    def test_truncates_at_max(self, mod):
        e = mod.LiteLLMConversationEngine()
        for i in range(10):
            e._append_history(f"Q{i}", f"A{i}")
        assert len(e.history) == e.max_history_turns * 2

    def test_keeps_most_recent(self, mod):
        e = mod.LiteLLMConversationEngine()
        for i in range(10):
            e._append_history(f"Q{i}", f"A{i}")
        assert e.history[-1]["content"] == "A9"


# ---------------------------------------------------------------------------
# Fallback message
# ---------------------------------------------------------------------------

class TestFallbackMessage:
    def test_includes_user_text(self, mod):
        msg = mod.LiteLLMConversationEngine._fallback_response("Wake me up", "guide")
        assert "Wake me up" in msg

    def test_includes_personality(self, mod):
        msg = mod.LiteLLMConversationEngine._fallback_response("Hi", "coach")
        assert "coach" in msg