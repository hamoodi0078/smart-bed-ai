from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Iterator

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from core.http_client import http

try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic = None  # type: ignore[assignment]
    _ANTHROPIC_AVAILABLE = False

# Transient Anthropic errors that warrant an automatic retry.
_ANTHROPIC_TRANSIENT: tuple[type[BaseException], ...] = ()
if _ANTHROPIC_AVAILABLE and _anthropic is not None:
    try:
        _ANTHROPIC_TRANSIENT = (
            _anthropic.RateLimitError,
            _anthropic.APIConnectionError,
            _anthropic.APITimeoutError,
            _anthropic.InternalServerError,
        )
    except AttributeError:
        pass

# Shared tenacity policy: up to 3 attempts, exponential backoff 1 → 2 → 4 s.
_AI_RETRY_KWARGS = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)

try:
    import litellm as _litellm
    _LITELLM_AVAILABLE = True
except ImportError:
    _litellm = None  # type: ignore[assignment]
    _LITELLM_AVAILABLE = False

try:
    from langchain_core.messages import (
        AIMessage as _AIMessage,
        BaseMessage as _BaseMessage,
        HumanMessage as _HumanMessage,
        SystemMessage as _SystemMessage,
    )
    from langchain_core.output_parsers import StrOutputParser as _StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate as _ChatPromptTemplate
    _LANGCHAIN_CORE_AVAILABLE = True
    _str_parser = _StrOutputParser()
except ImportError:
    _LANGCHAIN_CORE_AVAILABLE = False
    _str_parser = None  # type: ignore[assignment]


# ── Token budget helpers ──────────────────────────────────────────────────────
# Claude's context window is 200K tokens.  We leave a 40K buffer for the
# system prompt + response, so history is pruned when it grows past 160K.
_HISTORY_TOKEN_BUDGET = 160_000


