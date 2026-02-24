from datetime import datetime, timezone
import json

import requests


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
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout_seconds: int = 20):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_history_turns = 6
        self.history = []

    def _build_messages(
        self,
        user_text: str,
        personality: str,
        realtime_context: str,
        user_context: str,
        emotion_state: str = "neutral",
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
        quick_timeout_seconds: int = 4,
        total_timeout_seconds: int = 10,
        max_response_tokens: int = 120,
    ) -> str:
        personality = personality.lower().strip()

        if not self.api_key:
            return self._fallback_response(user_text, personality)

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        conversation_messages = self._build_messages(
            user_text=user_text,
            personality=personality,
            realtime_context=realtime_context,
            user_context=user_context,
            emotion_state=emotion_state,
        )

        payload = {
            "model": self.model,
            "temperature": 0.6,
            "max_tokens": max(40, int(max_response_tokens)),
            "messages": conversation_messages,
        }

        timeouts = [
            max(1, int(quick_timeout_seconds)),
            max(max(1, int(quick_timeout_seconds)), int(total_timeout_seconds)),
        ]

        for timeout_seconds in timeouts:
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                assistant_text = data["choices"][0]["message"]["content"].strip()
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

    def generate_response_stream(
        self,
        user_text: str,
        personality: str = "therapist",
        realtime_context: str = "",
        user_context: str = "",
        emotion_state: str = "neutral",
        total_timeout_seconds: int = 15,
        max_response_tokens: int = 140,
    ):
        personality = personality.lower().strip()
        if not self.api_key:
            yield self._fallback_response(user_text, personality)
            return

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0.6,
            "max_tokens": max(40, int(max_response_tokens)),
            "stream": True,
            "messages": self._build_messages(
                user_text=user_text,
                personality=personality,
                realtime_context=realtime_context,
                user_context=user_context,
                emotion_state=emotion_state,
            ),
        }

        collected = []
        try:
            with requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=max(4, int(total_timeout_seconds)),
                stream=True,
            ) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines(decode_unicode=True):
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

                    choices = event.get("choices") or []
                    if not choices:
                        continue

                    delta = choices[0].get("delta") or {}
                    chunk = str(delta.get("content", "") or "")
                    if not chunk:
                        continue
                    collected.append(chunk)
                    yield chunk
        except Exception:
            yield self._fallback_response(user_text, personality)
            return

        assistant_text = "".join(collected).strip()
        if assistant_text:
            self._append_history(user_text, assistant_text)

    @staticmethod
    def _fallback_response(user_text: str, personality: str) -> str:
        return (
            f"(Offline fallback - {personality}) I heard: '{user_text}'. "
            "I can respond better once API access is available."
        )
