"""Thin launcher + shared utility functions imported by the test suite.

All module functionality is accessed via explicit imports in each file.
No global namespace pollution.
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv(override=True)
import re
from datetime import datetime, timedelta, timezone
from typing import Any


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------

def _run() -> None:
    from app_entry import main
    main()


if __name__ == "__main__":
    _run()


# ---------------------------------------------------------------------------
# Profile persistence (lazy import so tests can patch it)
# ---------------------------------------------------------------------------

def save_profile(profile: dict) -> None:
    try:
        from Storage.user_profile import save_profile as _save
        _save(profile)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_DETAIL_TRIGGERS = [
    "tell me about", "tell me more", "walk me through", "explain in detail",
    "explain to me", "give me a full", "deep dive", "break it down",
    "elaborate on", "describe in detail", "step by step",
]


def wants_detailed_answer(text: str) -> bool:
    """Return True when the user explicitly asks for a detailed response."""
    t = text.lower().strip()
    return any(trigger in t for trigger in _DETAIL_TRIGGERS)


def clamp_non_detail_response(
    text: str,
    detailed_mode: bool,
    response_style: str = "balanced",
) -> str:
    """Trim a response to a shorter length when detailed_mode is False.

    Respects sentence boundaries and avoids cutting mid-sentence or after a
    numbered-list marker (e.g. "1.").
    """
    if detailed_mode:
        return text

    # Tokenise into sentences at sentence-ending punctuation
    raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences: list[str] = []
    for s in raw_sentences:
        s = s.strip()
        if s:
            sentences.append(s)

    if not sentences:
        return text

    # Keep sentences until we exceed the char limit, but never cut after "N."
    char_limit = 160 if response_style == "balanced" else 120
    kept: list[str] = []
    total = 0
    for s in sentences:
        # Never stop right after a numbered-list marker like "ones: 1."
        if kept and re.search(r"\d+\.$", kept[-1]):
            kept.append(s)
            total += len(s)
            continue
        if total + len(s) > char_limit and kept:
            break
        kept.append(s)
        total += len(s)

    if not kept:
        kept = [sentences[0]]

    result = " ".join(kept)

    # If we only have one very long sentence with no natural break, add ellipsis
    if len(kept) == 1 and len(result) > char_limit and not re.search(r"[.!?]$", result):
        words = result.split()
        result = " ".join(words[:30]) + "..."

    return result


# ---------------------------------------------------------------------------
# Fast TTS start helpers
# ---------------------------------------------------------------------------

def _split_for_fast_tts_start(
    text: str,
    head_limit_chars: int = 100,
) -> tuple[str, str]:
    """Split text into (head, tail) for low-latency TTS streaming.

    The head is the first chunk that ends on a sentence boundary near
    *head_limit_chars*.  If the text is short enough to fit in the head,
    tail is empty.
    """
    if len(text) <= head_limit_chars:
        return text, ""

    # Find the last sentence-ending punctuation before the limit
    search_region = text[:head_limit_chars + 40]
    matches = list(re.finditer(r"[.!?](?:\s|$)", search_region))
    if matches:
        cut = matches[-1].end()
        head = text[:cut].rstrip()
        tail = text[cut:].lstrip()
        if tail:
            return head, tail

    # Fall back: cut at a word boundary
    cut = text[:head_limit_chars].rfind(" ")
    if cut == -1:
        cut = head_limit_chars
    return text[:cut], text[cut:].lstrip()


def play_tts_with_fast_start(
    tts: Any,
    player: Any,
    text: str,
    voice_override: str = "",
    pace_override: float = 1.0,
) -> str:
    """Synthesize the head chunk, play it immediately, then queue the tail.

    Returns the file path of the first (head) audio file.
    """
    head, tail = _split_for_fast_tts_start(text)

    if not tail:
        path = tts.synthesize_to_mp3(
            text,
            filename="latest_response.mp3",
            voice_override=voice_override,
            pace_override=pace_override,
        )
        player.play_file(path)
        return path

    head_path = tts.synthesize_to_mp3(
        head,
        filename="latest_response_head.mp3",
        voice_override=voice_override,
        pace_override=pace_override,
    )
    tail_path = tts.synthesize_to_mp3(
        tail,
        filename="latest_response_tail.mp3",
        voice_override=voice_override,
        pace_override=pace_override,
    )
    player.play_file(head_path)
    player.queue_file(tail_path)
    return head_path


# ---------------------------------------------------------------------------
# Listening / confidence helpers
# ---------------------------------------------------------------------------

_SCENE_CLARIFICATION_KEYWORDS = {
    "brightness", "bright", "dim", "dimmer", "lighter", "darker",
    "lighting", "lights", "scene", "normal brightness", "keep it",
}

_SESSION_END_PHRASES = {
    "bye", "bye-bye", "goodbye", "good bye", "see you", "see ya",
    "ok bye", "ok bye-bye", "okay bye", "that's all", "thats all",
    "stop listening", "go to sleep", "exit",
}

_ECHO_MAX_OVERLAP_RATIO = 0.6


def _is_scene_clarification_candidate(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _SCENE_CLARIFICATION_KEYWORDS)


def _is_session_end_command(text: str) -> bool:
    t = text.lower().strip().rstrip(".,!?")
    return t in _SESSION_END_PHRASES or any(p in t for p in _SESSION_END_PHRASES)


def _is_simple_yes(text: str) -> bool:
    return text.lower().strip().startswith("yes")


def _is_wake_only_utterance(wake_manager: Any, text: str) -> bool:
    """Return True when the utterance contains only the wake word (+ trailing noise)."""
    t = text.lower().strip()
    noise_words = {"please", "ok", "okay", "um", "uh", "ah", "hey", "hi"}

    phrases: list[str] = []
    if hasattr(wake_manager, "wake_word") and wake_manager.wake_word:
        phrases.append(wake_manager.wake_word.lower())
    if hasattr(wake_manager, "wake_aliases"):
        for alias in wake_manager.wake_aliases or []:
            phrases.append(alias.lower())

    for phrase in phrases:
        if t == phrase:
            return True
        if t.startswith(phrase + " "):
            remainder = t[len(phrase):].strip()
            words = remainder.split()
            if all(w in noise_words for w in words):
                return True
    return False


def _looks_like_echo_capture(
    user_text: str,
    last_assistant: str,
    confidence: float,
) -> bool:
    """Detect when user_text is a replay of what the assistant last said."""
    if confidence > 0.85:
        return False
    ut = user_text.lower().strip()
    la = last_assistant.lower()
    # User text is a prefix/substring of the assistant's last response
    return len(ut) >= 8 and ut in la


def _is_llm_fallback_response(text: str) -> bool:
    """Return True for responses generated by any offline/fallback engine."""
    t = text.strip()
    fallback_prefixes = (
        "(deepgram fallback",
        "(offline fallback",
        "(claude fallback",
        "(litellm fallback",
        "(local fallback",
    )
    return t.lower().startswith(fallback_prefixes)


def _resolve_scene_clarification_followup(text: str) -> dict:
    """Map a lighting clarification phrase to a set_scene action."""
    t = text.lower().strip()
    if "normal brightness" in t or "keep" in t:
        return {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}}
    if "dim" in t or "darker" in t or "softer" in t:
        return {"intent": "set_scene", "slots": {"scene_key": "calm_recovery"}}
    if "bright" in t or "lighter" in t:
        return {"intent": "set_scene", "slots": {"scene_key": "focus_momentum"}}
    return {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}}


_CONFIDENCE_THRESHOLD = 0.58


def get_query_text(
    stt: Any,
    wake_manager: Any,
    require_api_stream: bool = False,
) -> tuple[str, float]:
    """Retrieve transcribed user text with confidence gating.

    Returns (text, confidence).  Returns ("", 0.0) when confidence is below
    the threshold.
    """
    if hasattr(wake_manager, "is_voice_available") and wake_manager.is_voice_available():
        if require_api_stream and hasattr(stt, "transcribe_microphone_with_interim"):
            mic_index = getattr(wake_manager, "get_active_mic_index", lambda: None)()
            timeout = getattr(wake_manager, "voice_timeout_seconds", 5)
            phrase_limit = (
                getattr(wake_manager, "get_voice_phrase_limit_seconds", lambda: None)() or None
            )
            text, conf = stt.transcribe_microphone_with_interim(
                mic_device_index=mic_index,
                timeout_seconds=timeout,
                max_phrase_seconds=phrase_limit or 16.0,
            )
            if not text and mic_index is not None:
                # Retry with default microphone
                text, conf = stt.transcribe_microphone_with_interim(
                    mic_device_index=None,
                    timeout_seconds=timeout,
                    max_phrase_seconds=phrase_limit or 16.0,
                )
            return (text, conf) if conf >= _CONFIDENCE_THRESHOLD else ("", 0.0)

        # Standard voice path
        text, conf = wake_manager.get_user_text_with_confidence()
        return (text, conf) if conf >= _CONFIDENCE_THRESHOLD else ("", 0.0)

    # Audio file path from stdin
    raw = input("audio_path> ").strip()
    path = raw[len("audio:"):] if raw.startswith("audio:") else raw
    text, conf = stt.transcribe_file_with_confidence(path)
    return (text, conf) if conf >= _CONFIDENCE_THRESHOLD else ("", 0.0)


# ---------------------------------------------------------------------------
# Bed intent / guide
# ---------------------------------------------------------------------------

_COLORS = {
    "red", "blue", "green", "yellow", "orange", "purple", "white",
    "pink", "warm", "cool", "cyan", "teal", "violet", "gold",
}


def detect_natural_bed_intent(text: str) -> tuple[str | None, dict]:
    """Parse a natural language phrase into a (intent, payload) pair."""
    t = text.lower().strip()

    # Bed guide triggers
    if any(p in t for p in ["how to use this bed", "how do i use", "guide me through", "bed guide"]):
        return "bed_guide_start", {}
    if any(p in t for p in ["next guide step", "next step guide", "guide next"]):
        return "bed_guide_next", {}

    # Get nickname — must come before set_nickname to avoid "what" being captured as nickname
    if re.search(r"what\s+(?:is|'s)\s+your\s+nick\s*name", t):
        return "get_bed_nickname", {}

    # Nickname: "jojo is your nick name"
    m = re.match(r"^(\w+)\s+is\s+your\s+nick\s*(?:name|names?)", t)
    if m:
        return "set_bed_nickname", {"nickname": m.group(1)}

    # Nickname: "jojo i would like to call you"
    m = re.match(r"^(\w+)\s+i\s+would\s+like\s+to\s+call\s+you", t)
    if m:
        return "set_bed_nickname", {"nickname": m.group(1)}

    # Nickname setup intent
    if re.search(r"(?:give|assign)\s+(?:u|you|ya)\s+a\s+nick\s*name", t):
        return "nickname_setup", {}

    # Color: "make it [color]"
    m = re.search(r"make\s+it\s+(\w+)", t)
    if m and m.group(1) in _COLORS:
        return "set_color", {"color": m.group(1)}

    # Brightness: "set lights to X% brightness" or "X% brightness"
    m = re.search(r"(\d+)\s*%", t)
    if m and ("brightness" in t or "lights" in t or "light" in t):
        return "brightness_set", {"brightness_percent": int(m.group(1))}

    return None, {}


def build_bed_guide_steps() -> list[str]:
    """Return the ordered bed guide steps."""
    return [
        "Welcome to your smart bed! I will walk you through the main features.",
        "Lighting control: say 'make it warm' or 'dim the lights' to adjust LED scenes.",
        "Sleep sounds: say 'play ambient sounds' or 'play calm music' to start audio.",
        "Wind-down mode: say 'start wind down' to begin a relaxing bedtime sequence.",
        "Alarm: say 'set alarm for 7 AM' and I will wake you gently at the right time.",
        "Daily check-in: I will ask how you slept and track your sleep quality over time.",
        "That is all for now. You can say 'bed guide start' anytime to revisit this tour.",
    ]


def render_bed_guide_step(index: int) -> str:
    """Render a single bed guide step with progress indicator."""
    steps = build_bed_guide_steps()
    if index >= len(steps):
        return "Bed guide completed. You are all set to use your smart bed!"
    total = len(steps)
    step_text = steps[index]
    hint = "Say 'next guide step' to continue." if index < total - 1 else "Say 'stop' to finish."
    return f"Bed guide {index + 1}/{total}: {step_text} {hint}"


def resolve_bed_guide_shortcut_intent(text: str) -> str | None:
    """Map a short phrase to a bed guide navigation intent."""
    t = text.lower().strip()
    if t in {"next", "next step", "continue", "go on", "proceed"}:
        return "bed_guide_next"
    if "next" in t and "step" in t:
        return "bed_guide_next"
    if t in {"repeat", "again", "كرر", "كررها", "مجددا"}:
        return "bed_guide_repeat"
    if t in {"stop", "quit", "exit", "cancel", "end guide", "stop guide"}:
        return "bed_guide_stop"
    return None


# ---------------------------------------------------------------------------
# Compound / followup control intent detection
# ---------------------------------------------------------------------------

_BRIGHTNESS_DOWN_PHRASES = {"a bit dimmer", "dimmer", "less bright", "darker", "lower brightness"}
_BRIGHTNESS_UP_PHRASES = {"a bit brighter", "brighter", "more bright", "lighter", "higher brightness"}
_PAUSE_PHRASES = {"pause it", "pause", "stop it", "stop music", "mute", "silence"}
_LIGHT_INTENTS = {"set_color", "set_scene", "brightness_set", "brightness_up", "brightness_down"}
_MUSIC_INTENTS = {"play_music", "start_music"}


def _resolve_followup_control_intent(text: str, profile: dict) -> tuple[str | None, dict]:
    """Resolve a shorthand command using the last action context from the profile."""
    t = text.lower().strip()
    last_intent = (
        profile.get("runtime_flags", {}).get("last_action", {}).get("intent") or ""
    ).lower()

    if last_intent in _LIGHT_INTENTS:
        if any(p in t for p in _BRIGHTNESS_DOWN_PHRASES):
            return "brightness_down", {}
        if any(p in t for p in _BRIGHTNESS_UP_PHRASES):
            return "brightness_up", {}

    if last_intent in _MUSIC_INTENTS:
        if any(p in t for p in _PAUSE_PHRASES):
            return "pause_music_followup", {}

    return None, {}


def _detect_compound_control_intents(text: str, profile: dict) -> list[dict]:
    """Parse a compound command (joined by 'and') into a list of intent dicts."""
    parts = [p.strip() for p in re.split(r"\band\b", text, flags=re.IGNORECASE) if p.strip()]
    results: list[dict] = []

    for part in parts:
        intent, slots = detect_natural_bed_intent(part)
        if intent:
            results.append({"intent": intent, "slots": slots})
            continue

        f_intent, f_slots = _resolve_followup_control_intent(part, profile)
        if f_intent:
            results.append({"intent": f_intent, "slots": f_slots})
            continue

        # Music keyword fallback
        if any(w in part.lower() for w in ("music", "play", "song", "track", "audio")):
            results.append({"intent": "play_music", "slots": {"query": part.strip()}})

    return results


# ---------------------------------------------------------------------------
# Wake word aliases + greeting
# ---------------------------------------------------------------------------

def _deduplicate_consecutive_chars(word: str) -> str:
    """Collapse consecutive duplicate characters: 'ishfaaq' → 'ishfaq'."""
    if not word:
        return word
    out = [word[0]]
    for ch in word[1:]:
        if ch != out[-1]:
            out.append(ch)
    return "".join(out)


def build_wake_aliases_from_profile(profile: dict) -> list[str]:
    """Return wake-phrase aliases derived from the bed nickname."""
    prefs = profile.get("preferences", {})
    nickname = str(prefs.get("bed_nickname") or "").strip()
    extra = list(prefs.get("wake_aliases") or [])

    aliases: list[str] = list(extra)
    if not nickname:
        return aliases

    deduped = _deduplicate_consecutive_chars(nickname)
    candidates = {nickname, deduped}
    for variant in list(candidates):
        candidates.add(f"hey {variant}")

    for alias in sorted(candidates):
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def build_wake_greeting(profile: dict) -> str:
    """Return a personalised wake greeting based on profile language and name."""
    name = str(profile.get("name") or "").strip()
    prefs = profile.get("preferences", {})
    lang = str(prefs.get("language") or "en").lower().strip()

    hour = datetime.now().hour
    if hour < 12:
        period = "morning"
    elif hour < 18:
        period = "afternoon"
    else:
        period = "evening"

    if lang == "ar":
        if name:
            return f"صباح الخير {name}! أنا هنا وجاهز للمساعدة. أنا في sleep mode."
        return "صباح الخير! أنا هنا وجاهز للمساعدة. أنا في sleep mode."

    if name:
        return f"Good {period}, {name}! I am in sleep mode and ready. How can I help?"
    return f"Good {period}! I am here and listening. I am in sleep mode and ready."


# ---------------------------------------------------------------------------
# Sleep help
# ---------------------------------------------------------------------------

def build_sleep_help() -> str:
    """Return a help text describing sleep-related voice commands."""
    return (
        "Sleep commands you can use:\n"
        "• 'sleep quality score' — see your personalised sleep quality score out of 100\n"
        "• 'bedtime drift alert' — check if your bedtimes are drifting later\n"
        "• 'start wind down' — begin a 45-minute relaxing wind-down sequence\n"
        "• 'set alarm for 7 AM' — set a gentle wake alarm\n"
        "• 'how did I sleep' — get last night's sleep summary\n"
        "• 'sleep tips' — get personalised tips to improve sleep quality\n"
    )


# ---------------------------------------------------------------------------
# Therapist follow-up system
# ---------------------------------------------------------------------------

_OPT_OUT_PHRASES = {
    "don't ask about this again", "stop asking", "i don't want to talk about it",
    "please do not ask", "do not ask", "stop following up", "drop it",
    "forget about it", "i don't want to discuss",
}

_ISLAMIC_TONE_WORDS = {"islamic", "quran", "dua", "allah", "prayer"}
_TEEN_TONE_WORDS = {"teen", "teenager", "teenage", "youth"}


def normalize_followup_tone(tone: str) -> str:
    """Map a free-form tone string to a canonical tone variant."""
    t = tone.lower().strip()
    if any(w in t for w in _ISLAMIC_TONE_WORDS):
        return "islamic"
    if any(w in t for w in _TEEN_TONE_WORDS):
        return "teen"
    if "professional" in t or "formal" in t:
        return "professional"
    return "soft"


def record_therapist_concern(
    profile: dict,
    user_text: str,
    personality: str,
    now: datetime | None = None,
) -> bool:
    """Record an emotional concern and schedule a follow-up for the next day."""
    if personality != "therapist":
        return False
    now = now or datetime.now()
    due = (now + timedelta(days=1)).date().isoformat()
    daily_life = profile.setdefault("daily_life", {})
    followups: list[dict] = daily_life.setdefault("emotional_followups", [])
    followups.append(
        {
            "concern": user_text,
            "recorded_at": now.isoformat(timespec="seconds"),
            "followup_due_date": due,
            "resolved": False,
        }
    )
    return True


def get_due_therapist_followup(
    profile: dict,
    personality: str,
    user_text: str,
    now: datetime | None = None,
) -> str:
    """Return a follow-up prompt if one is pending for today (once per day)."""
    if personality != "therapist":
        return ""

    now = now or datetime.now()
    today = now.date().isoformat()

    daily_life = profile.setdefault("daily_life", {})

    # Once-per-day guard
    if daily_life.get("last_followup_asked_date") == today:
        return ""

    # Find the first unresolved followup due today
    followups: list[dict] = daily_life.get("emotional_followups") or []
    pending = [
        f for f in followups
        if not f.get("resolved") and f.get("followup_due_date") == today
    ]
    if not pending:
        return ""

    concern = pending[0].get("concern", "")
    daily_life["last_followup_asked_date"] = today

    # Tone
    prefs = profile.get("preferences", {})
    raw_tone = str(prefs.get("therapist_followup_tone") or "soft")
    tone = normalize_followup_tone(raw_tone)

    if tone == "islamic":
        return (
            f"I hope you are well today. Yesterday you mentioned feeling: \"{concern}\". "
            "I wanted to check in — how are you feeling now? "
            "May Allah ease whatever you are going through."
        )
    if tone == "teen":
        return (
            f"Hey! Yesterday you mentioned: \"{concern}\". "
            "Just checking in — are you feeling better today?"
        )
    return (
        f"I noticed yesterday you mentioned: \"{concern}\". "
        "How are you feeling about that today?"
    )


def resolve_therapist_followup_if_answered(
    profile: dict,
    user_text: str,
    now: datetime | None = None,
) -> bool:
    """Mark the active follow-up as resolved; set opt-out if user declines."""
    now = now or datetime.now()
    today = now.date().isoformat()
    daily_life = profile.setdefault("daily_life", {})

    # Check if we asked today
    if daily_life.get("last_followup_asked_date") != today:
        return False

    t = user_text.lower().strip()
    opted_out = any(phrase in t for phrase in _OPT_OUT_PHRASES)

    followups: list[dict] = daily_life.get("emotional_followups") or []
    resolved_any = False
    for f in followups:
        if not f.get("resolved") and f.get("followup_due_date") == today:
            f["resolved"] = True
            resolved_any = True
            break

    if opted_out:
        daily_life["followup_opt_out"] = True

    return resolved_any or opted_out


# ---------------------------------------------------------------------------
# Local command handler
# ---------------------------------------------------------------------------

def handle_local_commands(
    user_text: str,
    profile: dict,
    led: Any,
    spotify: Any,
    local_music: Any,
    schedule: Any,
    goal_manager: Any,
    daily_life_support: Any,
    goal_compass: Any,
    sleep_engine: Any,
    environment_orchestrator: Any,
    runtime_orchestrator: Any,
    goal_strategy: Any,
    sleep_routine: Any,
    routine_engine: Any,
    tts_player: Any,
    audio_output: Any,
    backend_client: Any,
    health_report_builder: Any,
    on_sleep_timer_finish: Any,
    breathing_guide: Any,
    dream_journal: Any,
    adaptive_personality: Any,
    tts: Any,
    wake_word_manager: Any,
) -> tuple[str, bool]:
    """Handle local environment / control commands; return (response, handled)."""
    t = user_text.lower().strip()

    # Sleep room optimization
    if re.search(r"optimize\s+(?:my\s+)?(?:room\s+for\s+sleep|sleep\s+(?:room|environment))", t):
        scene = {
            "key": "sleep_optimized_room",
            "animation": "breathing",
            "color": "warm",
            "brightness": 0.2,
            "line": "Environment scene: sleep optimization.",
        }
        scene_line = environment_orchestrator.apply_scene(led, profile, scene)
        wind_down_minutes = profile.get("sleep", {}).get("wind_down_minutes", 45)
        wind_line = sleep_engine.build_wind_down_autopilot(profile, minutes=wind_down_minutes)

        parts = [scene_line, wind_line]

        # Try Spotify first, then local music
        ok, audio_msg = spotify.play_track_query("sleep ambient")
        if ok and audio_msg:
            parts.append(audio_msg)
        else:
            ok2, audio_msg2 = local_music.play_query("sleep ambient")
            if ok2 and audio_msg2:
                parts.append(audio_msg2)
            elif not ok and not ok2:
                parts.append("Your room settings are optimized for sleep.")

        save_profile(profile)
        return " ".join(p for p in parts if p), True

    return "", False


# ---------------------------------------------------------------------------
# Action executor
# ---------------------------------------------------------------------------

def _execute_resolved_action(
    resolved: dict,
    profile: dict,
    led: Any,
    spotify: Any,
    local_music: Any,
    sleep_engine: Any,
    orchestrator: Any,
    sleep_routine: Any,
    routine_engine: Any,
    on_sleep_timer_finish: Any,
) -> tuple[str, bool]:
    """Execute a resolved action intent against the profile and hardware objects."""
    intent = resolved.get("intent", "")
    slots = resolved.get("slots", {})
    prefs = profile.setdefault("preferences", {})
    flags = profile.setdefault("runtime_flags", {})

    if intent == "set_response_style":
        # Snapshot current values for undo
        undo_keys = {k for k in slots if k in prefs}
        flags["undo_snapshot"] = {
            "intent": intent,
            "preferences": {k: prefs[k] for k in undo_keys},
        }
        for key, val in slots.items():
            prefs[key] = val
        flags["last_action"] = {"intent": intent, "slots": slots}
        return "Done. Response style updated.", True

    if intent == "undo_last_action":
        snapshot = flags.get("undo_snapshot", {})
        restored = snapshot.get("preferences", {})
        if restored:
            prefs.update(restored)
            return "Done. Last action reverted.", True
        return "Nothing to undo.", True

    if intent == "start_wind_down":
        minutes = int(slots.get("minutes", 45))
        msg = sleep_engine.build_wind_down_autopilot(profile, minutes=minutes)
        flags["last_action"] = {"intent": intent, "slots": slots}
        return msg, True

    if intent == "set_scene":
        scene_key = slots.get("scene_key", "balanced_default")
        scene = orchestrator.choose_scene("neutral", False, 1, "guide") if hasattr(orchestrator, "choose_scene") else {}
        scene["key"] = scene_key
        line = orchestrator.apply_scene(led, profile, scene) if scene else ""
        flags["last_action"] = {"intent": intent, "slots": slots}
        return line or "Scene applied.", True

    if intent == "play_music":
        query = slots.get("query", "")
        ok, msg = spotify.play_track_query(query)
        if not ok:
            ok, msg = local_music.play_query(query)
        flags["last_action"] = {"intent": intent, "slots": slots}
        return msg or "Playing music.", True

    if intent == "pause_music":
        ok, msg = spotify.pause()
        if not ok:
            ok, msg = local_music.pause()
        flags["last_action"] = {"intent": intent, "slots": slots}
        return msg or "Music paused.", True

    return "", False