def _estimate_tokens(text: str) -> int:
    """Fast approximation: ~4 chars per token (slightly conservative)."""
    return max(1, len(str(text or "")) // 4)


def _trim_history_to_budget(history: list[dict]) -> list[dict]:
    """Remove oldest message pairs until the history fits within _HISTORY_TOKEN_BUDGET.

    Always removes in user/assistant pairs (oldest pair first) to preserve
    conversational coherence.
    """
    while len(history) >= 2:
        total = sum(_estimate_tokens(m.get("content", "")) for m in history)
        if total <= _HISTORY_TOKEN_BUDGET:
            break
        history = history[2:]  # drop oldest user+assistant pair
    return history


SYSTEM_PROMPTS = {
    "therapist": (
        "You are a calm, professional therapeutic conversation partner. "
        "Your style is emotionally attuned, practical, and deeply human-sounding. "
        "Start by reflecting the user's feeling in one short sentence using their own wording when possible, then give one practical next step. "
        "Use micro-structure when useful: validate -> clarify -> action step. "
        "Avoid robotic phrasing, cliches, and template empathy lines unless truly fitting. "
        "Do not describe yourself as an AI, model, or assistant unless user explicitly asks. "
        "Keep default replies to 1-3 short lines, unless the user asks for depth. "
        "Use one brief follow-up question only when it meaningfully improves progress."
    ),
    "coach": (
        "You are a high-performance coach with professional communication. "
        "Turn problems into clear action: outcome -> next 1-2 steps -> accountability check. "
        "Sound direct, motivating, realistic, and conversational. "
        "Do not sound like a scripted bot and do not use repetitive catchphrases. "
        "Keep responses concise in 1-3 short lines, unless user asks for a plan or details. "
        "Use concrete wording, deadlines, and simple metrics when relevant. "
        "Use one short action-focused question only when helpful."
    ),
    "guide": (
        "You are a professional guide and educator focused on clarity and confidence. "
        "Explain in a simple, human way with minimal jargon and natural rhythm. "
        "Avoid textbook tone and avoid sounding scripted. "
        "Use structure when useful: quick answer -> why it matters -> what to do next. "
        "Keep default replies to 1-3 short lines, unless user asks for detail. "
        "Use one brief follow-up question only when it helps understanding."
    ),
}

HUMAN_ENGAGEMENT_INSTRUCTION = (
    "Human engagement rule: Write like a warm real conversation partner, not a generic assistant. "
    "Prefer specific language tied to the user's exact message. "
    "Vary openings so responses do not feel repetitive. "
    "Avoid generic reassurance lines that could fit anyone. "
    "When user shares emotion, reflect one specific phrase from their words, then one concrete next step. "
    "For 'teach/explain/tell me about' requests, include one vivid practical example in the first reply."
)


def _cognitive_load_instruction(mode: str) -> str:
    state = str(mode or "normal").strip().lower()
    if state == "exhausted":
        return (
            "Cognitive load mode: exhausted. Keep reply 60-70% shorter than your default. "
            "Use only essential comfort, one guidance step, and no extra branching."
        )
    if state == "reduced":
        return (
            "Cognitive load mode: reduced. Keep response concise and low-friction. "
            "Prefer one key point and one practical next step."
        )
    return ""

MOOD_LAYERS = {
    "distressed": (
        "Mood layer: user is distressed. Keep voice softer, validate first, and avoid performance pressure. "
        "Use one stabilizing next step before any broader advice."
    ),
    "low_energy": (
        "Mood layer: user energy is low. Keep sentences short, lower cognitive load, and offer one tiny action."
    ),
    "motivated": (
        "Mood layer: user is motivated. Keep momentum with concise and concrete action language."
    ),
    "dream_negative": (
        "Mood layer: user may be emotionally fragile after a negative dream. Prioritize calm reassurance and safety."
    ),
    "dream_positive": (
        "Mood layer: user has positive affect. Keep warmth and support momentum gently."
    ),
}


def _build_temporal_grounding_message() -> str:
    now_local = datetime.now()
    now_utc = datetime.now(timezone.utc)
    return (
        "Temporal grounding requirement: Use runtime date/time from this message for any time-sensitive answer. "
        "If user asks current year/date/day/time, do not infer from training data. "
        f"Local runtime datetime={now_local.isoformat(timespec='seconds')}; "
        f"UTC runtime datetime={now_utc.isoformat(timespec='seconds')}; "
        f"Current local year={now_local.year}."
    )

PERSONA_METHOD_PACKS = {
    "therapist": (
        "Therapist method pack: Use brief CBT-style support. "
        "Help user name thought patterns, test one belief, and pick one grounding or sleep-regulation action. "
        "For distress: use validate -> regulate -> next safe step."
    ),
    "coach": (
        "Coach method pack: Use sprint coaching. "
        "Define one measurable outcome, identify one obstacle, pick one next action, and confirm commitment timing."
    ),
    "guide": (
        "Guide method pack: Use teaching loop. "
        "Give a simple answer, one practical example, then one check-for-understanding question."
    ),
}

SESSION_ARC_INSTRUCTION = (
    "Session arc requirement for real-world problems: "
    "1) align on goal, 2) provide focused intervention, 3) recap key point, 4) ask for commitment/next step. "
    "Keep this lightweight and natural in short replies."
)


class ConversationEngine:
    def __init__(
        self,
        api_key: str,
        model: str = "voice-agent-conversational",
        timeout_seconds: int = 20,
        voice_agent_url: str = "https://agent.deepgram.com/v1/agent/converse",
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.voice_agent_url = voice_agent_url
        self.max_history_turns = 6
        self.history = []

    @staticmethod
    def _extract_text_from_response(payload: dict) -> str:
        if not isinstance(payload, dict):
            return ""

        output = payload.get("output")
        if isinstance(output, dict):
            text = str(output.get("text", "") or "").strip()
            if text:
                return text

        response_text = str(payload.get("response", "") or "").strip()
        if response_text:
            return response_text

        message = payload.get("message")
        if isinstance(message, dict):
            content = str(message.get("content", "") or "").strip()
            if content:
                return content

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") if isinstance(first, dict) else {}
            if isinstance(message, dict):
                content = str(message.get("content", "") or "").strip()
                if content:
                    return content

        results = payload.get("results")
        if isinstance(results, list) and results:
            first = results[0] if isinstance(results[0], dict) else {}
            content = str(first.get("content", "") or "").strip()
            if content:
                return content

        return ""

    def _build_voice_agent_payload(
        self,
        *,
        user_text: str,
        personality: str,
        realtime_context: str,
        user_context: str,
        emotion_state: str,
        cognitive_load_mode: str,
        max_response_tokens: int,
        stream: bool,
    ) -> dict:
        conversation_messages = self._build_messages(
            user_text=user_text,
            personality=personality,
            realtime_context=realtime_context,
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
        )
        return {
            "model": self.model,
            "stream": bool(stream),
            "max_output_tokens": max(40, int(max_response_tokens)),
            "messages": conversation_messages,
            "context": {
                "personality": personality,
                "emotion_state": str(emotion_state or "neutral"),
                "cognitive_load_mode": str(cognitive_load_mode or "normal"),
                "has_realtime_context": bool(str(realtime_context or "").strip()),
                "has_user_context": bool(str(user_context or "").strip()),
            },
        }

    def _build_messages(
        self,
        user_text: str,
        personality: str,
        realtime_context: str,
        user_context: str,
        emotion_state: str = "neutral",
        cognitive_load_mode: str = "normal",
    ) -> list[dict]:
        personality = personality.lower().strip()
        system_prompt = SYSTEM_PROMPTS.get(personality, SYSTEM_PROMPTS["guide"])

        conversation_messages = [{"role": "system", "content": system_prompt}]
        conversation_messages.append(
            {"role": "system", "content": _build_temporal_grounding_message()}
        )
        conversation_messages.append({"role": "system", "content": HUMAN_ENGAGEMENT_INSTRUCTION})
        method_pack = PERSONA_METHOD_PACKS.get(personality)
        if method_pack:
            conversation_messages.append({"role": "system", "content": method_pack})
        conversation_messages.append({"role": "system", "content": SESSION_ARC_INSTRUCTION})

        mood_key = str(emotion_state or "neutral").strip().lower()
        mood_layer = MOOD_LAYERS.get(mood_key)
        if mood_layer:
            conversation_messages.append({"role": "system", "content": mood_layer})
        load_instruction = _cognitive_load_instruction(cognitive_load_mode)
        if load_instruction:
            conversation_messages.append({"role": "system", "content": load_instruction})

        if user_context.strip():
            conversation_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Personalization context (follow this for tone and format when helpful):\n"
                        f"{user_context.strip()}"
                    ),
                }
            )
        if realtime_context.strip():
            conversation_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Use this live context when relevant to answer accurately. "
                        "If context conflicts with prior knowledge, prefer this context:\n"
                        f"{realtime_context.strip()}"
                    ),
                }
            )
        conversation_messages.extend(self.history)
        conversation_messages.append({"role": "user", "content": user_text})
        return conversation_messages

    def generate_response(
        self,
        user_text: str,
        personality: str = "therapist",
        realtime_context: str = "",
        user_context: str = "",
        emotion_state: str = "neutral",
        cognitive_load_mode: str = "normal",
        quick_timeout_seconds: int = 4,
        total_timeout_seconds: int = 10,
        max_response_tokens: int = 120,
    ) -> str:
        personality = personality.lower().strip()

        if not self.api_key:
            return self._fallback_response(user_text, personality)

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_voice_agent_payload(
            user_text=user_text,
            personality=personality,
            realtime_context=realtime_context,
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
            max_response_tokens=max_response_tokens,
            stream=False,
        )

        timeouts = [
            max(1, int(quick_timeout_seconds)),
            max(max(1, int(quick_timeout_seconds)), int(total_timeout_seconds)),
        ]

        for timeout_seconds in timeouts:
            try:
                response = http.post(
                    self.voice_agent_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                assistant_text = self._extract_text_from_response(data)
                if not assistant_text:
                    continue
                self._append_history(user_text, assistant_text)
                return assistant_text
            except Exception:
                continue

        return self._fallback_response(user_text, personality)

    def _append_history(self, user_text: str, assistant_text: str):
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        max_messages = self.max_history_turns * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]
        self.history = _trim_history_to_budget(self.history)

    def generate_response_stream(
        self,
        user_text: str,
        personality: str = "therapist",
        realtime_context: str = "",
        user_context: str = "",
        emotion_state: str = "neutral",
        cognitive_load_mode: str = "normal",
        total_timeout_seconds: int = 15,
        max_response_tokens: int = 140,
    ):
        personality = personality.lower().strip()
        if not self.api_key:
            yield self._fallback_response(user_text, personality)
            return

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_voice_agent_payload(
            user_text=user_text,
            personality=personality,
            realtime_context=realtime_context,
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
            max_response_tokens=max_response_tokens,
            stream=True,
        )

        collected = []
        try:
            with http.stream(
                "POST",
                self.voice_agent_url,
                headers=headers,
                json=payload,
                timeout=max(4, int(total_timeout_seconds)),
            ) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    line = str(raw_line).strip()
                    if not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        event = json.loads(data_str)
                    except Exception:
                        continue

                    chunk = ""
                    event_type = str(event.get("type", "") or "").strip().lower()
                    if event_type in ("content.delta", "response.output_text.delta", "delta"):
                        chunk = str(
                            event.get("delta")
                            or event.get("text")
                            or event.get("content")
                            or ""
                        )
                    else:
                        choices = event.get("choices") or []
                        if choices and isinstance(choices[0], dict):
                            delta = choices[0].get("delta") or {}
                            chunk = str(delta.get("content", "") or "")
                        if not chunk:
                            chunk = str(
                                event.get("delta")
                                or event.get("text")
                                or event.get("content")
                                or ""
                            )
                    if not chunk:
                        continue
                    collected.append(chunk)
                    yield chunk
        except Exception:
            fallback = self._fallback_response(user_text, personality)
            if not collected:
                yield fallback
            return

        assistant_text = "".join(collected).strip()
        if assistant_text:
            self._append_history(user_text, assistant_text)

    @staticmethod
    def _fallback_response(user_text: str, personality: str) -> str:
        return (
            f"(Deepgram fallback - {personality}) I heard: '{user_text}'. "
            "I can respond better once Deepgram Voice Agent access is available."
        )


