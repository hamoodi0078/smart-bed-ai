"""Tests for AnthropicConversationEngine in ai/conversation_engine.py.

All tests run offline — the anthropic package and the Anthropic API are
fully mocked so no network calls or real API keys are needed.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers to build a minimal mock of the anthropic library
# ---------------------------------------------------------------------------


def _make_anthropic_mock():
    """Return a minimal anthropic module mock with Anthropic client class."""
    mod = types.ModuleType("anthropic")

    class _TextBlock:
        def __init__(self, text):
            self.type = "text"
            self.text = text

    class _ThinkingBlock:
        def __init__(self):
            self.type = "thinking"
            self.thinking = "..."

    class _Message:
        def __init__(self, text):
            self.content = [_TextBlock(text)]
            self.stop_reason = "end_turn"

    class _Stream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        @property
        def text_stream(self):
            return iter(self._chunks)

    class _Messages:
        def __init__(self, chunks=("Hello", " there")):
            self._chunks = chunks
            self.last_call_kwargs = {}

        def create(self, **kwargs):
            self.last_call_kwargs = kwargs
            text = "".join(self._chunks)
            return _Message(text)

        def stream(self, **kwargs):
            self.last_call_kwargs = kwargs
            return _Stream(self._chunks)

    class _Anthropic:
        def __init__(self, **kwargs):
            self.messages = _Messages()
            self._init_kwargs = kwargs

    mod.Anthropic = _Anthropic
    mod._TextBlock = _TextBlock
    mod._ThinkingBlock = _ThinkingBlock
    mod._Message = _Message
    mod._Stream = _Stream
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_http_client(monkeypatch):
    """Silence the core.http_client import that conversation_engine uses."""
    fake_core = types.ModuleType("core")
    fake_http_mod = types.ModuleType("core.http_client")
    fake_http_mod.http = MagicMock()
    fake_core.http_client = fake_http_mod
    monkeypatch.setitem(sys.modules, "core", fake_core)
    monkeypatch.setitem(sys.modules, "core.http_client", fake_http_mod)


@pytest.fixture()
def engine_mod(monkeypatch):
    """Import the module with anthropic mocked as available."""
    anthropic_mock = _make_anthropic_mock()
    monkeypatch.setitem(sys.modules, "anthropic", anthropic_mock)

    # Force re-import so the patched sys.modules is used
    if "ai.conversation_engine" in sys.modules:
        del sys.modules["ai.conversation_engine"]
    if "conversation_engine" in sys.modules:
        del sys.modules["conversation_engine"]

    import importlib
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "conversation_engine",
        Path(__file__).parent.parent / "ai" / "conversation_engine.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Inject the anthropic mock so the module-level flag is True
    mod._ANTHROPIC_AVAILABLE = True
    mod._anthropic = anthropic_mock
    return mod


@pytest.fixture()
def engine_mod_unavailable(monkeypatch):
    """Import the module with anthropic NOT available."""
    monkeypatch.setitem(sys.modules, "anthropic", None)

    if "ai.conversation_engine" in sys.modules:
        del sys.modules["ai.conversation_engine"]
    if "conversation_engine" in sys.modules:
        del sys.modules["conversation_engine"]

    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "conversation_engine",
        Path(__file__).parent.parent / "ai" / "conversation_engine.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._ANTHROPIC_AVAILABLE = False
    return mod


# ---------------------------------------------------------------------------
# Module-level flag
# ---------------------------------------------------------------------------


class TestAvailabilityFlag:
    def test_flag_is_bool_when_available(self, engine_mod):
        assert isinstance(engine_mod._ANTHROPIC_AVAILABLE, bool)

    def test_flag_is_false_when_unavailable(self, engine_mod_unavailable):
        assert engine_mod_unavailable._ANTHROPIC_AVAILABLE is False


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_model(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="key")
        assert e._model == "claude-opus-4-7"

    def test_custom_model(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k", model="claude-haiku-4-5")
        assert e._model == "claude-haiku-4-5"

    def test_empty_api_key_stored(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine()
        assert e._api_key == ""

    def test_history_starts_empty(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        assert e.history == []

    def test_max_history_turns_default(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        assert e.max_history_turns == 6

    def test_timeout_stored(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k", timeout_seconds=30)
        assert e._timeout_seconds == 30


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_returns_none_when_unavailable(self, engine_mod):
        engine_mod._ANTHROPIC_AVAILABLE = False
        e = engine_mod.AnthropicConversationEngine(api_key="key")
        assert e._get_client() is None

    def test_returns_none_when_no_api_key(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="")
        assert e._get_client() is None

    def test_returns_client_when_available_and_key_set(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="test-key")
        client = e._get_client()
        assert client is not None

    def test_client_is_cached(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="test-key")
        c1 = e._get_client()
        c2 = e._get_client()
        assert c1 is c2


# ---------------------------------------------------------------------------
# System blocks / prompt caching
# ---------------------------------------------------------------------------


class TestBuildSystemBlocks:
    def _engine(self, engine_mod):
        return engine_mod.AnthropicConversationEngine(api_key="k")

    def test_first_block_has_cache_control(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("therapist", "", "neutral", "normal")
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_first_block_type_is_text(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("guide", "", "neutral", "normal")
        assert blocks[0]["type"] == "text"

    def test_persona_text_in_stable_block(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("therapist", "", "neutral", "normal")
        stable_text = blocks[0]["text"]
        assert (
            "therapeutic" in stable_text.lower()
            or "therapist" in stable_text.lower()
            or "therapeutic" in stable_text.lower()
            or "therapeutic" in stable_text.lower()
            or "calm" in stable_text.lower()
        )

    def test_volatile_block_present(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("coach", "", "neutral", "normal")
        assert len(blocks) >= 2

    def test_volatile_block_has_no_cache_control(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("coach", "", "neutral", "normal")
        assert "cache_control" not in blocks[1]

    def test_temporal_grounding_in_volatile_block(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("guide", "", "neutral", "normal")
        assert "runtime" in blocks[1]["text"].lower() or "temporal" in blocks[1]["text"].lower()

    def test_user_context_appended_to_volatile_block(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks(
            "therapist", "User likes short replies", "neutral", "normal"
        )
        assert "User likes short replies" in blocks[1]["text"]

    def test_mood_layer_for_distressed(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("therapist", "", "distressed", "normal")
        assert "distressed" in blocks[1]["text"].lower()

    def test_cognitive_load_exhausted_instruction(self, engine_mod):
        e = self._engine(engine_mod)
        blocks = e._build_system_blocks("guide", "", "neutral", "exhausted")
        assert "exhausted" in blocks[1]["text"].lower()


# ---------------------------------------------------------------------------
# Message list construction
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_user_message_appended(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        msgs = e._build_messages("Hello")
        assert msgs[-1] == {"role": "user", "content": "Hello"}

    def test_realtime_context_prepended(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        msgs = e._build_messages("What time is it?", realtime_context="time=08:00")
        assert "time=08:00" in msgs[-1]["content"]
        assert "What time is it?" in msgs[-1]["content"]

    def test_history_included(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        e.history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        msgs = e._build_messages("How are you?")
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[-1]["content"] == "How are you?"


# ---------------------------------------------------------------------------
# generate_response — fallbacks
# ---------------------------------------------------------------------------


class TestGenerateResponseFallback:
    def test_fallback_when_unavailable(self, engine_mod_unavailable):
        e = engine_mod_unavailable.AnthropicConversationEngine(api_key="k")
        result = e.generate_response("Hi")
        assert "fallback" in result.lower() or "Claude fallback" in result

    def test_fallback_when_no_api_key(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="")
        result = e.generate_response("Hi")
        assert "fallback" in result.lower()

    def test_fallback_contains_personality(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="")
        result = e.generate_response("Hi", personality="coach")
        assert "coach" in result.lower()


# ---------------------------------------------------------------------------
# generate_response — success path (mocked client)
# ---------------------------------------------------------------------------


class TestGenerateResponseSuccess:
    def test_returns_text_from_api(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        result = e.generate_response("Good morning")
        assert result == "Hello there"

    def test_history_updated_on_success(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        e.generate_response("Good morning")
        assert len(e.history) == 2
        assert e.history[0]["role"] == "user"
        assert e.history[1]["role"] == "assistant"

    def test_thinking_param_passed(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        e.generate_response("Tell me a fact")
        client = e._get_client()
        kwargs = client.messages.last_call_kwargs
        assert kwargs.get("thinking") == {"type": "adaptive"}

    def test_min_max_tokens_512(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        e.generate_response("Hi", max_response_tokens=50)
        client = e._get_client()
        assert client.messages.last_call_kwargs["max_tokens"] >= 512

    def test_model_passed_to_api(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        e.generate_response("Hi")
        client = e._get_client()
        assert client.messages.last_call_kwargs["model"] == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# generate_response_stream — fallbacks
# ---------------------------------------------------------------------------


class TestGenerateResponseStreamFallback:
    def test_fallback_when_unavailable(self, engine_mod_unavailable):
        e = engine_mod_unavailable.AnthropicConversationEngine(api_key="k")
        chunks = list(e.generate_response_stream("Hi"))
        assert any("fallback" in c.lower() for c in chunks)

    def test_fallback_when_no_key(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="")
        chunks = list(e.generate_response_stream("Hi"))
        assert chunks


# ---------------------------------------------------------------------------
# generate_response_stream — success path
# ---------------------------------------------------------------------------


class TestGenerateResponseStreamSuccess:
    def test_yields_chunks(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        chunks = list(e.generate_response_stream("Good morning"))
        assert chunks == ["Hello", " there"]

    def test_history_updated_after_stream(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        list(e.generate_response_stream("Good morning"))
        assert len(e.history) == 2
        assert e.history[1]["content"] == "Hello there"

    def test_thinking_param_in_stream_call(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="real-key")
        list(e.generate_response_stream("Hi"))
        client = e._get_client()
        kwargs = client.messages.last_call_kwargs
        assert kwargs.get("thinking") == {"type": "adaptive"}


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------


class TestAppendHistory:
    def test_appends_two_entries(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        e._append_history("Q", "A")
        assert len(e.history) == 2

    def test_truncates_at_max(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        for i in range(10):
            e._append_history(f"Q{i}", f"A{i}")
        assert len(e.history) == e.max_history_turns * 2

    def test_keeps_most_recent_on_truncate(self, engine_mod):
        e = engine_mod.AnthropicConversationEngine(api_key="k")
        for i in range(10):
            e._append_history(f"Q{i}", f"A{i}")
        assert e.history[-1]["content"] == "A9"


# ---------------------------------------------------------------------------
# Static fallback message
# ---------------------------------------------------------------------------


class TestStaticFallback:
    def test_includes_user_text(self, engine_mod):
        msg = engine_mod.AnthropicConversationEngine._fallback_response("Hello", "guide")
        assert "Hello" in msg

    def test_includes_personality(self, engine_mod):
        msg = engine_mod.AnthropicConversationEngine._fallback_response("Hi", "coach")
        assert "coach" in msg