class AnthropicConversationEngine:
    """Claude-powered conversation engine using the Anthropic SDK.

    Uses claude-opus-4-7 with adaptive thinking and prompt caching so the
    stable persona block is re-used across calls without re-tokenising.

    Falls back to a canned message when the ``anthropic`` package is absent
    or no API key is provided.
    """

    DEFAULT_MODEL = "claude-opus-4-7"

    def __init__(
        self,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = 20,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        self._model = str(model or self.DEFAULT_MODEL).strip()
        self._timeout_seconds = int(timeout_seconds)
        self._client: Any = None
        self.max_history_turns = 6
        self.history: list[dict] = []

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        if not _ANTHROPIC_AVAILABLE or not self._api_key:
            return None
        if self._client is None:
            self._client = _anthropic.Anthropic(
                api_key=self._api_key,
                timeout=float(self._timeout_seconds),
            )
        return self._client

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_system_blocks(
        self,
        personality: str,
        user_context: str,
        emotion_state: str,
        cognitive_load_mode: str,
    ) -> list[dict]:
        """Return system as content blocks; the stable persona block is cached."""
        p = personality.lower().strip()
        persona_text = SYSTEM_PROMPTS.get(p, SYSTEM_PROMPTS["guide"])
        method_pack = PERSONA_METHOD_PACKS.get(p, "")

        stable_parts = [persona_text, HUMAN_ENGAGEMENT_INSTRUCTION]
        if method_pack:
            stable_parts.append(method_pack)
        stable_parts.append(SESSION_ARC_INSTRUCTION)

        blocks: list[dict] = [
            {
                "type": "text",
                "text": "\n\n".join(stable_parts),
                "cache_control": {"type": "ephemeral"},
            }
        ]

        volatile_parts = [_build_temporal_grounding_message()]

        mood_layer = MOOD_LAYERS.get(str(emotion_state or "neutral").strip().lower())
        if mood_layer:
            volatile_parts.append(mood_layer)

        load_instruction = _cognitive_load_instruction(cognitive_load_mode)
        if load_instruction:
            volatile_parts.append(load_instruction)

        if user_context.strip():
            volatile_parts.append(
                "Personalization context (follow this for tone and format when helpful):\n"
                + user_context.strip()
            )

        blocks.append({"type": "text", "text": "\n\n".join(volatile_parts)})
        return blocks

    def _build_messages(
        self,
        user_text: str,
        realtime_context: str = "",
    ) -> list[dict]:
        msgs: list[dict] = list(self.history)
        content = user_text
        if realtime_context.strip():
            content = f"[Live context: {realtime_context.strip()}]\n\n{user_text}"
        msgs.append({"role": "user", "content": content})
        return msgs

    # ------------------------------------------------------------------
    # Response generation
    # ------------------------------------------------------------------

    def generate_response(
        self,
        user_text: str,
        personality: str = "therapist",
        realtime_context: str = "",
        user_context: str = "",
        emotion_state: str = "neutral",
        cognitive_load_mode: str = "normal",
        quick_timeout_seconds: int = 4,
        total_timeout_seconds: int = 10,
        max_response_tokens: int = 120,
    ) -> str:
        personality = personality.lower().strip()
        client = self._get_client()
        if client is None:
            return self._fallback_response(user_text, personality)

        system_blocks = self._build_system_blocks(
            personality=personality,
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
        )
        messages = self._build_messages(user_text=user_text, realtime_context=realtime_context)

        @retry(
            retry=retry_if_exception(lambda e: isinstance(e, _ANTHROPIC_TRANSIENT)),
            **_AI_RETRY_KWARGS,
        )
        def _call() -> Any:
            return client.messages.create(
                model=self._model,
                max_tokens=max(512, int(max_response_tokens)),
                system=system_blocks,
                messages=messages,
                thinking={"type": "adaptive"},
            )

        try:
            response = _call()
            text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            if text:
                self._append_history(user_text, text)
                return text
        except Exception as exc:
            logger.debug("AnthropicConversationEngine.generate_response error: {}", exc)

        return self._fallback_response(user_text, personality)

    def generate_response_stream(
        self,
        user_text: str,
        personality: str = "therapist",
        realtime_context: str = "",
        user_context: str = "",
        emotion_state: str = "neutral",
        cognitive_load_mode: str = "normal",
        total_timeout_seconds: int = 15,
        max_response_tokens: int = 140,
    ) -> Iterator[str]:
        personality = personality.lower().strip()
        client = self._get_client()
        if client is None:
            yield self._fallback_response(user_text, personality)
            return

        collected: list[str] = []
        try:
            with client.messages.stream(
                model=self._model,
                max_tokens=max(512, int(max_response_tokens)),
                system=self._build_system_blocks(
                    personality=personality,
                    user_context=user_context,
                    emotion_state=emotion_state,
                    cognitive_load_mode=cognitive_load_mode,
                ),
                messages=self._build_messages(
                    user_text=user_text,
                    realtime_context=realtime_context,
                ),
                thinking={"type": "adaptive"},
            ) as stream:
                for chunk in stream.text_stream:
                    if chunk:
                        collected.append(chunk)
                        yield chunk
        except Exception as exc:
            logger.debug(
                "AnthropicConversationEngine.generate_response_stream error: {}", exc
            )
            if not collected:
                yield self._fallback_response(user_text, personality)
            return

        assistant_text = "".join(collected).strip()
        if assistant_text:
            self._append_history(user_text, assistant_text)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _append_history(self, user_text: str, assistant_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        max_msgs = self.max_history_turns * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]
        self.history = _trim_history_to_budget(self.history)

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_response(user_text: str, personality: str) -> str:
        return (
            f"(Claude fallback - {personality}) I heard: '{user_text}'. "
            "I can respond better once ANTHROPIC_API_KEY is configured."
        )


class LiteLLMConversationEngine:
    """Universal conversation engine backed by litellm.

    Routes to any provider supported by litellm (Anthropic, OpenAI, Gemini,
    Ollama, …) using a single ``provider/model`` string.  API keys are read
    from the environment (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, …) or
    passed explicitly via *api_key*.

    Uses the same system-prompt architecture as the other engines — persona,
    temporal grounding, mood layers, cognitive-load adjustments — but combines
    everything into one ``system`` message so it works with every provider.

    Parameters
    ----------
    model:
        LiteLLM model string, e.g. ``"anthropic/claude-opus-4-7"``,
        ``"gpt-4o"``, ``"gemini/gemini-1.5-pro"``, ``"ollama/llama3"``.
    api_key:
        Optional explicit API key — overrides the environment variable for
        the chosen provider.
    timeout_seconds:
        Request timeout forwarded to litellm.
    """

    DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str = "",
        timeout_seconds: int = 20,
        temperature: float = 0.7,
        num_retries: int = 2,
    ) -> None:
        self._model = str(model or self.DEFAULT_MODEL).strip()
        self._api_key = str(api_key or "").strip() or None
        self._timeout_seconds = int(timeout_seconds)
        self._temperature = max(0.0, min(2.0, float(temperature)))
        self._num_retries = max(0, int(num_retries))
        self.max_history_turns = 6
        # History stored as typed langchain-core messages when available,
        # falling back to raw dicts for providers that skip langchain-core.
        self.history: list[Any] = []

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(msg: Any) -> dict:
        """Convert a langchain-core BaseMessage (or plain dict) to a litellm dict."""
        if isinstance(msg, dict):
            return msg
        if _LANGCHAIN_CORE_AVAILABLE and isinstance(msg, _BaseMessage):
            role_map = {"human": "user", "ai": "assistant", "system": "system"}
            return {"role": role_map.get(msg.type, msg.type), "content": str(msg.content)}
        return {"role": "user", "content": str(msg)}

    def _messages_to_dicts(self, msgs: list[Any]) -> list[dict]:
        return [self._to_dict(m) for m in msgs]

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_system_text(
        self,
        personality: str,
        user_context: str,
        emotion_state: str,
        cognitive_load_mode: str,
    ) -> str:
        """Assemble all system-prompt layers into a single text block."""
        p = personality.lower().strip()

        if _LANGCHAIN_CORE_AVAILABLE:
            # Use ChatPromptTemplate for the stable persona+engagement block.
            persona_template = _ChatPromptTemplate.from_messages([
                ("system", "{persona}\n\n{engagement}\n\n{method_pack}\n\n{session_arc}"),
            ])
            method_pack = PERSONA_METHOD_PACKS.get(p, "")
            base_block = persona_template.format_messages(
                persona=SYSTEM_PROMPTS.get(p, SYSTEM_PROMPTS["guide"]),
                engagement=HUMAN_ENGAGEMENT_INSTRUCTION,
                method_pack=method_pack,
                session_arc=SESSION_ARC_INSTRUCTION,
            )[0].content
            parts = [base_block, _build_temporal_grounding_message()]
        else:
            parts = [SYSTEM_PROMPTS.get(p, SYSTEM_PROMPTS["guide"])]
            parts.append(_build_temporal_grounding_message())
            parts.append(HUMAN_ENGAGEMENT_INSTRUCTION)
            method_pack_text = PERSONA_METHOD_PACKS.get(p)
            if method_pack_text:
                parts.append(method_pack_text)
            parts.append(SESSION_ARC_INSTRUCTION)

        mood_layer = MOOD_LAYERS.get(str(emotion_state or "neutral").strip().lower())
        if mood_layer:
            parts.append(mood_layer)

        load_instruction = _cognitive_load_instruction(cognitive_load_mode)
        if load_instruction:
            parts.append(load_instruction)

        if user_context.strip():
            parts.append(
                "Personalization context (follow this for tone and format when helpful):\n"
                + user_context.strip()
            )
        return "\n\n".join(parts)

    def _build_messages(
        self,
        user_text: str,
        personality: str,
        realtime_context: str,
        user_context: str,
        emotion_state: str,
        cognitive_load_mode: str,
    ) -> list[dict]:
        system_text = self._build_system_text(
            personality=personality,
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
        )
        content = user_text
        if realtime_context.strip():
            content = f"[Live context: {realtime_context.strip()}]\n\n{user_text}"

        if _LANGCHAIN_CORE_AVAILABLE:
            lc_msgs: list[Any] = [_SystemMessage(content=system_text)]
            lc_msgs.extend(self.history)
            lc_msgs.append(_HumanMessage(content=content))
            return self._messages_to_dicts(lc_msgs)

        msgs: list[dict] = [{"role": "system", "content": system_text}]
        msgs.extend(self.history)  # type: ignore[arg-type]
        msgs.append({"role": "user", "content": content})
        return msgs

    # ------------------------------------------------------------------
    # Response generation
    # ------------------------------------------------------------------

    def generate_response(
        self,
        user_text: str,
        personality: str = "therapist",
        realtime_context: str = "",
        user_context: str = "",
        emotion_state: str = "neutral",
        cognitive_load_mode: str = "normal",
        quick_timeout_seconds: int = 4,
        total_timeout_seconds: int = 10,
        max_response_tokens: int = 120,
    ) -> str:
        personality = personality.lower().strip()
        if not _LITELLM_AVAILABLE:
            return self._fallback_response(user_text, personality)

        messages = self._build_messages(
            user_text=user_text,
            personality=personality,
            realtime_context=realtime_context,
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
        )
        extra = {"api_key": self._api_key} if self._api_key else {}

        @retry(
            retry=retry_if_exception(
                lambda e: isinstance(e, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError))
            ),
            **_AI_RETRY_KWARGS,
        )
        def _call() -> Any:
            return _litellm.completion(
                model=self._model,
                messages=messages,
                max_tokens=max(40, int(max_response_tokens)),
                temperature=self._temperature,
                timeout=self._timeout_seconds,
                num_retries=self._num_retries,
                drop_params=True,
                **extra,
            )

        try:
            response = _call()
            raw = str(
                (response.choices[0].message.content or "") if response.choices else ""
            ).strip()
            text = _str_parser.parse(raw) if _LANGCHAIN_CORE_AVAILABLE and _str_parser else raw
            if text:
                self._append_history(user_text, text)
                return text
        except Exception as exc:
            logger.debug("LiteLLMConversationEngine.generate_response error: {}", exc)

        return self._fallback_response(user_text, personality)

    def generate_response_stream(
        self,
        user_text: str,
        personality: str = "therapist",
        realtime_context: str = "",
        user_context: str = "",
        emotion_state: str = "neutral",
        cognitive_load_mode: str = "normal",
        total_timeout_seconds: int = 15,
        max_response_tokens: int = 140,
    ) -> Iterator[str]:
        personality = personality.lower().strip()
        if not _LITELLM_AVAILABLE:
            yield self._fallback_response(user_text, personality)
            return

        messages = self._build_messages(
            user_text=user_text,
            personality=personality,
            realtime_context=realtime_context,
            user_context=user_context,
            emotion_state=emotion_state,
            cognitive_load_mode=cognitive_load_mode,
        )
        collected: list[str] = []
        try:
            stream = _litellm.completion(
                model=self._model,
                messages=messages,
                stream=True,
                max_tokens=max(40, int(max_response_tokens)),
                temperature=self._temperature,
                timeout=self._timeout_seconds,
                num_retries=self._num_retries,
                drop_params=True,
                **({"api_key": self._api_key} if self._api_key else {}),
            )
            for chunk in stream:
                delta = ""
                if chunk.choices:
                    delta = str(chunk.choices[0].delta.content or "")
                if delta:
                    collected.append(delta)
                    yield delta
        except Exception as exc:
            logger.debug(
                "LiteLLMConversationEngine.generate_response_stream error: {}", exc
            )
            if not collected:
                yield self._fallback_response(user_text, personality)
            return

        assistant_text = "".join(collected).strip()
        if assistant_text:
            self._append_history(user_text, assistant_text)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _append_history(self, user_text: str, assistant_text: str) -> None:
        if _LANGCHAIN_CORE_AVAILABLE:
            self.history.append(_HumanMessage(content=user_text))
            self.history.append(_AIMessage(content=assistant_text))
        else:
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": assistant_text})
        max_msgs = self.max_history_turns * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]
        # Normalize to dicts for token counting, then convert back if needed
        dict_history = self._messages_to_dicts(self.history) if _LANGCHAIN_CORE_AVAILABLE else list(self.history)
        dict_history = _trim_history_to_budget(dict_history)
        if _LANGCHAIN_CORE_AVAILABLE and len(dict_history) < len(self.history):
            self.history = self.history[len(self.history) - len(dict_history):]
        elif not _LANGCHAIN_CORE_AVAILABLE:
            self.history = dict_history

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_response(user_text: str, personality: str) -> str:
        return (
            f"(LiteLLM fallback - {personality}) I heard: '{user_text}'. "
            "I can respond better once litellm is installed and a provider key is set."
        )
