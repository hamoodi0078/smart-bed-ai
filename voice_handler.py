"""Voice turn processing, intent handling, STT/TTS flow, and conversational command execution."""

from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
import logging
import re
import threading
import time
from zoneinfo import ZoneInfo

import requests

from ai.audio_output_manager import AudioOutputManager
from ai.action_resolver import resolve_action
from ai.acoustic_echo_guard import AcousticEchoGuard
from ai.barge_in_monitor import ContinuousBargeInMonitor
from ai.bed_backend_client import BedBackendClient
from ai.conversational_fillers import ConversationalFillerManager
from ai.conversation_engine import ConversationEngine
from ai.audio_playback_controller import AudioPlaybackController
from ai.device_health import format_health_report, run_device_health_checks
from ai.crisis_protocol import (
    build_fast_protocol_message,
    command_match as crisis_command_match,
    should_run_fast_protocol,
)
from ai.emotion_router import detect_emotion_state, emotion_response_hint, emotion_tts_profile
from ai.daily_life_support import DailyLifeSupport
from ai.environment_orchestrator import EnvironmentOrchestrator
from ai.goal_compass import GoalCompass
from ai.intent_classifier import detect_led_command, detect_personality_switch
from ai.local_music_manager import LocalMusicManager
from ai.offline_intent_pack import OfflineIntentPack
from ai.online_calendar import get_online_calendar_answer
from ai.proactive_automation_engine import ProactiveAutomationEngine
from ai.response_quality_gate import ResponseQualityGate
from ai.goal_strategy_engine import GoalStrategyEngine
from ai.adaptive_personality_engine import AdaptivePersonalityEngine
from ai.breathing_guide_engine import BreathingGuideEngine
from ai.dream_journal_manager import DreamJournalManager
from ai.realtime_info import fetch_realtime_context, is_realtime_query
from ai.realtime_voice_pipeline import RealtimeVoicePipeline
from ai.routine_engine import RoutineEngine
from ai.safety_guardrails import evaluate_safety
from ai.safety_valve import SafetyValve
from ai.session_goal_manager import SessionGoalManager
from ai.sensor_bridge import SensorBridge
from ai.signature_experiences import SignatureExperienceEngine
from ai.sleep_intelligence import SleepIntelligenceEngine
from ai.long_term_memory import LongTermMemoryStore
from ai.personality_runtime import PersonalityRuntimeOrchestrator
from ai.sleep_routine_manager import SleepRoutineManager
from ai.spotify_manager import SpotifyManager
from ai.stt_manager import STTManager
from ai.tts_manager import TTSManager
from ai.voice_circuit_breaker import VoiceCircuitBreaker
from ai.wake_word_manager import WakeWordManager
from automations.defaults import build_default_automations
from automations.registry import AutomationRegistry
from config import RUNTIME_DATA_DIR, settings
from core.structured_logging import emit_json_log
from core.types import CommandResult
from commands.lights import handle_light_intent_result
from commands.reflection import process_reflection_turn
from commands.registry import match as match_command_handler
from commands.registry import register as register_command_handler
from commands.reminders import handle_reminder_intent_result
from commands.sleep import handle_sleep_intent_result
from led.led_control import LEDController
from Storage.cache_manager import CacheManager
from Storage.schedule_manager import ScheduleManager, is_valid_time_24h
from Storage.user_profile import delete_profile, load_profile, save_profile
from time_utils import utcnow

from automation_engine import format_repeat_days
from led_controller import (
    ARABIC_COLOR_MAP,
    _clamp_percent,
    _extract_color_from_normalized_text,
    _safe_int,
    apply_led_hardware_config,
    apply_music_led_preferences,
    ensure_hardware_shape,
    ensure_music_led_preferences,
)
from prayer_handler import normalize_followup_tone
from scene_manager import (
    _is_scene_clarification_candidate,
    _resolve_scene_clarification_followup,
    _scene_payload_from_key,
)

LISTEN_CONFIDENCE_CONFIRM_THRESHOLD = 0.58
LISTEN_CONFIDENCE_MIN_ACCEPT_THRESHOLD = 0.50

THERAPIST_DISTRESS_KEYWORDS = (
    "sad",
    "upset",
    "worried",
    "worry",
    "anxious",
    "stressed",
    "stress",
    "overwhelmed",
    "scared",
    "lonely",
    "depressed",
    "hurt",
    "cry",
    "hopeless",
    "empty",
    "panic",
    "fear",
    "i feel bad",
    "i feel down",
    "i am not okay",
    "im not okay",
    "i'm not okay",
    "i feel worried",
    "قلقان",
    "حزين",
    "زعلان",
    "متوتر",
    "مضغوط",
)

def ensure_emotional_followup_shape(profile: dict) -> dict:
    daily = profile.setdefault("daily_life", {})
    daily.setdefault("overthinking_entries", [])
    daily.setdefault("last_mood_bundle", "")
    daily.setdefault("last_coaching_tone", "")
    daily.setdefault("emotional_followups", [])
    daily.setdefault("followup_opt_out", False)
    daily.setdefault("last_emotional_followup_date", "")
    return daily

def _is_meaningful_followup_turn(user_text: str) -> bool:
    normalized = normalize_for_intent(user_text)
    if not normalized:
        return False
    if len(normalized.split()) <= 1 and normalized in {"hi", "hey", "hello", "yo", "sup", "ok", "okay", "yes", "no"}:
        return False
    return True

def _extract_concern_emotion(normalized: str) -> str:
    if has_any(normalized, ("sad", "down", "depressed", "حزين", "زعلان")):
        return "sad"
    if has_any(normalized, ("worried", "worry", "anxious", "panic", "fear", "قلقان", "متوتر")):
        return "worried"
    if has_any(normalized, ("stressed", "stress", "overwhelmed", "مضغوط")):
        return "stressed"
    return "concerned"

def _topic_summary(user_text: str, max_words: int = 12) -> str:
    cleaned = re.sub(r"\s+", " ", (user_text or "").strip())
    words = cleaned.split()
    if not words:
        return "something that felt heavy"
    short = " ".join(words[:max_words]).strip(" ,.;:-")
    return short or "something that felt heavy"

def record_therapist_concern(profile: dict, user_text: str, personality: str, now: datetime | None = None) -> bool:
    if (personality or "").strip().lower() != "therapist":
        return False
    daily = ensure_emotional_followup_shape(profile)
    if bool(daily.get("followup_opt_out", False)):
        return False

    normalized = normalize_for_intent(user_text)
    if not has_any(normalized, THERAPIST_DISTRESS_KEYWORDS):
        return False

    now = now or datetime.now()
    topic = _topic_summary(user_text)
    entries = daily.get("emotional_followups", [])
    if entries:
        latest = entries[-1]
        if (str(latest.get("topic", "")).strip().lower() == topic.lower()) and (
            str(latest.get("created_date", "")) == now.date().isoformat()
        ):
            return False

    entries.append(
        {
            "topic": topic,
            "emotion": _extract_concern_emotion(normalized),
            "created_at": now.isoformat(timespec="seconds"),
            "created_date": now.date().isoformat(),
            "followup_due_date": (now.date() + timedelta(days=1)).isoformat(),
            "followup_asked_at": "",
            "resolved": False,
        }
    )
    daily["emotional_followups"] = entries[-40:]
    return True

def build_bed_guide_steps() -> tuple[str, ...]:
    return (
        "Wake and sleep: say 'wake' to start and 'sleep mode' to end active listening.",
        "Nickname: say 'i want to give you a nickname' then tell the name. Ask 'what is your nickname'.",
        "Lights: try 'set user strip to blue', 'set animation to rainbow', or 'dim lights'.",
        "Music and audio: try 'turn on music lights', 'set music lights to wave mode', or 'use bed speaker'.",
        "Routines: try 'set bedtime routine for 22:30' and 'set morning routine for 07:00'.",
        "Care and privacy: ask 'sleep help', 'privacy status', or 'delete all my data'.",
    )

def render_bed_guide_step(step_index: int) -> str:
    steps = build_bed_guide_steps()
    if step_index < 0:
        step_index = 0
    if step_index >= len(steps):
        return "Bed guide completed. Say 'bed tutorial' anytime to run it again."
    return (
        f"Bed guide {step_index + 1}/{len(steps)}: {steps[step_index]} "
        "Say 'next guide step' to continue, 'repeat guide step' to hear this again, or 'stop bed guide'."
    )

def resolve_bed_guide_shortcut_intent(user_text: str) -> str:
    normalized = normalize_for_intent(user_text)
    if not normalized:
        return ""

    next_tokens = {
        "next",
        "continue",
        "go next",
        "go on",
        "keep going",
        "move on",
        "next one",
        "التالي",
        "كمل",
        "كمّل",
        "التاليه",
    }
    repeat_tokens = {
        "repeat",
        "again",
        "say again",
        "repeat that",
        "اعيد",
        "أعيد",
        "كرر",
    }
    stop_tokens = {
        "stop",
        "exit",
        "cancel",
        "enough",
        "وقف",
        "الغاء",
        "إلغاء",
        "خلاص",
    }

    if normalized in next_tokens:
        return "bed_guide_next"
    if normalized.startswith("next ") or normalized.startswith("continue "):
        return "bed_guide_next"
    if normalized in repeat_tokens:
        return "bed_guide_repeat"
    if normalized.startswith("repeat ") or normalized.startswith("again "):
        return "bed_guide_repeat"
    if normalized in stop_tokens:
        return "bed_guide_stop"
    if normalized.startswith("stop ") or normalized.startswith("cancel "):
        return "bed_guide_stop"
    return ""

def resolve_therapist_followup_if_answered(profile: dict, user_text: str, now: datetime | None = None) -> bool:
    daily = ensure_emotional_followup_shape(profile)
    entries = daily.get("emotional_followups", [])
    active = None
    for entry in reversed(entries):
        if bool(entry.get("resolved", False)):
            continue
        if str(entry.get("followup_asked_at", "")).strip():
            active = entry
            break
    if active is None:
        return False

    normalized = normalize_for_intent(user_text)
    if not normalized:
        return False

    if has_any(normalized, ("dont ask", "do not ask", "stop asking", "leave this", "لا تسال", "لا تسأل")):
        active["resolved"] = True
        daily["followup_opt_out"] = True
        now = now or datetime.now()
        active["resolved_at"] = now.isoformat(timespec="seconds")
        return True

    if not has_any(
        normalized,
        (
            "i am",
            "im",
            "i m",
            "feeling",
            "better",
            "worse",
            "fine",
            "okay",
            "not okay",
            "still",
            "الحمدلله",
            "كويس",
            "تعبان",
            "قلقان",
            "حزين",
        ),
    ):
        return False

    now = now or datetime.now()
    active["resolved"] = True
    active["resolved_at"] = now.isoformat(timespec="seconds")
    return True

def get_due_therapist_followup(profile: dict, personality: str, user_text: str, now: datetime | None = None) -> str:
    if (personality or "").strip().lower() != "therapist":
        return ""
    if not _is_meaningful_followup_turn(user_text):
        return ""

    daily = ensure_emotional_followup_shape(profile)
    if bool(daily.get("followup_opt_out", False)):
        return ""

    now = now or datetime.now()
    today = now.date().isoformat()
    if str(daily.get("last_emotional_followup_date", "")) == today:
        return ""

    entries = daily.get("emotional_followups", [])
    due_entry = None
    for entry in entries:
        if bool(entry.get("resolved", False)):
            continue
        if str(entry.get("followup_asked_at", "")).strip():
            continue
        due_date = str(entry.get("followup_due_date", ""))
        if due_date and due_date <= today:
            due_entry = entry
            break

    if due_entry is None:
        return ""

    topic = str(due_entry.get("topic", "")).strip() or "what you shared yesterday"
    tone = normalize_followup_tone(profile.get("preferences", {}).get("therapist_followup_tone", "soft"))
    templates_by_tone = {
        "soft": (
            "Yesterday you sounded worried about {topic}. How are you feeling now?",
            "You were carrying something heavy yesterday about {topic}. How are you today?",
            "I remember you were concerned about {topic} yesterday. How is your heart now?",
        ),
        "teen": (
            "Yesterday you seemed stressed about {topic}. How are you doing today, for real?",
            "You had a lot on your mind yesterday about {topic}. How are you feeling now?",
            "Quick check-in: yesterday you were worried about {topic}. Better, same, or worse today?",
        ),
        "islamic": (
            "Yesterday you were worried about {topic}. How is your heart today, alhamdulillah?",
            "I remember yesterday's concern about {topic}. How are you feeling now? May Allah ease it for you.",
            "You shared worry about {topic} yesterday. How are you now? I pray today feels lighter for you.",
        ),
    }
    templates = templates_by_tone.get(tone, templates_by_tone["soft"])
    prompt = templates[len(topic) % len(templates)].format(topic=topic)

    due_entry["followup_asked_at"] = now.isoformat(timespec="seconds")
    daily["last_emotional_followup_date"] = today
    return prompt

def _parse_yes_no(value: str, default: bool = True) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    if text in ("y", "yes", "on", "true", "1"):
        return True
    if text in ("n", "no", "off", "false", "0"):
        return False
    return default

def build_help_overview() -> str:
    return (
        "Quick help -> Wake/sleep: 'wake', 'sleep mode'. "
        "Lights: 'set user strip to #00ffaa', 'set animation to rainbow'. "
        "Music lights: 'turn on music lights', 'set music lights to wave mode', "
        "'set music lights brightness to 30'. "
        "Privacy: 'privacy status', 'set retention to 30 days', 'delete all my data'. "
        "Voice pacing: 'mute thinking acknowledgements', 'enable thinking acknowledgements'. "
        "Reliability: 'run health check', 'pilot readiness report', 'pilot readiness checklist', 'pilot go no go', 'pilot smoke checklist', 'bed phase status'. "
        "Sleep features: 'start wind down autopilot 45', 'optimize my room for sleep', "
        "'night wake recovery', 'sleep consistency', 'predictive bedtime drift', 'weekly sleep insights', "
        "'partner sleep mode status', 'weekly recovery score card', 'what did you auto-manage today'. "
        "Signature modes: 'start deep recovery', 'run couple harmony wake', '90 second reset'. "
        "Guided tour: 'bed tutorial', 'next guide step', 'repeat guide step'. "
        "Routines: 'set bedtime routine for 22:30', 'set morning routine for 07:00'. "
        "Audio: 'use bed speaker', 'scan bluetooth speakers', 'connect bluetooth speaker <name>'. "
        "New: 'start breathing guide', 'dream journal', 'adaptive personality insights'."
    )

def build_sleep_help() -> str:
    return (
        "Sleep help -> 1) Wind-down: 'start wind down autopilot 45'. "
        "2) One-command setup: 'optimize my room for sleep'. "
        "3) If you wake at night: 'night wake recovery'. "
        "4) Partner mode: 'enable partner sleep mode', 'set partner 1 wake style gentle', "
        "'set partner 2 wake style energizing', 'partner sleep mode status'. "
        "5) Recovery analytics: 'weekly recovery score card'. "
        "6) Track and improve: 'log bedtime', 'log wake', 'sleep consistency', 'sleep quality score', "
        "'predictive bedtime drift', 'sleep debt recovery plan'. "
        "7) Weekly coaching: 'weekly sleep insights'. "
        "8) Signature experiences: 'start deep recovery', 'run couple harmony wake', '90 second reset'."
    )

def _select_runtime_phrase(
    profile: dict,
    runtime_orchestrator: PersonalityRuntimeOrchestrator | None,
    candidates: tuple[str, ...] | list[str],
    *,
    phrase_kind: str,
) -> str:
    options = list(candidates or [])
    if runtime_orchestrator is not None:
        try:
            return runtime_orchestrator.choose_unique_phrase(profile, options, phrase_kind=phrase_kind)
        except Exception:
            pass
    return options[0] if options else ""

def build_wake_greeting(
    profile: dict,
    runtime_orchestrator: PersonalityRuntimeOrchestrator | None = None,
) -> str:
    raw_name = str(profile.get("name", "") or "").strip()
    prefs = profile.get("preferences", {})
    language_pref = str(prefs.get("language", "auto") or "auto").strip().lower()
    is_arabic_name = bool(re.search(r"[\u0600-\u06FF]", raw_name))
    use_arabic = language_pref in {"ar", "arabic", "ar-sa"} or (
        language_pref in {"auto", "any", "all", ""} and is_arabic_name
    )

    hour = datetime.now().hour
    if use_arabic:
        if 5 <= hour < 12:
            candidates = ("صباح الخير", "أهلا صباحك جميل", "صباح النور")
            intro = _select_runtime_phrase(profile, runtime_orchestrator, candidates, phrase_kind="greeting_ar_morning")
        elif 12 <= hour < 18:
            candidates = ("مساء الخير", "أهلا مساءك جميل", "مساء النور")
            intro = _select_runtime_phrase(profile, runtime_orchestrator, candidates, phrase_kind="greeting_ar_afternoon")
        else:
            candidates = ("أهلا", "هلا", "أهلا وسهلا")
            intro = _select_runtime_phrase(profile, runtime_orchestrator, candidates, phrase_kind="greeting_ar_evening")
        if raw_name:
            return f"{intro} {raw_name}. أنا هنا وجاهز للمساعدة. قل 'sleep mode' لإنهاء الجلسة."
        return f"{intro}. أنا هنا وجاهز للمساعدة. قل 'sleep mode' لإنهاء الجلسة."

    if 5 <= hour < 12:
        candidates = ("Good morning", "Morning", "Good morning and welcome back")
        intro = _select_runtime_phrase(profile, runtime_orchestrator, candidates, phrase_kind="greeting_en_morning")
    elif 12 <= hour < 18:
        candidates = ("Good afternoon", "Hey, good afternoon", "Welcome back this afternoon")
        intro = _select_runtime_phrase(profile, runtime_orchestrator, candidates, phrase_kind="greeting_en_afternoon")
    else:
        candidates = ("Good evening", "Evening", "Good evening, welcome back")
        intro = _select_runtime_phrase(profile, runtime_orchestrator, candidates, phrase_kind="greeting_en_evening")
    if raw_name:
        return f"{intro}, {raw_name}. I am here and listening. Say 'sleep mode' to end this session."
    return f"{intro}. I am here and listening. Say 'sleep mode' to end this session."

def build_transition_ack(profile: dict, runtime_orchestrator: PersonalityRuntimeOrchestrator) -> str:
    candidates = (
        "Okay, one moment.",
        "Got it, give me a second.",
        "Sure, I am on it.",
        "Alright, working on that now.",
    )
    return runtime_orchestrator.choose_unique_phrase(
        profile,
        list(candidates),
        phrase_kind="transition_ack",
    )

def should_use_local_music_fallback(message: str) -> bool:
    text = (message or "").lower()
    keywords = (
        "spotify is not configured",
        "token expired",
        "premium",
        "user may not be registered",
        "no active spotify device",
        "spotify request failed",
        "spotify rejected",
    )
    return any(k in text for k in keywords)

def _parse_health_summary_counts(health_report: str) -> tuple[int, int]:
    match = re.search(r"health summary\s+(\d+)\s*/\s*(\d+)\s+checks passed", health_report or "", re.IGNORECASE)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))

def _parse_health_warn_names(health_report: str) -> set[str]:
    return {
        name.strip().upper()
        for name in re.findall(r"\[WARN\]\s+([A-Z0-9_]+)\s*:", health_report or "", re.IGNORECASE)
        if name.strip()
    }

def build_pilot_readiness_checklist(profile: dict, health_report: str) -> str:
    preferences = profile.get("preferences", {})
    speed_mode = str(preferences.get("speed_mode", "normal") or "normal").strip().lower()
    response_style = str(preferences.get("response_style", "quick") or "quick").strip().lower()
    engagement = str(preferences.get("engagement_level", "normal") or "normal").strip().lower()

    quick_timeout = _safe_int(settings.chat_quick_timeout_seconds, default_value=4, min_value=1, max_value=60)
    total_timeout = _safe_int(settings.chat_total_timeout_seconds, default_value=10, min_value=1, max_value=120)
    max_tokens = _safe_int(settings.chat_max_response_tokens, default_value=120, min_value=32, max_value=512)

    latency_ok = quick_timeout <= 4 and total_timeout <= 10 and max_tokens <= 140 and speed_mode in ("fast", "normal")
    off_topic_ok = response_style in ("quick", "balanced")
    boredom_ok = engagement in ("high", "normal")

    checks_ok, checks_total = _parse_health_summary_counts(health_report)
    warn_names = _parse_health_warn_names(health_report)
    spotify_only_warn = warn_names == {"SPOTIFY_CONFIG"}
    local_music_ok = "LOCAL_MUSIC" not in warn_names
    failure_ok = (checks_total > 0 and checks_ok == checks_total) or (spotify_only_warn and local_music_ok)

    latency_status = "PASS" if latency_ok else "WARN"
    off_topic_status = "PASS" if off_topic_ok else "WARN"
    boredom_status = "PASS" if boredom_ok else "WARN"
    failure_status = "PASS" if failure_ok else "WARN"

    return (
        "Pilot readiness checklist -> "
        f"latency={latency_status} (quick={quick_timeout}s, total={total_timeout}s, max_tokens={max_tokens}, speed={speed_mode}); "
        f"off_topic={off_topic_status} (response_style={response_style}); "
        f"boredom_reduction={boredom_status} (engagement={engagement}); "
        f"failure_handling={failure_status} (health={checks_ok}/{checks_total}, warns={','.join(sorted(warn_names)) if warn_names else 'none'})."
    )

def build_pilot_go_no_go(profile: dict, health_report: str) -> str:
    checklist = build_pilot_readiness_checklist(profile, health_report)
    if "WARN" in checklist:
        return "Pilot signoff -> HOLD. Resolve WARN items before onboarding testers. " + checklist
    return "Pilot signoff -> GO. Core readiness checks are passing. " + checklist

def normalize_for_intent(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-z0-9#(),\s'\u0600-\u06ff]+", " ", (text or "").lower()),
    ).strip()

def has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)

def _is_llm_fallback_response(text: str) -> bool:
    value = str(text or "").strip()
    return value.startswith("(Deepgram fallback -") or value.startswith("(Offline fallback -")

def _voice_offline_fallback_response(offline_pack: OfflineIntentPack, user_text: str) -> str:
    offline_response, handled_offline = offline_pack.handle(user_text)
    if handled_offline and str(offline_response or "").strip():
        return str(offline_response).strip()
    return (
        "Voice pipeline is in offline recovery mode. "
        "I can still handle core local commands like alarms, routines, lights, and local music."
    )

def _is_voice_circuit_reset_command(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return lowered in {
        "reset voice circuit",
        "voice circuit reset",
        "reset voice pipeline",
        "reset voice breaker",
    }

def _extract_openai_chat_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if text_value:
                parts.append(str(text_value))
        return "".join(parts).strip()
    return ""

def _build_gpt_route_diagnostics(backend_client: BedBackendClient | None) -> dict:
    issues: list[str] = []
    backend_proxy_enabled = bool(settings.use_backend_ai_proxy)
    backend_configured = bool(backend_client is not None and backend_client.is_configured())
    openai_direct_enabled = bool(settings.use_openai_direct)
    openai_api_key_present = bool(str(settings.openai_api_key or "").strip())
    openai_model_present = bool(str(settings.openai_chat_model or "").strip())

    backend_ready = backend_proxy_enabled and backend_configured
    openai_ready = openai_direct_enabled and openai_api_key_present and openai_model_present

    if openai_direct_enabled and (not openai_api_key_present):
        issues.append("OPENAI_API_KEY is missing while USE_OPENAI_DIRECT=1.")
    if openai_direct_enabled and (not openai_model_present):
        issues.append("OPENAI_CHAT_MODEL is missing while USE_OPENAI_DIRECT=1.")
    if backend_proxy_enabled and (not backend_configured):
        issues.append("APP_BACKEND_BASE_URL or BED_DEVICE_ID is missing for backend GPT route.")
    if (not openai_direct_enabled) and (not backend_proxy_enabled):
        issues.append("Both USE_OPENAI_DIRECT and USE_BACKEND_AI_PROXY are disabled.")

    return {
        "openai_ready": openai_ready,
        "backend_ready": backend_ready,
        "openai_direct_enabled": openai_direct_enabled,
        "backend_proxy_enabled": backend_proxy_enabled,
        "issues": issues,
    }

def _request_openai_chat_reply(
    *,
    user_text_for_ai: str,
    personality: str,
    user_context: str,
    realtime_context: str,
    max_response_tokens: int,
) -> tuple[bool, str]:
    api_key = str(settings.openai_api_key or "").strip()
    model = str(settings.openai_chat_model or "").strip()
    if not api_key:
        return False, "OPENAI_API_KEY is missing."
    if not model:
        return False, "OPENAI_CHAT_MODEL is missing."

    base_url = str(settings.openai_base_url or "https://api.openai.com/v1").strip().rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are Smart Bed's conversational assistant. "
                f"Personality mode: {personality}. Keep replies practical, natural, and concise."
            ),
        }
    ]
    if user_context.strip():
        messages.append({"role": "system", "content": f"User context:\n{user_context.strip()}"})
    if realtime_context.strip():
        messages.append({"role": "system", "content": f"Realtime context:\n{realtime_context.strip()}"})
    messages.append({"role": "user", "content": str(user_text_for_ai or "").strip()})
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max(40, int(max_response_tokens)),
        "temperature": 0.7,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=max(6, int(settings.ai_timeout_seconds)),
        )
        if not response.ok:
            body_preview = str(response.text or "").replace("\n", " ").strip()[:260]
            return False, f"OpenAI chat failed ({response.status_code}): {body_preview}"
        text = _extract_openai_chat_text(response.json())
        if not text:
            return False, "OpenAI chat returned an empty response."
        return True, text
    except Exception as e:
        return False, f"OpenAI chat request error: {e}"

def _looks_like_echo_capture(user_text: str, last_assistant_response: str, confidence: float) -> bool:
    user_norm = normalize_for_intent(user_text)
    assistant_norm = normalize_for_intent(last_assistant_response)
    if (not user_norm) or (not assistant_norm):
        return False

    if len(user_norm) < 12:
        return False

    score = SequenceMatcher(None, user_norm, assistant_norm).ratio()
    likely_clip = (len(user_norm) >= 24) and (user_norm in assistant_norm)
    is_low_conf = float(confidence or 0.0) < 0.78
    return is_low_conf and (score >= 0.88 or likely_clip)

def detect_natural_bed_intent(user_text: str, breathing_offer_active: bool = False) -> tuple[str, dict]:
    text = normalize_for_intent(user_text)
    payload: dict = {}
    light_scope = has_any(
        text,
        (
            "light",
            "lights",
            "led",
            "lighting",
            "lamp",
            "lamps",
            "room light",
            "room lights",
            "strip",
            "strips",
            "الضوء",
            "الاضواء",
            "الأضواء",
            "اضاءة",
            "إضاءة",
            "الوان",
            "ألوان",
        ),
    )

    # Breathing guide intents
    if (
        (
            has_any(text, ("breathe", "breathing", "4-7-8", "4 7 8", "478", "تنفس", "التنفس", "4-7-8"))
            and has_any(text, ("start", "begin", "do", "try", "guide", "ابدأ", "ابدا", "نبدأ", "ابدئي", "خلينا"))
        )
        or has_any(
            text,
            (
                "start this technique",
                "start the technique",
                "begin this technique",
                "نبدأ التقنية",
                "ابدأ التقنية",
                "ابدا التقنية",
                "خلينا نبدأ",
                "خلنا نبدأ",
                "يلا نبدأ",
            ),
        )
        or (
            breathing_offer_active
            and text in ("lets start", "let's start", "okay", "ok", "yes", "نعم", "اوكي", "حسنا", "تمام", "يلا")
        )
    ):
        return "start_breathing", payload

    if has_any(
        text,
        (
            "stop breathing",
            "cancel breathing",
            "end breathing",
            "stop the breathing guide",
            "وقف التنفس",
            "اوقف التنفس",
            "إيقاف التنفس",
            "الغاء التنفس",
        ),
    ):
        return "stop_breathing", payload

    # Dream journal intents
    if has_any(
        text,
        (
            "what did i dream",
            "dream journal",
            "talk about my dream",
            "i want to share my dream",
            "ماذا حلمت",
            "احكي حلمي",
            "أحكي حلمي",
            "يوميات الاحلام",
            "يوميات الأحلام",
        ),
    ):
        return "dream_prompt", payload

    if has_any(
        text,
        (
            "dream insights",
            "dream patterns",
            "analyze my dreams",
            "dream analysis",
            "تحليل الاحلام",
            "تحليل الأحلام",
            "انماط الاحلام",
            "أنماط الأحلام",
        ),
    ):
        return "dream_insights", payload

    # Adaptive personality intents
    if has_any(
        text,
        (
            "adaptive personality",
            "personality insights",
            "how are you adapting",
            "الشخصية التكيفية",
            "الشخصية المتكيفة",
            "تحليل الشخصية",
        ),
    ):
        return "adaptive_insights", payload

    if has_any(
        text,
        (
            "enable adaptive personality",
            "turn on adaptive personality",
            "فعل الشخصية التكيفية",
            "تشغيل الشخصية التكيفية",
        ),
    ):
        payload["enabled"] = True
        return "adaptive_toggle", payload

    if has_any(
        text,
        (
            "disable adaptive personality",
            "turn off adaptive personality",
            "ايقاف الشخصية التكيفية",
            "إيقاف الشخصية التكيفية",
            "عطل الشخصية التكيفية",
        ),
    ):
        payload["enabled"] = False
        return "adaptive_toggle", payload

    # Wake nickname intents
    if has_any(
        text,
        (
            "what is your nickname",
            "what is your nick name",
            "what s your nickname",
            "what s your nick name",
            "what's your nickname",
            "what's your nick name",
            "do you have a nickname",
            "what should i call you",
            "what is your name",
            "what should i name you",
            "what did i name you",
            "what did i call you",
            "شو اسمك",
            "ايش اسمك",
        ),
    ):
        return "get_bed_nickname", payload

    nickname_statement_match = re.search(
        r"(.+?)\s+(?:is|it is|it's|will be)\s+your\s+nick ?name$",
        text,
    )
    if nickname_statement_match:
        payload["nickname"] = nickname_statement_match.group(1).strip(" .'")
        return "set_bed_nickname", payload

    nickname_statement_match = re.search(
        r"your\s+nick ?name\s+(?:is|will be)\s+(.+)$",
        text,
    )
    if nickname_statement_match:
        payload["nickname"] = nickname_statement_match.group(1).strip(" .'")
        return "set_bed_nickname", payload

    nickname_statement_match = re.search(
        r"(.+?)\s+i\s+would\s+like\s+to\s+call\s+you$",
        text,
    )
    if nickname_statement_match:
        payload["nickname"] = nickname_statement_match.group(1).strip(" .'")
        return "set_bed_nickname", payload

    nickname_match = re.search(
        r"(?:set (?:bed|your)? ?nick ?name(?: to)?|change (?:bed|your)? ?nick ?name(?: to)?|call (?:this bed|you)|name you)\s+(.+)$",
        text,
    )
    if nickname_match:
        payload["nickname"] = nickname_match.group(1).strip(" .")
        return "set_bed_nickname", payload

    if has_any(
        text,
        (
            "set your nickname",
            "set your nick name",
            "set bed nickname",
            "change your nickname",
            "change bed nickname",
            "i want to set your nickname",
            "i wanna set your nickname",
            "i wanna set your nick name",
            "i want to give you a nickname",
            "i want to give u a nickname",
            "i wanna give u a nickname",
            "i want to give u nickname",
            "i want you to have a nickname",
            "i want u to have a nickname",
            "i want to you to have a nick name",
            "give you a nickname",
            "give u a nickname",
            "ابغى اسميك",
            "أبغى أسميك",
            "اريد اسميك",
            "أريد أسميك",
            "بدي اسميك",
            "بدّي أسميك",
        ),
    ):
        return "nickname_setup", payload

    if has_any(
        text,
        (
            "clear bed nickname",
            "remove bed nickname",
            "reset bed nickname",
            "delete bed nickname",
            "remove nickname",
            "clear nickname",
            "احذف اسم السرير",
            "امسح اسم السرير",
        ),
    ):
        return "clear_bed_nickname", payload

    if has_any(
        text,
        (
            "what is your nickname",
            "what is your nick name",
            "what s your nickname",
            "what s your nick name",
            "what's your nickname",
            "what's your nick name",
            "do you have a nickname",
            "what should i call you",
            "what is your name",
            "what should i name you",
            "what did i name you",
            "what did i call you",
            "شو اسمك",
            "ايش اسمك",
        ),
    ):
        return "get_bed_nickname", payload

    if has_any(
        text,
        (
            "show wake names",
            "show wake aliases",
            "wake names",
            "wake aliases",
            "what are your wake words",
            "what are your wake phrases",
            "ايش اسماء التفعيل",
            "ما اسماء التفعيل",
        ),
    ):
        return "show_wake_names", payload

    if has_any(
        text,
        (
            "bed tutorial",
            "start bed tutorial",
            "teach me the bed",
            "how to use this bed",
            "how do i use this bed",
            "guide me through the bed",
            "show bed guide",
            "show bed tutorial",
        ),
    ):
        return "bed_guide_start", payload

    if has_any(
        text,
        (
            "next guide step",
            "continue bed guide",
            "bed guide next",
            "next tutorial step",
        ),
    ):
        return "bed_guide_next", payload

    if has_any(
        text,
        (
            "repeat guide step",
            "repeat bed guide step",
            "bed guide repeat",
            "repeat tutorial step",
        ),
    ):
        return "bed_guide_repeat", payload

    if has_any(
        text,
        (
            "stop bed guide",
            "exit bed guide",
            "end bed guide",
            "cancel bed guide",
            "stop bed tutorial",
        ),
    ):
        return "bed_guide_stop", payload

    # Routine intents
    if has_any(
        text,
        (
            "start bedtime routine",
            "begin bedtime routine",
            "lets do bedtime routine",
            "ابدأ روتين النوم",
            "ابدا روتين النوم",
            "نبدأ روتين النوم",
        ),
    ):
        return "start_bedtime_routine", payload

    if has_any(
        text,
        (
            "start morning routine",
            "run morning routine",
            "begin morning routine",
            "ابدأ روتين الصباح",
            "ابدا روتين الصباح",
            "نبدأ روتين الصباح",
        ),
    ):
        return "start_morning_routine", payload

    # Lighting intents
    if light_scope and has_any(
        text,
        ("brighter", "increase brightness", "more bright", "زيد الاضاءة", "زيد الإضاءة", "ارفع الاضاءة", "ارفع الإضاءة"),
    ):
        return "brightness_up", payload

    if light_scope and has_any(
        text,
        ("dim", "dimmer", "lower brightness", "less bright", "خفف الاضاءة", "خفف الإضاءة", "قلل الاضاءة", "قلل الإضاءة"),
    ):
        return "brightness_down", payload

    brightness_match = re.search(r"(\d{1,3})\s*%?", text)
    if light_scope and brightness_match and has_any(
        text,
        ("brightness", "bright", "dim to", "set to", "اضاءة", "إضاءة", "سطوع"),
    ):
        payload["brightness_percent"] = int(brightness_match.group(1))
        return "brightness_set", payload

    music_scope = has_any(
        text,
        (
            "music",
            "spotify",
            "song",
            "songs",
            "audio",
            "اغنية",
            "اغاني",
            "أغنية",
            "أغاني",
            "موسيقى",
            "سبوتيفاي",
        ),
    ) and has_any(
        text,
        (
            "light",
            "lights",
            "led",
            "lighting",
            "الضوء",
            "الاضواء",
            "الأضواء",
        ),
    )

    if music_scope and has_any(
        text,
        (
            "status",
            "config",
            "setting",
            "اعدادات",
            "إعدادات",
            "حالة",
        ),
    ):
        return "music_lights_status", payload

    if music_scope and has_any(
        text,
        (
            "turn on",
            "enable",
            "start sync",
            "sync",
            "on",
            "شغل",
            "تشغيل",
            "فعل",
            "فعّل",
            "مزامنة",
        ),
    ) and not has_any(text, ("off", "disable", "stop", "ايقاف", "إيقاف", "وقف", "تعطيل")):
        return "music_lights_on", payload

    if music_scope and has_any(
        text,
        (
            "turn off",
            "disable",
            "stop sync",
            "off",
            "ايقاف",
            "إيقاف",
            "وقف",
            "تعطيل",
        ),
    ):
        return "music_lights_off", payload

    if music_scope and has_any(text, ("calm", "night", "هادئ", "هادى", "ليلي", "ليل")):
        return "music_lights_calm", payload

    if music_scope and has_any(text, ("energetic", "party", "حماسي", "حفلة", "قوي")):
        return "music_lights_energetic", payload

    if music_scope and has_any(text, ("both strips", "both", "strip both", "الشريطين", "كله", "كلاهما")):
        payload["target"] = "both"
        return "music_lights_target", payload

    if music_scope and has_any(text, ("user strip", "main strip", "single strip", "strip only", "شريط المستخدم", "شريط واحد")):
        payload["target"] = "user_only"
        return "music_lights_target", payload

    mode_match = re.search(r"(pulse|wave|spectrum)", text)
    if music_scope and mode_match:
        payload["mode"] = mode_match.group(1)
        return "music_lights_mode", payload

    brightness_match = re.search(r"(\d{1,3})\s*%?", text)
    if music_scope and brightness_match and has_any(text, ("brightness", "bright", "سطوع", "إضاءة", "اضاءة")):
        payload["brightness_percent"] = int(brightness_match.group(1))
        return "music_lights_brightness", payload

    if music_scope and has_any(text, ("default", "reset", "افتراضي", "إعادة ضبط", "اعادة ضبط")):
        return "music_lights_default", payload

    color_request_scope = light_scope or has_any(
        text,
        (
            "make it",
            "change it to",
            "set it to",
            "make the room",
            "room color",
            "خليها",
            "خلها",
            "خلي الغرفة",
            "لون الغرفة",
        ),
    )
    if color_request_scope:
        named = tuple(LEDController.NAMED_COLORS.keys())
        for name in named:
            if f" {name} " in f" {text} ":
                payload["color"] = name
                return "set_color", payload

        for ar_name, en_name in ARABIC_COLOR_MAP.items():
            if f" {ar_name.lower()} " in f" {text} ":
                payload["color"] = en_name
                return "set_color", payload

        hex_match = re.search(r"#[0-9a-f]{6}", text)
        if hex_match:
            payload["color"] = hex_match.group(0)
            return "set_color", payload

    return "", payload

def build_wake_aliases_from_profile(profile: dict) -> list[str]:
    prefs = profile.get("preferences", {})
    aliases = []

    def _alias_variants(value: str) -> list[str]:
        base = str(value or "").strip().lower()
        if not base:
            return []
        reduced = re.sub(r"([a-z])\1+", r"\1", base)
        variants = [base]
        if reduced and reduced != base:
            variants.append(reduced)
        return variants

    nickname = str(prefs.get("bed_nickname", "") or "").strip().lower()
    if nickname:
        for variant in _alias_variants(nickname):
            aliases.append(variant)
            aliases.append(f"hey {variant}")

    extra_aliases = prefs.get("wake_aliases", [])
    if isinstance(extra_aliases, list):
        for item in extra_aliases:
            alias = str(item or "").strip().lower()
            if alias:
                aliases.extend(_alias_variants(alias))

    cleaned = []
    for alias in aliases:
        if alias and alias not in cleaned:
            cleaned.append(alias)
    return cleaned[:8]

def apply_bed_nickname(profile: dict, wake_word_manager: WakeWordManager, raw_nickname: str) -> str:
    nickname = re.sub(r"\s+", " ", str(raw_nickname or "")).strip(" '")
    if not nickname:
        return ""
    if len(nickname) > 32:
        nickname = nickname[:32].strip()
    profile.setdefault("preferences", {})["bed_nickname"] = nickname
    wake_word_manager.set_wake_aliases(build_wake_aliases_from_profile(profile))
    return nickname

def build_user_context(
    profile: dict,
    goals_context: str = "",
    compass_context: str = "",
    progress_context: str = "",
    emotion_context: str = "",
    sleep_context: str = "",
    runtime_context: str = "",
    goal_strategy_context: str = "",
    environment_context: str = "",
    daily_life_context: str = "",
    detailed_mode: bool = False,
) -> str:
    prefs = profile.get("preferences", {})
    name = profile.get("name", "friend")
    age = str(profile.get("age", "?") or "?")
    style = prefs.get("response_style", "quick")
    engagement = prefs.get("engagement_level", "high")
    language = str(prefs.get("language", "auto") or "auto").strip()
    if language.lower() in ("auto", "any", "all"):
        language_instruction = "Reply in the same language as the user's latest message."
    else:
        language_instruction = f"Reply in language: {language}."
    if detailed_mode:
        detail_instruction = "User asked for detail now; provide a fuller explanation with one practical example."
    elif style == "detailed":
        detail_instruction = (
            "Preferred style is detailed: answer in 3-5 lines with clear structure and one concrete example."
        )
    elif style == "balanced":
        detail_instruction = (
            "Preferred style is balanced: answer in 2-4 natural lines and include one concrete idea or example when useful."
        )
    else:
        detail_instruction = "Preferred style is quick: keep replies in 1-2 short lines unless user asks for depth."
    engagement_instruction = (
        "Engagement rule: respond like a real conversation partner. "
        "Use the user's exact wording when helpful, avoid generic advice, and keep continuity with previous turns. "
        "Ask one specific follow-up question only when it clearly helps progress."
    )
    return (
        f"User name: {name}. User age: {age}. Preferred response style: {style}. "
        f"Engagement level: {engagement}. Language hint: {language}. "
        f"{language_instruction} "
        f"{detail_instruction} "
        f"{engagement_instruction} "
        f"{goals_context} "
        f"{compass_context} "
        f"{progress_context} "
        f"{emotion_context} "
        f"{sleep_context} "
        f"{runtime_context} "
        f"{goal_strategy_context} "
        f"{environment_context} "
        f"{daily_life_context} "
        "Keep responses concise, natural, and professionally useful."
    )

def wants_detailed_answer(user_text: str) -> bool:
    lower = (user_text or "").lower()
    detail_markers = (
        "tell me more",
        "tell me about",
        "teach me",
        "walk me through",
        "break it down",
        "more please",
        "expand",
        "go deeper",
        "in detail",
        "more detail",
        "explain more",
        "تفصيل",
        "بالتفصيل",
    )
    return any(k in lower for k in detail_markers)

def is_contextual_short_followup(user_text: str) -> bool:
    lower = (user_text or "").lower().strip()
    words = lower.split()
    if not words or len(words) > 4:
        return False

    normalized = " ".join(
        re.sub(r"^[^a-z0-9\u0600-\u06ff']+|[^a-z0-9\u0600-\u06ff']+$", "", w)
        for w in words
    ).strip()
    markers = {
        "yes",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "true",
        "right",
        "exactly",
        "correct",
        "hmm",
        "hmmm",
        "huh",
        "maybe",
        "same",
        "why",
        "how",
        "what",
        "when",
        "where",
        "who",
        "which",
        "why so",
        "how so",
        "ليه",
        "لماذا",
        "كيف",
        "متى",
        "وين",
        "اين",
    }
    return normalized in markers

def clamp_non_detail_response(response_text: str, detailed_mode: bool, response_style: str = "quick") -> str:
    text = (response_text or "").strip()
    if detailed_mode or not text:
        return text

    style = (response_style or "quick").strip().lower()
    if style not in ("quick", "balanced", "detailed"):
        style = "quick"

    max_sentences_by_style = {
        "quick": 2,
        "balanced": 3,
        "detailed": 4,
    }
    max_words_by_style = {
        "quick": 35,
        "balanced": 60,
        "detailed": 90,
    }
    sentence_limit = max_sentences_by_style[style]
    word_limit = max_words_by_style[style]

    cleaned = re.sub(r"[*_`#]+", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    marker_token = "__LIST_DOT__"
    cleaned_for_split = re.sub(r"\b(\d+)\.\s+", rf"\1{marker_token} ", cleaned)

    sentence_parts = re.split(r"(?<=[.!?])\s+", cleaned_for_split)
    concise = " ".join([p.strip() for p in sentence_parts if p.strip()][:sentence_limit]).strip()
    if concise:
        cleaned = concise.replace(marker_token, ".")

    words = cleaned.split()
    if len(words) > word_limit:
        cleaned_for_split = re.sub(r"\b(\d+)\.\s+", rf"\1{marker_token} ", cleaned)
        sentence_parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", cleaned_for_split) if p.strip()]
        kept_sentences = []
        kept_words = 0
        for part in sentence_parts:
            part_words = len(part.split())
            if kept_sentences and (kept_words + part_words > word_limit):
                break
            if not kept_sentences and part_words > word_limit:
                break
            kept_sentences.append(part)
            kept_words += part_words

        if kept_sentences:
            cleaned = " ".join(kept_sentences).replace(marker_token, ".")
        else:
            cleaned = " ".join(words[:word_limit]).rstrip(" ,;:-") + "..."

    return cleaned

def get_personality_voice(profile: dict) -> str:
    personality = profile.get("preferences", {}).get("personality", "therapist").lower().strip()
    if personality == "coach":
        return settings.tts_voice_coach
    if personality == "guide":
        return settings.tts_voice_guide
    return settings.tts_voice_therapist

def _execute_resolved_action(
    resolved: dict,
    profile: dict,
    led: LEDController,
    spotify: SpotifyManager,
    local_music: LocalMusicManager,
    sleep_engine: SleepIntelligenceEngine,
    environment_orchestrator: EnvironmentOrchestrator,
    sleep_routine: SleepRoutineManager,
    routine_engine: RoutineEngine,
    on_sleep_timer_finish,
    store_last_action: bool = True,
) -> tuple[str, bool]:
    intent = str(resolved.get("intent", "") or "").strip().lower()
    slots = resolved.get("slots", {}) if isinstance(resolved.get("slots", {}), dict) else {}
    runtime_flags = profile.setdefault("runtime_flags", {})

    if intent == "undo_last_action":
        last_action = runtime_flags.get("last_action") or {}
        inverse = last_action.get("inverse") if isinstance(last_action, dict) else None
        if not isinstance(inverse, dict) or not inverse:
            return "There is no reversible action to undo yet.", True
        msg, handled = _execute_resolved_action(
            inverse,
            profile,
            led,
            spotify,
            local_music,
            sleep_engine,
            environment_orchestrator,
            sleep_routine,
            routine_engine,
            on_sleep_timer_finish,
            store_last_action=False,
        )
        runtime_flags["last_action"] = {}
        return (f"Done — reverted the last action. {msg}".strip(), handled)

    if intent == "start_wind_down":
        minutes = routine_engine.parse_minutes_from_text(str(slots.get("minutes", "45")), default_minutes=45)
        autopilot_text = sleep_engine.build_wind_down_autopilot(profile, minutes=minutes)
        led.set_user_animation("breathing")
        led.set_user_brightness(0.22)
        music_ok, music_msg = spotify.play_track_query("sleep ambient")
        if not music_ok:
            local_ok, local_msg = local_music.play_query("sleep")
            music_msg = local_msg if local_ok else ""
            music_ok = local_ok
        if music_ok:
            apply_music_led_preferences(led, profile, active=True)
        timer_text = sleep_routine.start_sleep_timer(minutes, on_sleep_timer_finish)
        if store_last_action:
            runtime_flags["last_action"] = {
                "intent": intent,
                "inverse": {"intent": "disable_wind_down", "slots": {}},
            }
        return f"Done — {autopilot_text} {timer_text} {music_msg}".strip(), True

    if intent == "disable_wind_down":
        message = sleep_engine.disable_wind_down_autopilot(profile)
        return message, True

    if intent == "set_scene":
        scene = _scene_payload_from_key(str(slots.get("scene_key", "")), slots)
        scene_line = environment_orchestrator.apply_scene(led, profile, scene)
        if store_last_action:
            runtime_flags["last_action"] = {
                "intent": intent,
                "inverse": {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}},
            }
        partner_line = str(slots.get("partner_line", "")).strip()
        if partner_line:
            return f"Done — {scene_line} {partner_line}".strip(), True
        return f"Done — {scene_line}".strip(), True

    if intent == "play_music":
        query = str(slots.get("query", "") or "").strip()
        ok, msg = spotify.play_track_query(query)
        if (not ok) and query:
            local_ok, local_msg = local_music.play_query(query)
            ok, msg = local_ok, local_msg if local_ok else msg
        if ok:
            apply_music_led_preferences(led, profile, active=True)
        if store_last_action:
            runtime_flags["last_action"] = {
                "intent": intent,
                "inverse": {"intent": "pause_music", "slots": {}},
            }
        return (f"Done — {msg}" if msg else "Done — started audio playback."), True

    if intent == "pause_music":
        ok, msg = spotify.pause()
        if not ok:
            local_ok, local_msg = local_music.pause()
            ok, msg = local_ok, local_msg if local_ok else msg
        if ok:
            apply_music_led_preferences(led, profile, active=False)
        if store_last_action:
            runtime_flags["last_action"] = {
                "intent": intent,
                "inverse": {"intent": "play_music", "slots": {"query": "ambient"}},
            }
        return (f"Done — {msg}" if msg else "Done — paused audio playback."), True

    if intent == "set_response_style":
        prefs = profile.setdefault("preferences", {})
        previous_style = str(prefs.get("response_style", "balanced") or "balanced")
        previous_ack = str(prefs.get("thinking_ack_mode", "minimal") or "minimal")
        style = str(slots.get("response_style", previous_style) or previous_style).strip().lower()
        ack_mode = str(slots.get("thinking_ack_mode", previous_ack) or previous_ack).strip().lower()
        if style in ("quick", "balanced", "detailed"):
            prefs["response_style"] = style
        if ack_mode in ("off", "minimal", "always"):
            prefs["thinking_ack_mode"] = ack_mode
        if store_last_action:
            runtime_flags["last_action"] = {
                "intent": intent,
                "inverse": {
                    "intent": "set_response_style",
                    "slots": {"response_style": previous_style, "thinking_ack_mode": previous_ack},
                },
            }
        return (
            f"Done — response style is now {prefs.get('response_style', 'balanced')}"
            f" with thinking acknowledgements {prefs.get('thinking_ack_mode', 'minimal')}."
        ), True

    return "", False

def get_speed_tuning(profile: dict):
    speed_mode = profile.get("preferences", {}).get("speed_mode", "normal").lower().strip()
    if speed_mode in ("super_fast", "superfast", "ultra"):
        return {
            "quick_timeout": 2,
            "total_timeout": 5,
            "max_tokens": 70,
            "allow_realtime_context": False,
        }

    return {
        "quick_timeout": settings.chat_quick_timeout_seconds,
        "total_timeout": settings.chat_total_timeout_seconds,
        "max_tokens": settings.chat_max_response_tokens,
        "allow_realtime_context": True,
    }

def get_turn_speed_tuning(profile: dict, user_text: str):
    tuning = dict(get_speed_tuning(profile))
    speed_mode = profile.get("preferences", {}).get("speed_mode", "normal").lower().strip()
    words_count = len((user_text or "").split())

    # Keep normal mode responsive on long prompts during laptop testing.
    if speed_mode == "normal" and words_count >= 12:
        tuning["quick_timeout"] = min(int(tuning.get("quick_timeout", 4)), 2)
        tuning["total_timeout"] = min(int(tuning.get("total_timeout", 10)), 5)
        tuning["max_tokens"] = min(int(tuning.get("max_tokens", 120)), 60)
        tuning["allow_realtime_context"] = False

    return tuning

def ensure_progress_shape(profile: dict):
    profile.setdefault("progress", {})
    progress = profile["progress"]
    progress.setdefault("sessions_count", 0)
    progress.setdefault("goals_created", 0)
    progress.setdefault("goals_completed", 0)
    progress.setdefault("last_session_date", "")
    progress.setdefault("last_goal_completion_date", "")
    progress.setdefault("current_streak_days", 0)
    progress.setdefault("best_streak_days", 0)
    progress.setdefault("completion_history_dates", [])

def _is_next_day(prev_iso_date: str, current_iso_date: str) -> bool:
    try:
        prev = datetime.fromisoformat(prev_iso_date).date()
        curr = datetime.fromisoformat(current_iso_date).date()
        return (curr - prev).days == 1
    except Exception:
        return False

def record_goal_completion(profile: dict):
    ensure_progress_shape(profile)
    progress = profile["progress"]
    today_iso = datetime.now().date().isoformat()
    last_completion = str(progress.get("last_goal_completion_date", ""))

    history = progress.get("completion_history_dates", [])
    if today_iso not in history:
        history.append(today_iso)
        progress["completion_history_dates"] = history[-60:]

    if last_completion == today_iso:
        return

    if (not last_completion) or _is_next_day(last_completion, today_iso):
        progress["current_streak_days"] = int(progress.get("current_streak_days", 0)) + 1
    else:
        progress["current_streak_days"] = 1

    progress["best_streak_days"] = max(
        int(progress.get("best_streak_days", 0)),
        int(progress.get("current_streak_days", 0)),
    )
    progress["last_goal_completion_date"] = today_iso

def mark_session_started(profile: dict):
    ensure_progress_shape(profile)
    progress = profile["progress"]
    progress["sessions_count"] = int(progress.get("sessions_count", 0)) + 1
    progress["last_session_date"] = datetime.now().date().isoformat()

def build_progress_summary(profile: dict) -> str:
    ensure_progress_shape(profile)
    progress = profile.get("progress", {})
    created = max(0, int(progress.get("goals_created", 0)))
    completed = max(0, int(progress.get("goals_completed", 0)))
    sessions = max(0, int(progress.get("sessions_count", 0)))
    streak = max(0, int(progress.get("current_streak_days", 0)))

    completion_rate = (completed / created * 100.0) if created else 0.0
    if completion_rate >= 70:
        trend = "strong"
    elif completion_rate >= 40:
        trend = "steady"
    else:
        trend = "building"

    return (
        f"Progress score: completion_rate={completion_rate:.0f}%, trend={trend}, "
        f"sessions={sessions}, goals_created={created}, goals_completed={completed}, streak_days={streak}."
    )

def format_progress_report(profile: dict) -> str:
    ensure_progress_shape(profile)
    progress = profile.get("progress", {})
    created = max(0, int(progress.get("goals_created", 0)))
    completed = max(0, int(progress.get("goals_completed", 0)))
    sessions = max(0, int(progress.get("sessions_count", 0)))
    streak = max(0, int(progress.get("current_streak_days", 0)))
    best_streak = max(0, int(progress.get("best_streak_days", 0)))
    completion_rate = (completed / created * 100.0) if created else 0.0
    trend = "strong" if completion_rate >= 70 else "steady" if completion_rate >= 40 else "building"
    return (
        f"Progress report: sessions={sessions}, goals completed={completed}/{created} "
        f"({completion_rate:.0f}%), trend={trend}, streak={streak} day(s), best_streak={best_streak}."
    )

def format_weekly_review(profile: dict, goal_manager: SessionGoalManager) -> str:
    ensure_progress_shape(profile)
    progress = profile.get("progress", {})
    history = progress.get("completion_history_dates", [])
    today = datetime.now().date()
    recent_completed = 0
    for iso_date in history:
        try:
            d = datetime.fromisoformat(iso_date).date()
            if 0 <= (today - d).days <= 6:
                recent_completed += 1
        except Exception:
            continue

    active_goals = [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]
    top_active = ", ".join(g.get("title", "") for g in active_goals[:2]) or "none"
    return (
        f"Weekly review: completed goals in last 7 days = {recent_completed}. "
        f"Current streak = {int(progress.get('current_streak_days', 0))} day(s). "
        f"Top active goals: {top_active}."
    )

def run_first_boot_intro(tts=None, tts_player=None):
    def _speak(line: str):
        print(line)
        if (tts is None) or (tts_player is None):
            return
        try:
            audio_file = tts.synthesize_to_mp3(
                line.replace("Bed: ", "", 1),
                voice_override=settings.tts_voice_guide,
            )
            if audio_file:
                tts_player.play_file(audio_file)
        except Exception:
            return

    def _ask(prompt: str) -> str:
        _speak(prompt)
        return input("You: ").strip()

    def _is_cancel(text: str) -> bool:
        return (text or "").strip().lower() in ("exit", "quit", "bye")

    _speak("Bed: Hello, I am your Smart Bed.")
    _speak("Bed: I will ask just two quick questions to get started.")

    while True:
        raw_name = _ask("Bed: What is your name? ")
        if _is_cancel(raw_name):
            _speak("Bed: Setup cancelled.")
            return None
        if raw_name and raw_name.lower() not in ("wake", "hey smart bed"):
            name = raw_name
            break
        _speak("Bed: Please enter a valid name, or type exit to cancel setup.")

    while True:
        raw_age = _ask("Bed: How old are you? ")
        if _is_cancel(raw_age):
            _speak("Bed: Setup cancelled.")
            return None
        if raw_age.isdigit() and 5 <= int(raw_age) <= 120:
            age = str(int(raw_age))
            break
        _speak("Bed: Please enter a valid age between 5 and 120.")

    personality = "therapist"
    favorite_color = None
    user_animation = "solid"
    sleep_target_hours = 8.0
    adaptive_wake_enabled = True
    wind_down_minutes = 45

    profile = {
        "name": name,
        "age": age,
        "gender": None,
        "education": None,
        "preferences": {
            "favorite_color": favorite_color,
            "personality": personality,
            "language": "auto",
            "audio_output_mode": "bed_speaker",
            "bluetooth_speaker_name": "",
            "bluetooth_speaker_mac": "",
            "user_strip_animation": user_animation,
            "music_lights_enabled": True,
            "music_lights_mode": "pulse",
            "music_lights_energy": "calm",
            "music_lights_target": "both",
            "music_lights_brightness_percent": 35,
            "music_lights_night_brightness_percent": 35,
            "data_retention_days": 14,
            "thinking_ack_mode": "minimal",
            "response_style": "balanced",
            "engagement_level": "high",
            "speed_mode": "normal",
            "guide_level": "beginner",
            "quiet_window": str(settings.quiet_hours_default_window or "22:00-07:00"),
            "sleep_target_hours": sleep_target_hours,
            "adaptive_wake_enabled": adaptive_wake_enabled,
        },
        "progress": {
            "sessions_count": 0,
            "goals_created": 0,
            "goals_completed": 0,
            "last_session_date": "",
        },
        "hardware": {
            "user_strip_pin": int(settings.user_strip_pin),
            "state_strip_pin": int(settings.state_strip_pin),
            "user_strip_led_count": int(settings.user_strip_led_count),
            "state_strip_led_count": int(settings.state_strip_led_count),
        },
        "sleep": {
            "bedtime_history": [],
            "wake_history": [],
            "recovery_mode": False,
            "recovery_reason": "",
            "challenge_level": 1,
            "challenge_last_adjust_date": "",
            "wind_down_enabled": True,
            "wind_down_minutes": wind_down_minutes,
            "night_wake_count": 0,
            "last_night_wake_date": "",
            "last_decompression_date": "",
            "last_weekly_insights_date": "",
        },
        "onboarding": {
            "first_boot_completed": True,
            "first_boot_completed_at": datetime.now().isoformat(timespec="seconds"),
            "help_hints_seen": [],
            "optional_profile_pending": True,
            "optional_profile_prompts_asked": [],
        },
    }
    save_profile(profile)

    _speak(f"Bed: Nice to meet you, {name}. I will remember your information.")
    _speak(
        "Bed: First-boot guide -> Say 'wake' to start and ask naturally. "
        "We can set your personality, colors, and sleep preferences anytime later when you need them. "
        "For quick help say: 'help' or 'sleep help'. You can also say 'bed tutorial' for guided steps."
    )
    return profile

def ensure_profile_shape(profile: dict):
    profile.setdefault("age", "?")
    profile.setdefault("preferences", {})
    profile["preferences"].setdefault("favorite_color", None)
    profile["preferences"].setdefault("personality", "therapist")
    profile["preferences"].setdefault("language", "auto")
    profile["preferences"].setdefault("audio_output_mode", "bed_speaker")
    profile["preferences"].setdefault("bluetooth_speaker_name", "")
    profile["preferences"].setdefault("bluetooth_speaker_mac", "")
    profile["preferences"].setdefault("user_strip_animation", "solid")
    profile["preferences"].setdefault("music_lights_night_brightness_percent", 35)
    profile["preferences"].setdefault("data_retention_days", 14)
    profile["preferences"].setdefault("thinking_ack_mode", "minimal")
    profile["preferences"].setdefault("response_style", "balanced")
    profile["preferences"].setdefault("engagement_level", "high")
    profile["preferences"].setdefault("speed_mode", "normal")
    profile["preferences"].setdefault("guide_level", "beginner")
    profile["preferences"].setdefault("quiet_window", str(settings.quiet_hours_default_window or "22:00-07:00"))
    profile["preferences"].setdefault("quiet_mode_active", False)
    profile["preferences"].setdefault("quiet_hours_override_until_utc", "")
    profile["preferences"].setdefault("timezone", "UTC")
    profile["preferences"].setdefault("fajr_light_time", "04:50")
    profile["preferences"].setdefault("sleep_target_hours", 8.0)
    profile["preferences"].setdefault("adaptive_wake_enabled", True)
    profile["preferences"].setdefault("therapist_followup_tone", "soft")
    profile["preferences"].setdefault("bed_nickname", "")
    profile["preferences"].setdefault("wake_aliases", [])
    ensure_emotional_followup_shape(profile)
    ensure_music_led_preferences(profile)
    profile.setdefault("onboarding", {})
    profile["onboarding"].setdefault("first_boot_completed", True)
    profile["onboarding"].setdefault("first_boot_completed_at", "")
    profile["onboarding"].setdefault("bed_phase_completed", False)
    profile["onboarding"].setdefault("bed_phase_completed_at", "")
    profile["onboarding"].setdefault("help_hints_seen", [])
    profile["onboarding"].setdefault("optional_profile_pending", False)
    profile["onboarding"].setdefault("optional_profile_prompts_asked", [])
    profile["onboarding"].setdefault("bed_guide_completed", False)
    ensure_progress_shape(profile)
    ensure_hardware_shape(profile)
    return profile

def _is_simple_yes(text: str) -> bool:
    normalized = normalize_for_intent(text)
    yes_tokens = {"yes", "yeah", "yep", "ok", "okay", "sure", "confirm", "نعم", "اوكي", "تمام"}
    if normalized in yes_tokens:
        return True
    return bool(set(normalized.split()).intersection(yes_tokens))

def _is_simple_no(text: str) -> bool:
    normalized = normalize_for_intent(text)
    no_tokens = {"no", "cancel", "stop", "لا", "الغاء", "إلغاء"}
    if normalized in no_tokens:
        return True
    return bool(set(normalized.split()).intersection(no_tokens))

def _is_app_exit_command(text: str) -> bool:
    normalized = normalize_for_intent(text)
    return normalized in {"exit", "quit"}

def _is_session_end_command(text: str) -> bool:
    normalized = normalize_for_intent(text)
    if not normalized:
        return False

    exact = {
        "bye",
        "goodbye",
        "good bye",
        "bye bye",
        "ok bye",
        "okay bye",
        "sleep mode",
        "stop listening",
        "good night",
    }
    if normalized in exact:
        return True

    return any(
        phrase in normalized
        for phrase in (
            "bye",
            "goodbye",
            "good bye",
            "sleep mode",
            "stop listening",
            "good night",
        )
    )

def _is_wake_only_utterance(wake_word_manager: WakeWordManager, text: str) -> bool:
    normalized = normalize_for_intent(text)
    if not normalized:
        return False

    filler_tokens = {
        "hey",
        "hi",
        "hello",
        "wake",
        "ok",
        "okay",
        "yo",
        "please",
        "يا",
        "لو",
        "طيب",
    }
    wake_tokens = {token for token in normalize_for_intent(wake_word_manager.wake_word).split() if token}
    for alias in wake_word_manager.get_wake_phrases():
        wake_tokens.update(token for token in normalize_for_intent(alias).split() if token)

    utterance_tokens = [token for token in normalized.split() if token]
    if not utterance_tokens:
        return False

    allowed_tokens = wake_tokens | filler_tokens
    if all(token in allowed_tokens for token in utterance_tokens):
        return True
    return False

def _resolve_followup_control_intent(user_text: str, profile: dict) -> tuple[str, dict]:
    normalized = normalize_for_intent(user_text)
    if not normalized:
        return "", {}

    runtime_flags = profile.get("runtime_flags", {}) if isinstance(profile, dict) else {}
    last_action = runtime_flags.get("last_action", {}) if isinstance(runtime_flags, dict) else {}
    last_intent = str(last_action.get("intent", "") or "").strip().lower()

    if last_intent in {"set_scene", "set_color", "brightness_up", "brightness_down", "brightness_set"}:
        if has_any(normalized, ("brighter", "more", "increase", "higher", "up", "زيد", "ارفع")):
            return "brightness_up", {}
        if has_any(normalized, ("dimmer", "dim", "less", "decrease", "lower", "down", "خف", "قلل")):
            return "brightness_down", {}

        brightness_match = re.search(r"(\d{1,3})\s*%?", normalized)
        if brightness_match and (
            ("%" in user_text)
            or has_any(normalized, ("percent", "brightness", "bright", "سطوع", "اضاءة", "إضاءة"))
        ):
            return "brightness_set", {"brightness_percent": int(brightness_match.group(1))}

        color_value = _extract_color_from_normalized_text(normalized)
        if color_value:
            return "set_color", {"color": color_value}

    if last_intent in {"play_music", "pause_music"}:
        if has_any(normalized, ("pause", "stop", "quiet", "وقف", "ايقاف", "إيقاف")):
            return "pause_music_followup", {}
        if has_any(normalized, ("resume", "continue", "play", "كمل", "كمل", "تشغيل", "شغل")):
            return "resume_music_followup", {}

    return "", {}

def _detect_compound_control_intents(user_text: str, profile: dict, breathing_offer_active: bool = False) -> list[dict]:
    raw = str(user_text or "").strip()
    if not raw:
        return []

    connector_pattern = r"\s*(?:,| and then | then | and | also | plus | بعدها | ثم | وبعدين |\sو\s)\s*"
    parts = [p.strip(" ,.;") for p in re.split(connector_pattern, raw, flags=re.IGNORECASE) if p.strip(" ,.;")]
    if len(parts) < 2:
        return []

    allowed = {
        "set_color",
        "brightness_up",
        "brightness_down",
        "brightness_set",
        "play_music",
        "pause_music",
        "resume_music_followup",
        "pause_music_followup",
        "start_wind_down",
    }

    steps: list[dict] = []
    for part in parts:
        intent, payload = detect_natural_bed_intent(part, breathing_offer_active=breathing_offer_active)
        if intent in allowed:
            steps.append({"intent": intent, "slots": dict(payload or {})})
            continue

        followup_intent, followup_payload = _resolve_followup_control_intent(part, profile)
        if followup_intent in allowed:
            steps.append({"intent": followup_intent, "slots": dict(followup_payload or {})})
            continue

        resolved = resolve_action(part, profile, context={"breathing_offer_active": breathing_offer_active})
        resolved_intent = str(resolved.get("intent", "") or "").strip().lower()
        confidence = float(resolved.get("confidence", 0.0) or 0.0)
        if resolved_intent in allowed and confidence >= 0.74:
            slots = resolved.get("slots", {}) if isinstance(resolved.get("slots", {}), dict) else {}
            steps.append({"intent": resolved_intent, "slots": slots})

    if len(steps) < 2:
        return []
    return steps

def _execute_compound_control_steps(
    steps: list[dict],
    profile: dict,
    led: LEDController,
    spotify: SpotifyManager,
    local_music: LocalMusicManager,
    sleep_engine: SleepIntelligenceEngine,
    environment_orchestrator: EnvironmentOrchestrator,
    sleep_routine: SleepRoutineManager,
    routine_engine: RoutineEngine,
    on_sleep_timer_finish,
) -> tuple[str, bool]:
    if not steps:
        return "", False

    runtime_flags = profile.setdefault("runtime_flags", {})
    lines: list[str] = []
    handled_any = False

    for step in steps:
        intent = str(step.get("intent", "") or "").strip().lower()
        slots = step.get("slots", {}) if isinstance(step.get("slots", {}), dict) else {}

        if intent in {"start_wind_down", "play_music", "pause_music"}:
            msg, handled = _execute_resolved_action(
                {"intent": intent, "slots": slots},
                profile,
                led,
                spotify,
                local_music,
                sleep_engine,
                environment_orchestrator,
                sleep_routine,
                routine_engine,
                on_sleep_timer_finish,
            )
            if handled:
                handled_any = True
                if msg:
                    lines.append(msg)
            continue

        if intent == "resume_music_followup":
            ok, message = spotify.resume()
            if (not ok) and should_use_local_music_fallback(message):
                ok, message = local_music.resume()
            if ok:
                apply_music_led_preferences(led, profile, active=True)
                runtime_flags["last_action"] = {
                    "intent": "play_music",
                    "inverse": {"intent": "pause_music", "slots": {}},
                }
                handled_any = True
                lines.append(message or "Resumed audio playback.")
            continue

        if intent == "pause_music_followup":
            ok, message = spotify.pause()
            if (not ok) and should_use_local_music_fallback(message):
                ok, message = local_music.pause()
            if ok:
                apply_music_led_preferences(led, profile, active=False)
                runtime_flags["last_action"] = {
                    "intent": "pause_music",
                    "inverse": {"intent": "play_music", "slots": {"query": "ambient"}},
                }
                handled_any = True
                lines.append(message or "Paused audio playback.")
            continue

        if intent == "brightness_up":
            led.brightness_up()
            runtime_flags["last_action"] = {
                "intent": "brightness_up",
                "inverse": {"intent": "brightness_down", "slots": {}},
            }
            handled_any = True
            lines.append("Made the lights brighter.")
            continue

        if intent == "brightness_down":
            led.brightness_down()
            runtime_flags["last_action"] = {
                "intent": "brightness_down",
                "inverse": {"intent": "brightness_up", "slots": {}},
            }
            handled_any = True
            lines.append("Dimmed the lights.")
            continue

        if intent == "brightness_set":
            percent = _clamp_percent(slots.get("brightness_percent", 40), default_value=40)
            led.set_user_brightness(percent / 100.0)
            runtime_flags["last_action"] = {
                "intent": "brightness_set",
                "inverse": {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}},
            }
            handled_any = True
            lines.append(f"Set brightness to {percent}%.")
            continue

        if intent == "set_color":
            color_value = str(slots.get("color", "") or "").strip()
            if color_value:
                led.set_color_value(color_value)
                profile.setdefault("preferences", {})["favorite_color"] = color_value
                runtime_flags["last_action"] = {
                    "intent": "set_color",
                    "inverse": {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}},
                }
                handled_any = True
                lines.append(f"Changed lights to {color_value}.")

    if handled_any:
        save_profile(profile)
        merged = " ".join(line.strip() for line in lines if line.strip())
        return merged.strip(), True
    return "", False

def _split_for_fast_tts_start(text: str, head_limit_chars: int = 140) -> tuple[str, str]:
    content = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(content) <= head_limit_chars:
        return content, ""

    punctuation_points = [
        idx
        for idx, ch in enumerate(content[:head_limit_chars])
        if ch in ".!?;:"
    ]
    if punctuation_points:
        split_at = punctuation_points[-1] + 1
    else:
        split_at = content.rfind(" ", max(50, head_limit_chars - 50), head_limit_chars)
        if split_at <= 0:
            split_at = head_limit_chars

    head = content[:split_at].strip()
    tail = content[split_at:].strip()
    return head, tail

def _infer_interim_intent_hint(text: str) -> dict:
    normalized = normalize_for_intent(text)
    if not normalized:
        return {}

    words = [w for w in normalized.split(" ") if w]
    has = lambda *tokens: any(t in normalized for t in tokens)

    if has("set alarm", "alarm for", "wake me"):
        return {"intent": "set_alarm", "category": "control", "normalized": normalized}
    if "timer" in words and has("set", "start", "for"):
        return {"intent": "set_timer", "category": "control", "normalized": normalized}
    if has("pause music", "pause spotify", "stop music"):
        return {"intent": "music_pause", "category": "control", "normalized": normalized}
    if has("resume music", "play music", "play spotify"):
        return {"intent": "music_play", "category": "control", "normalized": normalized}
    if has("next song", "skip song", "previous song", "prev song"):
        return {"intent": "music_transport", "category": "control", "normalized": normalized}

    led_action, _slots, _confidence = detect_led_command(text)
    if led_action:
        return {"intent": "lighting", "category": "control", "normalized": normalized}

    return {}

def play_tts_with_fast_start(
    tts: TTSManager,
    tts_player: AudioPlaybackController,
    text: str,
    voice_override: str = "",
    pace_override: float = 1.0,
    emotion_state: str = "neutral",
    profile_override: str = "",
) -> str:
    text_to_speak = str(text or "").strip()
    if not text_to_speak:
        return ""

    def _synthesize_segment(segment_text: str, filename: str) -> str | None:
        try:
            return tts.synthesize_to_mp3(
                segment_text,
                filename=filename,
                voice_override=voice_override,
                pace_override=pace_override,
                emotion_state=emotion_state,
                profile_override=profile_override,
            )
        except TypeError:
            # Backward compatibility with older/mock TTS adapters.
            return tts.synthesize_to_mp3(
                segment_text,
                filename=filename,
                voice_override=voice_override,
                pace_override=pace_override,
            )

    head_text, tail_text = _split_for_fast_tts_start(text_to_speak)
    head_filename = "latest_response_head.mp3" if tail_text else "latest_response.mp3"
    first_audio_path = _synthesize_segment(head_text, head_filename)
    if not first_audio_path:
        print("[TTS][WARN] No playable TTS audio produced; skipping playback.")
        return ""

    print(f"[AUDIO] Playback path: {first_audio_path}")
    print(f"[AUDIO] pygame playback starting: {first_audio_path}")
    played = tts_player.play_file(first_audio_path)
    print(f"[AUDIO] pygame playback finished: {first_audio_path} (played={played})")

    if tail_text:
        tail_audio_path = _synthesize_segment(tail_text, "latest_response_tail.mp3")
        if tail_audio_path:
            queued = tts_player.queue_file(tail_audio_path)
            if (not queued) and (not tts_player.is_playing()):
                tts_player.play_file(tail_audio_path)

    return first_audio_path

def run_streaming_voice_turn(
    *,
    chat: ConversationEngine,
    realtime_voice_pipeline: RealtimeVoicePipeline,
    filler_manager: ConversationalFillerManager,
    barge_in_monitor: ContinuousBargeInMonitor,
    echo_guard: AcousticEchoGuard,
    tts: TTSManager,
    tts_player: AudioPlaybackController,
    led: LEDController,
    environment_orchestrator: EnvironmentOrchestrator,
    profile: dict,
    user_text_for_ai: str,
    personality: str,
    realtime_context: str,
    user_context: str,
    emotion_state: str,
    cognitive_load_mode: str,
    voice_override: str,
    profile_override: str,
    pace_override: float,
    total_timeout_seconds: int,
    max_response_tokens: int,
) -> tuple[str, str]:
    interrupted = {"text": ""}
    first_chunk_seen = threading.Event()
    watch_stop = threading.Event()

    def _should_stop() -> bool:
        return bool(interrupted["text"])

    def _on_barge_in(text: str, confidence: float):
        if not echo_guard.should_accept_barge_in(
            playback_active=tts_player.is_playing(),
            text=text,
            confidence=confidence,
        ):
            return
        interrupted["text"] = str(text or "").strip()
        tts_player.stop()
        led.set_state("listening")

    stream_started_at = time.monotonic()

    def _filler_watcher():
        while (not watch_stop.is_set()) and (not first_chunk_seen.is_set()) and (not _should_stop()):
            elapsed = time.monotonic() - stream_started_at
            if filler_manager.should_play(elapsed) and tts_player.is_ready():
                filler = filler_manager.pick()
                if filler:
                    filler_audio = tts.synthesize_to_mp3(
                        filler,
                        filename="thinking_filler.mp3",
                        voice_override=voice_override,
                        pace_override=1.05,
                        emotion_state=emotion_state,
                        profile_override=profile_override,
                    )
                    if filler_audio:
                        tts_player.play_file(filler_audio)
                return
            time.sleep(0.05)

    watcher = threading.Thread(target=_filler_watcher, name="filler-watcher", daemon=True)
    watcher.start()

    barge_in_monitor.start(_on_barge_in)
    response_text = ""
    try:
        def _on_preload_phase(phase: str):
            if phase:
                environment_orchestrator.preload_transition_for_response(led, profile, phase)

        def _chunk_source():
            for chunk in chat.generate_response_stream(
                user_text_for_ai,
                personality=personality,
                realtime_context=realtime_context,
                user_context=user_context,
                emotion_state=emotion_state,
                cognitive_load_mode=cognitive_load_mode,
                total_timeout_seconds=total_timeout_seconds,
                max_response_tokens=max_response_tokens,
            ):
                if _should_stop():
                    break
                text_chunk = str(chunk or "")
                if text_chunk:
                    first_chunk_seen.set()
                    yield text_chunk

        response_text = realtime_voice_pipeline.speak_from_voice_agent_stream(
            _chunk_source(),
            voice_override=voice_override,
            pace_override=pace_override,
            emotion_state=emotion_state,
            profile_override=profile_override,
            should_stop=_should_stop,
            on_preload_start=_on_preload_phase,
        )
    finally:
        watch_stop.set()
        first_chunk_seen.set()
        barge_in_monitor.stop()

    return response_text, interrupted["text"]

def get_query_text(
    stt_manager: STTManager,
    wake_word_manager: WakeWordManager,
    interim_intent_callback=None,
    require_api_stream: bool = False,
) -> tuple[str, float]:
    if wake_word_manager.is_voice_available():
        text, confidence = "", 0.0
        stream_capture = getattr(stt_manager, "transcribe_microphone_with_interim", None)
        if callable(stream_capture):
            phrase_limit = wake_word_manager.get_voice_phrase_limit_seconds()
            max_phrase_seconds = float(phrase_limit) if isinstance(phrase_limit, int) and phrase_limit > 0 else 16.0
            last_interim = {"text": ""}
            last_hint = {"key": ""}
            active_mic_index = wake_word_manager.get_active_mic_index()

            def _on_interim(interim_text: str, _score: float):
                cleaned = str(interim_text or "").strip()
                if not cleaned:
                    return
                if cleaned == last_interim["text"]:
                    return
                last_interim["text"] = cleaned
                print(f"Bed (interim): {cleaned}")

                if interim_intent_callback is None:
                    return
                hint = _infer_interim_intent_hint(cleaned)
                if not hint:
                    return
                hint_key = f"{hint.get('intent', '')}|{hint.get('normalized', '')}"
                if hint_key == last_hint["key"]:
                    return
                last_hint["key"] = hint_key
                interim_intent_callback(hint)

            text, confidence = stream_capture(
                mic_device_index=active_mic_index,
                timeout_seconds=wake_word_manager.voice_timeout_seconds,
                max_phrase_seconds=max_phrase_seconds,
                silence_end_seconds=0.8,
                interim_callback=_on_interim,
            )

            should_retry_default_mic = (
                (not text)
                and require_api_stream
                and isinstance(active_mic_index, int)
                and active_mic_index >= 0
            )
            if should_retry_default_mic:
                print("Bed: Deepgram live STT retrying on default microphone...")
                text, confidence = stream_capture(
                    mic_device_index=None,
                    timeout_seconds=wake_word_manager.voice_timeout_seconds,
                    max_phrase_seconds=max_phrase_seconds,
                    silence_end_seconds=0.8,
                    interim_callback=_on_interim,
                )
            if text:
                print("Bed: STT source -> Deepgram live stream.")
            elif require_api_stream:
                now = time.time()
                last_warning_at = float(getattr(get_query_text, "_strict_stt_last_warning_at", 0.0) or 0.0)
                if now - last_warning_at >= 4.0:
                    print("Bed: Deepgram live STT did not capture speech. Strict stream mode is enabled, so fallback STT is disabled.")
                    setattr(get_query_text, "_strict_stt_last_warning_at", now)
                time.sleep(0.18)
                return "", 0.0

        if not text:
            print("Bed: STT source -> Wake-word fallback recognizer.")
            text, confidence = wake_word_manager.get_user_text_with_confidence()
        if not text:
            return "", 0.0

        print(f"Bed (voice): {text}")

        if confidence < LISTEN_CONFIDENCE_MIN_ACCEPT_THRESHOLD:
            print("Bed: I did not catch that clearly. Please repeat your command.")
            return "", 0.0

        if confidence >= LISTEN_CONFIDENCE_CONFIRM_THRESHOLD:
            return text, confidence
        return text, max(confidence, LISTEN_CONFIDENCE_CONFIRM_THRESHOLD)

    print("Bed: Say your command as text, or type audio:<path-to-wav>")
    raw = input("You: ").strip()

    if raw.lower().startswith("audio:"):
        audio_path = raw.split(":", 1)[1].strip().strip('"')
        text, confidence = stt_manager.transcribe_file_with_confidence(audio_path)
        if text:
            print(f"Bed (STT): {text}")
            if confidence < LISTEN_CONFIDENCE_MIN_ACCEPT_THRESHOLD:
                print("Bed: STT confidence is low. Please repeat your command.")
                return "", 0.0
            return text, max(confidence, LISTEN_CONFIDENCE_CONFIRM_THRESHOLD)
        print("Bed: STT failed. Please type your command.")
        retry = input("You (text fallback): ").strip()
        return retry, 1.0 if retry else 0.0

    return raw, 1.0 if raw else 0.0

def handle_local_commands(
    user_text: str,
    profile: dict,
    led: LEDController,
    spotify: SpotifyManager,
    local_music: LocalMusicManager,
    schedule: ScheduleManager,
    goal_manager: SessionGoalManager,
    daily_life_support: DailyLifeSupport,
    goal_compass: GoalCompass,
    sleep_engine: SleepIntelligenceEngine,
    environment_orchestrator: EnvironmentOrchestrator,
    runtime_orchestrator: PersonalityRuntimeOrchestrator,
    goal_strategy: GoalStrategyEngine,
    sleep_routine: SleepRoutineManager,
    routine_engine: RoutineEngine,
    tts_player: AudioPlaybackController,
    audio_output: AudioOutputManager,
    backend_client,
    health_report_builder,
    on_sleep_timer_finish,
    breathing_guide: BreathingGuideEngine,
    dream_journal: DreamJournalManager,
    adaptive_personality: AdaptivePersonalityEngine,
    proactive_engine: ProactiveAutomationEngine | None = None,
    signature_engine: SignatureExperienceEngine | None = None,
    tts: TTSManager | None = None,
    wake_word_manager: WakeWordManager | None = None,
    memory_store: LongTermMemoryStore | None = None,
):
    lower = user_text.lower().strip()
    normalized_lower = re.sub(r"[^a-z0-9\s']+", " ", lower)
    runtime_flags = profile.setdefault("runtime_flags", {})
    runtime_flags.setdefault("bed_guide_active", False)
    runtime_flags.setdefault("bed_guide_step_index", 0)
    runtime_flags.setdefault("last_action", {})
    runtime_flags.setdefault("pending_action_resolve", {})
    if runtime_flags.get("session_locked_after_delete"):
        return "Local data was deleted. Please restart so I can run fresh setup.", True

    reflection_response, reflection_handled, reflection_state_changed = process_reflection_turn(
        user_text=user_text,
        profile=profile,
        timeout_hours=12,
    )
    if reflection_state_changed:
        save_profile(profile)
    if reflection_handled:
        return reflection_response, True

    if proactive_engine is None:
        class _NoOpProactiveEngine:
            @staticmethod
            def daily_summary(_profile: dict) -> str:
                return "No proactive summary is available yet."

        proactive_engine = _NoOpProactiveEngine()

    if signature_engine is None:
        class _NoOpSignatureEngine:
            @staticmethod
            def run(*_args, **_kwargs):
                return "", False

        signature_engine = _NoOpSignatureEngine()

    if memory_store is None:
        class _NoOpMemoryStore:
            @staticmethod
            def inject_daily_events(*_args, **_kwargs) -> int:
                return 0

            @staticmethod
            def latest_daily_events_summary(*_args, **_kwargs) -> str:
                return ""

            @staticmethod
            def memory_prompt_line(*_args, **_kwargs) -> str:
                return ""

            @staticmethod
            def infer_invisible_routine(*_args, **_kwargs) -> dict:
                return {}

            @staticmethod
            def record_turn(*_args, **_kwargs):
                return None

        memory_store = _NoOpMemoryStore()

    if tts is None:
        class _NoOpTTS:
            @staticmethod
            def synthesize_to_mp3(*_args, **_kwargs):
                return ""

        tts = _NoOpTTS()

    if wake_word_manager is None:
        class _NoOpWakeWordManager:
            wake_word = "hey smart bed"

            @staticmethod
            def set_wake_aliases(*_args, **_kwargs):
                return None

            @staticmethod
            def get_wake_phrases() -> list[str]:
                return ["hey smart bed"]

        wake_word_manager = _NoOpWakeWordManager()

    prefs = ensure_music_led_preferences(profile)
    breathing_offer_active = bool(runtime_flags.get("breathing_offer_active", False))
    natural_intent, natural_payload = detect_natural_bed_intent(user_text, breathing_offer_active)
    if not natural_intent:
        followup_intent, followup_payload = _resolve_followup_control_intent(user_text, profile)
        if followup_intent:
            natural_intent = followup_intent
            natural_payload = followup_payload

    if bool(runtime_flags.get("bed_guide_active", False)):
        shortcut_intent = resolve_bed_guide_shortcut_intent(user_text)
        if shortcut_intent and natural_intent not in {
            "bed_guide_start",
            "bed_guide_next",
            "bed_guide_repeat",
            "bed_guide_stop",
        }:
            natural_intent = shortcut_intent

    if runtime_flags.get("awaiting_data_delete_confirm"):
        confirm_tokens = (
            "yes",
            "yeah",
            "yep",
            "confirm",
            "delete",
            "ok",
            "okay",
            "proceed",
            "وافق",
            "تأكيد",
            "احذف",
        )
        cancel_tokens = (
            "no",
            "cancel",
            "stop",
            "abort",
            "لا",
            "الغاء",
            "إلغاء",
            "خلاص",
        )
        cancel_phrases = ("never mind", "nevermind")
        tokens = set(normalized_lower.split())
        raw_tokens = set(re.findall(r"[\w']+", lower, flags=re.UNICODE))
        if (
            normalized_lower in cancel_tokens
            or lower in cancel_tokens
            or bool(tokens.intersection(cancel_tokens))
            or bool(raw_tokens.intersection(cancel_tokens))
            or any(phrase in normalized_lower for phrase in cancel_phrases)
            or any(phrase in lower for phrase in cancel_phrases)
        ):
            runtime_flags["awaiting_data_delete_confirm"] = False
            save_profile(profile)
            return "Data deletion cancelled.", True
        if bool(tokens.intersection(confirm_tokens)) or bool(raw_tokens.intersection(confirm_tokens)):
            runtime_flags["awaiting_data_delete_confirm"] = False
            if delete_profile(profile=profile):
                profile.clear()
                profile["runtime_flags"] = {"session_locked_after_delete": True}
                return "Current user data was deleted on this device. Shared subscription records were kept. Please restart so I can run fresh setup.", True
            return "I could not delete local data right now. Please try again.", True
        return "Please say confirm or cancel.", True

    if runtime_flags.get("awaiting_bed_nickname"):
        nickname_candidate = normalize_for_intent(user_text)
        if nickname_candidate in ("cancel", "stop", "never mind", "nevermind", "خلاص", "الغاء", "إلغاء"):
            runtime_flags["awaiting_bed_nickname"] = False
            save_profile(profile)
            return "Okay, nickname setup cancelled.", True
        if not nickname_candidate:
            return "Please say the nickname you want to use.", True

        nickname_words = [w for w in nickname_candidate.split(" ") if w]
        if len(nickname_words) > 3:
            return "Please keep it short (1 to 3 words). Example: baby or moon light.", True

        nickname = apply_bed_nickname(profile, wake_word_manager, nickname_candidate)
        runtime_flags["awaiting_bed_nickname"] = False
        save_profile(profile)
        return f"Done. You can wake me with '{nickname}' now.", True

    pending_action = runtime_flags.get("pending_action_resolve", {})
    if isinstance(pending_action, dict) and pending_action.get("intent"):
        normalized = normalize_for_intent(user_text)
        if _is_simple_yes(normalized):
            runtime_flags["pending_action_resolve"] = {}
            msg, handled = _execute_resolved_action(
                pending_action,
                profile,
                led,
                spotify,
                local_music,
                sleep_engine,
                environment_orchestrator,
                sleep_routine,
                routine_engine,
                on_sleep_timer_finish,
            )
            save_profile(profile)
            return msg, handled
        if _is_simple_no(normalized):
            runtime_flags["pending_action_resolve"] = {}
            save_profile(profile)
            return "Got it — cancelled.", True

        if str(pending_action.get("intent", "")).strip().lower() == "set_scene":
            scene_followup = _resolve_scene_clarification_followup(user_text)
            if scene_followup:
                runtime_flags["pending_action_resolve"] = {}
                msg, handled = _execute_resolved_action(
                    scene_followup,
                    profile,
                    led,
                    spotify,
                    local_music,
                    sleep_engine,
                    environment_orchestrator,
                    sleep_routine,
                    routine_engine,
                    on_sleep_timer_finish,
                )
                save_profile(profile)
                return msg, handled
            if _is_scene_clarification_candidate(user_text):
                return "Please say 'keep normal brightness' or 'set a calm dim scene'.", True

            runtime_flags["pending_action_resolve"] = {}
            save_profile(profile)

    compound_steps = _detect_compound_control_intents(
        user_text,
        profile,
        breathing_offer_active=breathing_offer_active,
    )
    if compound_steps:
        message, handled = _execute_compound_control_steps(
            compound_steps,
            profile,
            led,
            spotify,
            local_music,
            sleep_engine,
            environment_orchestrator,
            sleep_routine,
            routine_engine,
            on_sleep_timer_finish,
        )
        if handled:
            return message, True

    if lower in ("what did you auto-manage today", "auto manage summary", "proactive summary status"):
        return proactive_engine.daily_summary(profile), True

    signature_response, signature_handled = signature_engine.run(
        user_text,
        profile,
        sleep_engine,
        environment_orchestrator,
        led,
        spotify,
        local_music,
    )
    if signature_handled:
        runtime_flags["last_action"] = {
            "intent": "signature_mode",
            "inverse": {"intent": "pause_music", "slots": {}},
        }
        save_profile(profile)
        return signature_response, True

    optimize_room_phrases = (
        "optimize my room for sleep",
        "optimize room for sleep",
        "optimize sleep room",
        "sleep optimize room",
    )
    if lower not in optimize_room_phrases:
        resolved = resolve_action(user_text, profile, context={"breathing_offer_active": breathing_offer_active})
        confidence = float(resolved.get("confidence", 0.0) or 0.0)
        if confidence >= 0.78:
            msg, handled = _execute_resolved_action(
                resolved,
                profile,
                led,
                spotify,
                local_music,
                sleep_engine,
                environment_orchestrator,
                sleep_routine,
                routine_engine,
                on_sleep_timer_finish,
            )
            if handled:
                runtime_flags["pending_action_resolve"] = {}
                save_profile(profile)
                return msg, True
        elif 0.45 <= confidence < 0.78 and str(resolved.get("clarify_question", "")).strip():
            runtime_flags["pending_action_resolve"] = resolved
            save_profile(profile)
            return str(resolved.get("clarify_question", "")).strip(), True

    if natural_intent == "nickname_setup":
        runtime_flags["awaiting_bed_nickname"] = True
        save_profile(profile)
        return "Sure. What nickname do you want for me?", True

    if natural_intent == "set_bed_nickname":
        nickname = apply_bed_nickname(profile, wake_word_manager, str(natural_payload.get("nickname", "")))
        if not nickname:
            runtime_flags["awaiting_bed_nickname"] = True
            save_profile(profile)
            return "Tell me the nickname you want, and I will set it.", True
        runtime_flags["awaiting_bed_nickname"] = False
        save_profile(profile)
        return f"Bed nickname set to '{nickname}'. You can wake me with it now.", True

    if natural_intent == "clear_bed_nickname":
        profile.setdefault("preferences", {})["bed_nickname"] = ""
        runtime_flags["awaiting_bed_nickname"] = False
        wake_word_manager.set_wake_aliases(build_wake_aliases_from_profile(profile))
        save_profile(profile)
        return "Bed nickname cleared. Default wake phrase remains active.", True

    if natural_intent == "get_bed_nickname":
        nickname = str(prefs.get("bed_nickname", "") or "").strip()
        if nickname:
            return f"My nickname is {nickname}.", True
        return (
            "I do not have a nickname yet. You can set one naturally, like: 'JoJo is your nickname.'",
            True,
        )

    if natural_intent == "show_wake_names":
        phrases = wake_word_manager.get_wake_phrases()
        return "Wake phrases: " + " | ".join(phrases), True

    if natural_intent == "bed_guide_start":
        runtime_flags["bed_guide_active"] = True
        runtime_flags["bed_guide_step_index"] = 0
        save_profile(profile)
        return render_bed_guide_step(0), True

    if natural_intent == "bed_guide_next":
        if not bool(runtime_flags.get("bed_guide_active", False)):
            runtime_flags["bed_guide_active"] = True
            runtime_flags["bed_guide_step_index"] = 0
            save_profile(profile)
            return render_bed_guide_step(0), True
        current_index = int(runtime_flags.get("bed_guide_step_index", 0)) + 1
        runtime_flags["bed_guide_step_index"] = current_index
        if current_index >= len(build_bed_guide_steps()):
            runtime_flags["bed_guide_active"] = False
            profile.setdefault("onboarding", {})["bed_guide_completed"] = True
            save_profile(profile)
            return "Bed guide completed. Say 'bed tutorial' anytime if you want a refresher.", True
        save_profile(profile)
        return render_bed_guide_step(current_index), True

    if natural_intent == "bed_guide_repeat":
        if not bool(runtime_flags.get("bed_guide_active", False)):
            runtime_flags["bed_guide_active"] = True
            runtime_flags["bed_guide_step_index"] = 0
        current_index = int(runtime_flags.get("bed_guide_step_index", 0))
        save_profile(profile)
        return render_bed_guide_step(current_index), True

    if natural_intent == "bed_guide_stop":
        runtime_flags["bed_guide_active"] = False
        save_profile(profile)
        return "Okay, stopped the bed guide. Say 'bed tutorial' anytime to resume.", True

    if natural_intent == "start_breathing":
        minutes = routine_engine.parse_minutes_from_text(user_text, default_minutes=5)
        runtime_flags["breathing_offer_active"] = False
        return (
            routine_engine.start_breathing_guide_routine(
                led=led,
                tts_manager=tts,
                audio_player=tts_player,
                duration_minutes=minutes,
            ),
            True,
        )

    if natural_intent == "stop_breathing":
        runtime_flags["breathing_offer_active"] = False
        return routine_engine.stop_breathing_guide_routine(), True

    if natural_intent == "dream_prompt":
        if not dream_journal.should_prompt_dream(profile):
            return "Dream journal prompt is available in the morning window (6:00-11:59).", True
        msg = dream_journal.start_dream_prompt_session(profile, None, tts, tts_player)
        save_profile(profile)
        return msg, True

    if natural_intent == "dream_insights":
        return dream_journal.get_dream_insights(profile), True

    if natural_intent == "adaptive_insights":
        return adaptive_personality.get_personality_insights(profile), True

    if natural_intent == "adaptive_toggle":
        msg = adaptive_personality.set_adaptive_enabled(profile, bool(natural_payload.get("enabled", True)))
        save_profile(profile)
        return msg, True

    if natural_intent == "music_lights_status":
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return led.music_reactive_status(), True

    if natural_intent == "music_lights_on":
        prefs["music_lights_enabled"] = True
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Music lights are on and synced with playback.", True

    if natural_intent == "music_lights_off":
        prefs["music_lights_enabled"] = False
        apply_music_led_preferences(led, profile, active=False)
        save_profile(profile)
        return "Music lights are now off.", True

    if natural_intent == "music_lights_calm":
        prefs["music_lights_energy"] = "calm"
        if has_any(normalized_lower, ("night", "ليلي", "ليل")):
            prefs["music_lights_brightness_percent"] = _clamp_percent(
                prefs.get("music_lights_night_brightness_percent", 35),
                default_value=35,
            )
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Done. Music lights are in calm mode.", True

    if natural_intent == "music_lights_energetic":
        prefs["music_lights_energy"] = "energetic"
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Done. Music lights are now energetic.", True

    if natural_intent == "music_lights_target":
        target = str(natural_payload.get("target", "")).strip().lower()
        if target in ("both", "user_only"):
            prefs["music_lights_target"] = target
            apply_music_led_preferences(led, profile)
            save_profile(profile)
            return (
                "Music lights will use both strips."
                if target == "both"
                else "Music lights now use user strip only."
            ), True

    if natural_intent == "music_lights_mode":
        mode = str(natural_payload.get("mode", "")).strip().lower()
        if mode in ("pulse", "wave", "spectrum"):
            prefs["music_lights_mode"] = mode
            apply_music_led_preferences(led, profile)
            save_profile(profile)
            return f"Music lights mode set to {mode}.", True

    if natural_intent == "music_lights_brightness":
        value = _clamp_percent(natural_payload.get("brightness_percent", 35), default_value=35)
        prefs["music_lights_brightness_percent"] = value
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return f"Music lights brightness set to {value}%.", True

    if natural_intent == "music_lights_default":
        prefs["music_lights_mode"] = "pulse"
        prefs["music_lights_energy"] = "calm"
        prefs["music_lights_target"] = "both"
        prefs["music_lights_enabled"] = True
        prefs["music_lights_brightness_percent"] = 35
        prefs["music_lights_night_brightness_percent"] = 35
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Music lighting reset to defaults.", True

    if natural_intent == "start_bedtime_routine":
        minutes = routine_engine.parse_minutes_from_text(user_text, default_minutes=30)
        return routine_engine.start_bedtime_routine(led, local_music, sleep_routine, minutes=minutes), True

    if natural_intent == "start_morning_routine":
        return routine_engine.trigger_morning_routine(led, local_music), True

    if natural_intent == "brightness_up":
        led.brightness_up()
        runtime_flags["last_action"] = {
            "intent": "brightness_up",
            "inverse": {"intent": "brightness_down", "slots": {}},
        }
        save_profile(profile)
        return "Made the lights brighter.", True

    if natural_intent == "brightness_down":
        led.brightness_down()
        runtime_flags["last_action"] = {
            "intent": "brightness_down",
            "inverse": {"intent": "brightness_up", "slots": {}},
        }
        save_profile(profile)
        return "Dimmed the lights.", True

    if natural_intent == "brightness_set":
        percent = _clamp_percent(natural_payload.get("brightness_percent", 40), default_value=40)
        led.set_user_brightness(percent / 100.0)
        runtime_flags["last_action"] = {
            "intent": "brightness_set",
            "inverse": {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}},
        }
        save_profile(profile)
        return f"Set brightness to {percent}%.", True

    if natural_intent == "set_color":
        color_value = str(natural_payload.get("color", "")).strip()
        if color_value:
            led.set_color_value(color_value)
            profile.setdefault("preferences", {})["favorite_color"] = color_value
            runtime_flags["last_action"] = {
                "intent": "set_color",
                "inverse": {"intent": "set_scene", "slots": {"scene_key": "balanced_default"}},
            }
            save_profile(profile)
            return f"Changed lights to {color_value}.", True

    if natural_intent == "pause_music_followup":
        ok, message = spotify.pause()
        if (not ok) and should_use_local_music_fallback(message):
            ok, message = local_music.pause()
        if ok:
            apply_music_led_preferences(led, profile, active=False)
            runtime_flags["last_action"] = {
                "intent": "pause_music",
                "inverse": {"intent": "play_music", "slots": {"query": "ambient"}},
            }
            save_profile(profile)
        return message or "Paused audio playback.", True

    if natural_intent == "resume_music_followup":
        ok, message = spotify.resume()
        if (not ok) and should_use_local_music_fallback(message):
            ok, message = local_music.resume()
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            runtime_flags["last_action"] = {
                "intent": "play_music",
                "inverse": {"intent": "pause_music", "slots": {}},
            }
            save_profile(profile)
        return message or "Resumed audio playback.", True

    if lower in (
        "what is my age",
        "what's my age",
        "how old am i",
        "my age",
        "age",
    ):
        age = str(profile.get("age", "?") or "?").strip()
        if age in ("", "?"):
            return "I do not have your age saved yet. Tell me: I am <age> years old.", True
        return f"You are {age} years old.", True

    if lower.startswith("set bed nickname to "):
        nickname = user_text.split("set bed nickname to", 1)[1].strip()
        nickname = apply_bed_nickname(profile, wake_word_manager, nickname)
        if not nickname:
            return "Use: set bed nickname to <name>", True
        runtime_flags["awaiting_bed_nickname"] = False
        save_profile(profile)
        return f"Bed nickname set to '{nickname}'. You can wake me with '{nickname}' too.", True

    if lower.startswith("call this bed "):
        nickname = user_text.split("call this bed", 1)[1].strip()
        nickname = apply_bed_nickname(profile, wake_word_manager, nickname)
        if not nickname:
            return "Use: call this bed <name>", True
        runtime_flags["awaiting_bed_nickname"] = False
        save_profile(profile)
        return f"Got it. You can wake me by saying '{nickname}'.", True

    if lower in ("clear bed nickname", "remove bed nickname", "reset bed nickname"):
        profile.setdefault("preferences", {})["bed_nickname"] = ""
        runtime_flags["awaiting_bed_nickname"] = False
        wake_word_manager.set_wake_aliases(build_wake_aliases_from_profile(profile))
        save_profile(profile)
        return "Bed nickname cleared. Default wake phrase remains active.", True

    if lower in ("show wake names", "wake names", "what can i call you", "show wake aliases"):
        phrases = wake_word_manager.get_wake_phrases()
        return "Wake phrases: " + " | ".join(phrases), True

    if lower in ("help", "show help", "help me", "what can you do", "commands"):
        return build_help_overview(), True

    if lower in ("delete all my data", "erase my data", "reset my data"):
        runtime_flags["awaiting_data_delete_confirm"] = True
        save_profile(profile)
        return "This will delete data for your current local user profile on this device. Shared subscription records for other users are kept. Say confirm to proceed or cancel.", True

    if lower in ("privacy status", "show privacy settings", "data retention"):
        days = _safe_int(profile.get("preferences", {}).get("data_retention_days", 14), default_value=14, min_value=1, max_value=365)
        return (
            f"Privacy defaults -> text retention target: {days} days, raw audio storage: off by default. "
            "Say 'delete all my data' for one-click local wipe."
        ), True

    retention_match = re.search(r"set (?:data )?retention(?: to)?\s*(\d{1,3})\s*(?:day|days)?", lower)
    if retention_match:
        days = max(1, min(365, int(retention_match.group(1))))
        profile.setdefault("preferences", {})["data_retention_days"] = days
        save_profile(profile)
        return f"Data retention set to {days} days.", True

    if lower in ("sleep help", "sleep features help", "sleep coaching help"):
        return build_sleep_help(), True

    if lower in ("first boot guide", "onboarding help", "quick start"):
        return (
            "Onboarding quick start -> 1) Set bedtime routine: 'set bedtime routine for 22:30'. "
            "2) Enable wind-down: 'start wind down autopilot 45'. "
            "3) In morning log: 'log wake'. 4) Review weekly: 'weekly sleep insights'.",
            True,
        )

    if lower.startswith("set language to "):
        lang = user_text.split("set language to", 1)[1].strip()
        if not lang:
            return "Use: set language to auto|en|ar|fr|...", True
        if lang.lower() in ("all", "any", "auto"):
            lang = "auto"
        profile.setdefault("preferences", {})["language"] = lang
        save_profile(profile)
        if lang == "auto":
            return "Language mode set to auto. I will follow your spoken/written language.", True
        return f"Language preference saved: {lang}.", True

    if lower in ("show language", "language status"):
        lang = profile.get("preferences", {}).get("language", "auto")
        return f"Language mode: {lang}.", True

    if lower in ("cloud status", "entitlement status", "subscription cloud status"):
        diag = _build_gpt_route_diagnostics(backend_client)
        lines = []
        if diag["openai_direct_enabled"]:
            if diag["openai_ready"]:
                lines.append(f"Direct OpenAI GPT route: ready (model={settings.openai_chat_model}).")
            else:
                lines.append("Direct OpenAI GPT route: not ready.")
        else:
            lines.append("Direct OpenAI GPT route: disabled (USE_OPENAI_DIRECT=0).")

        if diag["backend_proxy_enabled"] and (backend_client is not None) and backend_client.is_configured():
            backend_client.fetch_entitlement()
            lines.append(f"Backend GPT route: {backend_client.status_line()}")
            if not backend_client.is_feature_allowed("cloud_chat"):
                lines.append("Backend feature gate: cloud_chat is disabled for this device/subscription.")
        elif diag["backend_proxy_enabled"]:
            lines.append("Backend GPT route: not configured (set APP_BACKEND_BASE_URL and BED_DEVICE_ID).")
        else:
            lines.append("Backend GPT route: disabled (USE_BACKEND_AI_PROXY=0).")

        if diag["issues"]:
            lines.append("Missing/blocked: " + " | ".join(diag["issues"]))
        return " ".join(lines), True

    if lower in ("audio output status", "speaker status", "show audio output"):
        return audio_output.output_status(profile), True

    if lower in ("show led config", "led config", "hardware led status"):
        apply_led_hardware_config(led, profile)
        save_profile(profile)
        return led.hardware_status(), True

    if lower in (
        "music lights status",
        "show music lights status",
        "music lights config",
    ):
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return led.music_reactive_status(), True

    if lower in ("turn on music lights", "music lights on", "sync lights with music"):
        prefs["music_lights_enabled"] = True
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Music lights are on and synced with playback.", True

    if lower in ("turn off music lights", "music lights off", "stop syncing lights with music"):
        prefs["music_lights_enabled"] = False
        apply_music_led_preferences(led, profile, active=False)
        save_profile(profile)
        return "Music lights are now off.", True

    if lower in ("make music lights calmer", "music lights calmer", "apply night music lighting"):
        prefs["music_lights_energy"] = "calm"
        if "night" in lower:
            prefs["music_lights_brightness_percent"] = _clamp_percent(
                prefs.get("music_lights_night_brightness_percent", 35),
                default_value=35,
            )
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Done. Music lights are in calm mode.", True

    if lower in ("make music lights more energetic", "music lights energetic", "apply party music lighting"):
        prefs["music_lights_energy"] = "energetic"
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Done. Music lights are now energetic.", True

    if lower in ("use both strips for music lights", "music lights on both strips"):
        prefs["music_lights_target"] = "both"
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Music lights will use both strips.", True

    if lower in ("music lights on user strip only", "use user strip only for music lights"):
        prefs["music_lights_target"] = "user_only"
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Music lights now use user strip only.", True

    mode_match = re.search(r"set music lights to\s+(pulse|wave|spectrum)\s*(?:mode)?$", lower)
    if mode_match:
        mode = mode_match.group(1)
        prefs["music_lights_mode"] = mode
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return f"Music lights mode set to {mode}.", True

    brightness_match = re.search(r"set music lights brightness to\s*(\d{1,3})", lower)
    if brightness_match:
        value = _clamp_percent(brightness_match.group(1), default_value=35)
        prefs["music_lights_brightness_percent"] = value
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return f"Music lights brightness set to {value}%.", True

    night_brightness_match = re.search(r"set night music lights brightness to\s*(\d{1,3})", lower)
    if night_brightness_match:
        value = _clamp_percent(night_brightness_match.group(1), default_value=35)
        prefs["music_lights_night_brightness_percent"] = value
        save_profile(profile)
        return f"Night music lights default brightness set to {value}%.", True

    if lower in ("use default music lighting", "reset music lights"):
        prefs["music_lights_mode"] = "pulse"
        prefs["music_lights_energy"] = "calm"
        prefs["music_lights_target"] = "both"
        prefs["music_lights_enabled"] = True
        prefs["music_lights_brightness_percent"] = 35
        prefs["music_lights_night_brightness_percent"] = 35
        apply_music_led_preferences(led, profile)
        save_profile(profile)
        return "Music lighting reset to defaults.", True

    if lower.startswith("set user strip led count to "):
        raw_value = user_text.split("to", 1)[1].strip()
        try:
            count = max(1, int(raw_value))
        except ValueError:
            return "Use: set user strip led count to <number>", True
        profile.setdefault("hardware", {})["user_strip_led_count"] = count
        apply_led_hardware_config(led, profile)
        save_profile(profile)
        return f"Updated user strip LED count to {count}. {led.hardware_status()}", True

    if lower.startswith("set state strip led count to "):
        raw_value = user_text.split("to", 1)[1].strip()
        try:
            count = max(1, int(raw_value))
        except ValueError:
            return "Use: set state strip led count to <number>", True
        profile.setdefault("hardware", {})["state_strip_led_count"] = count
        apply_led_hardware_config(led, profile)
        save_profile(profile)
        return f"Updated state strip LED count to {count}. {led.hardware_status()}", True

    if lower in (
        "use bed speaker",
        "set audio output to bed speaker",
        "switch to bed speaker",
    ):
        ok, message = audio_output.set_bed_speaker(profile)
        save_profile(profile)
        return message, True

    if lower in ("scan bluetooth speakers", "list bluetooth speakers", "show bluetooth speakers"):
        ok, message, _ = audio_output.scan_speakers()
        return message, True

    if lower.startswith("connect bluetooth speaker"):
        target = user_text.split("connect bluetooth speaker", 1)[1].strip()
        if not target:
            return "Use: connect bluetooth speaker <name or mac>", True
        ok, message = audio_output.connect_bluetooth_speaker(target, profile)
        if ok:
            save_profile(profile)
        return message, True

    if lower in (
        "disconnect bluetooth speaker",
        "use default speaker",
        "disable bluetooth speaker",
    ):
        ok, message = audio_output.disconnect_bluetooth_speaker(profile)
        save_profile(profile)
        return message, True

    if lower in ("run health check", "device health", "health check"):
        return health_report_builder(), True

    if lower in ("pilot readiness", "pilot readiness report", "readiness report"):
        preferences = profile.get("preferences", {})
        ack_mode = str(preferences.get("thinking_ack_mode", "minimal") or "minimal")
        retention_days = _safe_int(preferences.get("data_retention_days", 14), default_value=14, min_value=1, max_value=365)
        speed_mode = str(preferences.get("speed_mode", "normal") or "normal")
        response_style = str(preferences.get("response_style", "quick") or "quick")
        engagement = str(preferences.get("engagement_level", "normal") or "normal")
        health_report = health_report_builder()
        return (
            "Pilot readiness snapshot -> "
            f"ack={ack_mode}, retention={retention_days}d, speed={speed_mode}, "
            f"response_style={response_style}, engagement={engagement}. "
            f"{health_report}"
        ), True

    if lower in ("pilot readiness checklist", "pilot qa checklist", "final pilot checklist"):
        health_report = health_report_builder()
        return build_pilot_readiness_checklist(profile, health_report), True

    if lower in ("pilot go no go", "pilot signoff", "pilot ready now"):
        health_report = health_report_builder()
        return build_pilot_go_no_go(profile, health_report), True

    if lower in ("bed phase status", "bed phase complete status", "pilot phase status"):
        onboarding = profile.get("onboarding", {})
        done = bool(onboarding.get("bed_phase_completed", False))
        completed_at = str(onboarding.get("bed_phase_completed_at", "") or "")
        if done:
            return f"Bed phase status -> completed at {completed_at}.", True
        return "Bed phase status -> not completed yet. Run 'pilot go no go' then 'mark bed phase complete' when GO.", True

    if lower in ("mark bed phase complete", "complete bed phase", "mark pilot phase complete"):
        health_report = health_report_builder()
        signoff = build_pilot_go_no_go(profile, health_report)
        if "-> HOLD" in signoff:
            return f"Cannot mark complete yet. {signoff}", True
        onboarding = profile.setdefault("onboarding", {})
        onboarding["bed_phase_completed"] = True
        onboarding["bed_phase_completed_at"] = datetime.now().isoformat(timespec="seconds")
        save_profile(profile)
        return f"Bed phase marked complete. {signoff}", True

    if lower in ("pilot smoke checklist", "tester checklist", "smoke checklist"):
        return (
            "Pilot smoke checklist -> "
            "1) run health check. "
            "2) play/pause/next/previous/stop music. "
            "3) turn on music lights and change mode/brightness. "
            "4) start wind down autopilot 15 then stop it. "
            "5) test privacy status + set retention to 30 days. "
            "6) verify delete flow with cancel. "
            "7) ask a short follow-up and confirm same-topic concise response."
        ), True

    if lower in ("sleep debt", "sleep debt report", "calculate sleep debt"):
        return daily_life_support.sleep_debt_summary(profile), True

    if lower.startswith("start wind down autopilot"):
        default_minutes = int(profile.get("sleep", {}).get("wind_down_minutes", 45) or 45)
        minutes = routine_engine.parse_minutes_from_text(user_text, default_minutes=default_minutes)
        autopilot_text = sleep_engine.build_wind_down_autopilot(profile, minutes=minutes)
        led.set_user_animation("breathing")
        led.set_user_brightness(0.22)
        music_ok, music_msg = spotify.play_track_query("sleep ambient")
        if not music_ok:
            local_ok, local_msg = local_music.play_query("sleep")
            music_msg = local_msg if local_ok else ""
            music_ok = local_ok
        if music_ok:
            apply_music_led_preferences(led, profile, active=True)
        timer_text = sleep_routine.start_sleep_timer(minutes, on_sleep_timer_finish)
        save_profile(profile)
        return f"{autopilot_text} {timer_text} {music_msg}".strip(), True

    if lower in ("stop wind down autopilot", "disable wind down autopilot"):
        message = sleep_engine.disable_wind_down_autopilot(profile)
        save_profile(profile)
        return message, True

    if lower in (
        "optimize my room for sleep",
        "optimize room for sleep",
        "optimize sleep room",
        "sleep optimize room",
    ):
        scene = {
            "key": "sleep_optimized_room",
            "animation": "breathing",
            "color": "warmwhite",
            "brightness": 0.18,
            "line": "Environment scene: sleep optimization.",
        }
        scene_line = environment_orchestrator.apply_scene(led, profile, scene)
        target_minutes = int(profile.get("sleep", {}).get("wind_down_minutes", 45) or 45)
        autopilot_text = sleep_engine.build_wind_down_autopilot(profile, minutes=target_minutes)
        music_ok, music_msg = spotify.play_track_query("sleep ambient")
        if not music_ok:
            local_ok, local_msg = local_music.play_query("sleep")
            if local_ok:
                music_ok = True
                music_msg = local_msg
        if music_ok:
            apply_music_led_preferences(led, profile, active=True)
        if not (music_msg or "").strip():
            music_msg = "Audio: sleep audio is not available right now, but room settings are optimized."
        save_profile(profile)
        return f"{scene_line} {autopilot_text} {music_msg}".strip(), True

    if lower in ("sleep consistency", "consistency score", "sleep consistency score"):
        return sleep_engine.sleep_consistency_score(profile), True

    if lower in (
        "predictive bedtime drift",
        "bedtime drift",
        "bedtime drift alert",
        "sleep drift alert",
    ):
        return sleep_engine.bedtime_drift_alert(profile), True

    if lower in (
        "sleep quality",
        "sleep quality score",
        "quality sleep score",
        "sleep score",
    ):
        return sleep_engine.sleep_quality_score(profile), True

    if lower in ("adaptive wake routine", "wake routine plan"):
        return sleep_engine.adaptive_wake_routine_plan(profile), True

    if lower in ("enable adaptive wake", "adaptive wake on"):
        profile.setdefault("preferences", {})["adaptive_wake_enabled"] = True
        save_profile(profile)
        return "Adaptive wake routine enabled.", True

    if lower in ("disable adaptive wake", "adaptive wake off"):
        profile.setdefault("preferences", {})["adaptive_wake_enabled"] = False
        save_profile(profile)
        return "Adaptive wake routine disabled.", True

    if lower.startswith("start decompression") or lower.startswith("stress decompression"):
        minutes = routine_engine.parse_minutes_from_text(user_text, default_minutes=5)
        protocol = sleep_engine.stress_decompression_protocol(profile, minutes=minutes)
        scene = {
            "key": "stress_decompression",
            "animation": "breathing",
            "color": "cyan",
            "brightness": 0.18,
            "line": "Environment scene: stress decompression.",
        }
        line = environment_orchestrator.apply_scene(led, profile, scene)
        save_profile(profile)
        return f"{line} {protocol}".strip(), True

    if lower in (
        "sleep debt recovery plan",
        "sleep recovery plan",
        "debt recovery plan",
    ):
        return sleep_engine.sleep_debt_recovery_plan(profile), True

    if lower in ("environment intelligence", "sleep environment tip", "sleep environment"):
        return sleep_engine.environment_intelligence_tip(profile), True

    if lower in ("weekly sleep insights", "sleep weekly insights", "sleep weekly report"):
        message = sleep_engine.weekly_sleep_insights(profile)
        save_profile(profile)
        return message, True

    if lower in (
        "weekly recovery score card",
        "recovery score card",
        "weekly recovery card",
    ):
        message = sleep_engine.weekly_recovery_score_card(profile)
        save_profile(profile)
        return message, True

    if lower in (
        "enable partner sleep mode",
        "partner sleep mode on",
        "partner mode on",
    ):
        message = sleep_engine.set_partner_mode_enabled(profile, enabled=True)
        save_profile(profile)
        return message, True

    if lower in (
        "disable partner sleep mode",
        "partner sleep mode off",
        "partner mode off",
    ):
        message = sleep_engine.set_partner_mode_enabled(profile, enabled=False)
        save_profile(profile)
        return message, True

    if lower in (
        "partner sleep mode status",
        "partner mode status",
        "show partner sleep mode",
    ):
        return sleep_engine.partner_mode_status(profile), True

    partner_name_match = re.match(r"^set\s+partner\s+([12])\s+name\s+(.+)$", lower)
    if partner_name_match:
        slot = int(partner_name_match.group(1))
        # Safer extraction from original text preserving case for names.
        name_text = re.split(r"^set\s+partner\s+[12]\s+name\s+", user_text, maxsplit=1, flags=re.IGNORECASE)
        partner_name = name_text[1].strip() if len(name_text) > 1 else ""
        if not partner_name:
            return "Use: set partner <1|2> name <name>", True
        message = sleep_engine.set_partner_profile(profile, slot=slot - 1, name=partner_name)
        save_profile(profile)
        return message, True

    partner_style_match = re.match(r"^set\s+partner\s+([12])\s+wake\s+style\s+(.+)$", lower)
    if partner_style_match:
        slot = int(partner_style_match.group(1))
        style_text = re.split(r"^set\s+partner\s+[12]\s+wake\s+style\s+", user_text, maxsplit=1, flags=re.IGNORECASE)
        wake_style = style_text[1].strip() if len(style_text) > 1 else ""
        if not wake_style:
            return "Use: set partner <1|2> wake style <gentle|balanced|energizing>", True
        message = sleep_engine.set_partner_profile(profile, slot=slot - 1, wake_style=wake_style)
        save_profile(profile)
        return message, True

    if lower in (
        "partner conflict safe routine",
        "conflict safe wake routine",
        "partner wake routine",
    ):
        return sleep_engine.partner_conflict_safe_routine(profile), True

    if lower in (
        "night wake recovery",
        "night wake mode",
        "i woke at night",
        "help me sleep again",
    ):
        protocol = sleep_engine.night_wake_recovery_protocol(profile)
        scene = {
            "key": "night_wake_recovery",
            "animation": "breathing",
            "color": "warmwhite",
            "brightness": 0.12,
            "line": "Environment scene: night wake recovery.",
        }
        line = environment_orchestrator.apply_scene(led, profile, scene)
        save_profile(profile)
        return f"{line} {protocol}".strip(), True

    if lower.startswith("overthinking dump "):
        text = user_text.split("overthinking dump", 1)[1].strip()
        msg = daily_life_support.log_overthinking(profile, text)
        save_profile(profile)
        return msg, True

    if lower in ("show overthinking dump", "overthinking status"):
        return daily_life_support.overthinking_status(profile), True

    if lower in ("convert last worry to goal", "convert worry to goal"):
        goal_text = daily_life_support.convert_last_worry_to_goal_text(profile)
        if goal_text.startswith("No "):
            return goal_text, True
        goal = goal_manager.add_goal(profile, goal_text, scope="tonight")
        ensure_progress_shape(profile)
        profile["progress"]["goals_created"] = int(profile["progress"].get("goals_created", 0)) + 1
        save_profile(profile)
        return f"Created a goal from your last worry: {goal['title']} (ID: {goal['id']}).", True

    if lower in ("nightmare recovery", "i had a nightmare", "bad dream recovery"):
        message = daily_life_support.nightmare_recovery_message()
        scene = {
            "key": "nightmare_recovery",
            "animation": "breathing",
            "color": "cyan",
            "brightness": 0.2,
            "line": "Environment scene: nightmare recovery.",
        }
        line = environment_orchestrator.apply_scene(led, profile, scene)
        save_profile(profile)
        return f"{line} {message}".strip(), True

    if lower.startswith("mood scene ") or lower.startswith("play mood ") or lower.startswith("mood bundle "):
        mood = user_text
        for marker in ("mood scene", "play mood", "mood bundle"):
            if lower.startswith(marker):
                mood = user_text.split(marker, 1)[1].strip()
                break
        if not mood:
            return "Use: mood scene <mood> (e.g., stressed/focus/tired/motivated)", True
        personality = profile.get("preferences", {}).get("personality", "therapist")
        bundle = daily_life_support.mood_bundle(mood, personality)
        scene_payload = {
            "key": bundle.get("scene", {}).get("key", "mood_scene"),
            "animation": bundle.get("scene", {}).get("animation", "solid"),
            "color": bundle.get("scene", {}).get("color", "white"),
            "brightness": float(bundle.get("scene", {}).get("brightness", 0.35)),
            "line": f"Environment scene: {bundle.get('label', 'balanced')}.",
        }
        scene_line = environment_orchestrator.apply_scene(led, profile, scene_payload)

        music_ok, music_msg = spotify.play_track_query(bundle.get("spotify_query", ""))
        if not music_ok:
            local_ok, local_msg = local_music.play_query(bundle.get("local_query", ""))
            music_msg = local_msg if local_ok else music_msg
            music_ok = local_ok
        if music_ok:
            apply_music_led_preferences(led, profile, active=True)

        daily_life_support.set_last_mood_bundle(profile, bundle)
        save_profile(profile)
        coaching = bundle.get("coaching", "")
        return f"{scene_line} {music_msg} {coaching}".strip(), True

    if crisis_command_match(user_text):
        return build_fast_protocol_message(), True

    if lower.startswith("set monthly objective "):
        text = user_text.split("set monthly objective", 1)[1].strip()
        if not text:
            return "Use: set monthly objective <objective>", True
        message = goal_compass.set_monthly_objective(profile, text)
        save_profile(profile)
        return message, True

    if lower in ("show monthly objective", "monthly objective", "goal compass"):
        active_goals = [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]
        return goal_compass.summary_line(profile, active_goals), True

    if lower in ("environment status", "smart environment status"):
        return environment_orchestrator.status_line(profile), True

    if lower in ("apply smart scene", "smart scene now"):
        emotion_state = runtime_orchestrator.latest_emotion_state(profile)
        recovery_mode = bool(profile.get("sleep", {}).get("recovery_mode", False))
        challenge_level = int(profile.get("sleep", {}).get("challenge_level", 1))
        personality = profile.get("preferences", {}).get("personality", "therapist")
        scene = environment_orchestrator.choose_scene(
            emotion_state=emotion_state,
            recovery_mode=recovery_mode,
            challenge_level=challenge_level,
            personality=personality,
        )
        line = environment_orchestrator.apply_scene(led, profile, scene)
        save_profile(profile)
        return line or "Applied smart environment scene.", True

    if lower in ("show session continuity", "session continuity"):
        personality = profile.get("preferences", {}).get("personality", "therapist")
        return runtime_orchestrator.continuity_line(profile, personality), True

    if lower in ("voice pacing status", "show voice pacing"):
        return runtime_orchestrator.voice_pacing_status(profile), True

    if lower in ("start recovery protocol",):
        active_goals = [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]
        msg = goal_strategy.build_recovery_protocol_dialogue(profile, active_goals)
        goal_strategy.mark_recovery_prompted_today(profile)
        save_profile(profile)
        return msg, True

    if lower.startswith("set quiet window "):
        window = user_text.split("set quiet window", 1)[1].strip()
        if not re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}$", window):
            return "Use: set quiet window 23:00-07:00", True
        profile["preferences"]["quiet_window"] = window
        save_profile(profile)
        return f"Quiet window set to {window}.", True

    if lower in ("show quiet window", "quiet window status"):
        window = profile.get("preferences", {}).get("quiet_window", "") or "off"
        return f"Quiet window: {window}.", True

    if lower in ("log bedtime", "sleep now"):
        message = sleep_engine.record_bedtime_now(profile)
        save_profile(profile)
        return message, True

    if lower in ("log wake", "log wake time", "i woke up"):
        message = sleep_engine.record_wake_now(profile)
        save_profile(profile)
        return message, True

    if lower in ("sleep insights", "sleep status", "sleep intelligence"):
        return sleep_engine.summary_line(profile), True

    if lower in ("recovery status", "recovery protocol"):
        active_goals = [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]
        sleep_engine.evaluate_recovery_mode(profile, active_goals_count=len(active_goals))
        save_profile(profile)
        return sleep_engine.build_recovery_protocol(profile), True

    if lower.startswith("set guide level to "):
        level = user_text.split("to", 1)[1].strip().lower()
        if level not in ("beginner", "intermediate", "advanced"):
            return "Use: set guide level to beginner/intermediate/advanced", True
        profile["preferences"]["guide_level"] = level
        save_profile(profile)
        return f"Guide level set to {level}.", True

    if lower in ("intervention now", "suggest intervention"):
        personality = profile.get("preferences", {}).get("personality", "therapist")
        emotion_state = runtime_orchestrator.latest_emotion_state(profile)
        guide_level = profile.get("preferences", {}).get("guide_level", "beginner")
        intervention = runtime_orchestrator.choose_dynamic_intervention(
            personality=personality,
            emotion_state=emotion_state,
            level=guide_level,
        )
        return intervention, True

    if lower in ("adaptive weekly plan", "next week plan"):
        active_goals = [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]
        return runtime_orchestrator.build_weekly_adaptive_plan(profile, active_goals), True

    if lower.startswith("decompose goal "):
        ref = user_text.split("decompose goal", 1)[1].strip()
        ok, message = goal_strategy.decompose_goal_by_ref(profile, ref)
        return message, True

    if lower.startswith("decompose "):
        text = user_text.split("decompose", 1)[1].strip()
        steps = goal_strategy.decompose_goal_text(text)
        if not steps:
            return "Use: decompose <goal text>", True
        return "Micro-plan: " + " | ".join(f"{idx+1}. {s}" for idx, s in enumerate(steps)), True

    if lower.startswith("mark goal missed "):
        payload = user_text.split("mark goal missed", 1)[1].strip()
        goal_ref, cause_text = payload, ""
        payload_lower = payload.lower()
        marker = " because "
        idx = payload_lower.find(marker)
        if idx >= 0:
            goal_ref = payload[:idx].strip()
            cause_text = payload[idx + len(marker) :].strip()
        ok, message, _ = goal_strategy.mark_goal_missed(profile, goal_ref, cause_text=cause_text)
        if ok:
            save_profile(profile)
        return message, True

    if lower.startswith("root cause was "):
        cause_text = user_text.split("root cause was", 1)[1].strip()
        message = goal_strategy.record_miss_cause(profile, cause_text)
        save_profile(profile)
        return message, True

    if lower in ("miss analysis", "goal miss analysis"):
        return goal_strategy.root_cause_summary(profile), True

    if lower in ("bedtime challenge", "sleep challenge"):
        return sleep_engine.challenge_guidance(profile), True

    if lower.startswith("start bedtime routine"):
        minutes = routine_engine.parse_minutes_from_text(user_text, default_minutes=30)
        return (
            routine_engine.start_bedtime_routine(led, local_music, sleep_routine, minutes=minutes),
            True,
        )

    if lower in ("start morning routine", "run morning routine"):
        return routine_engine.trigger_morning_routine(led, local_music), True

    if lower.startswith("set morning routine for "):
        hhmm, error = routine_engine.parse_time_from_text(user_text)
        if error:
            return error, True
        repeat_days = routine_engine.parse_repeat_days_from_text(user_text)
        alarm = schedule.add_alarm(hhmm, label="Morning Routine", repeat_days=repeat_days)
        repeat_text = format_repeat_days(repeat_days)
        return f"Morning routine set for {alarm.time_24h} ({repeat_text}). ID: {alarm.id}", True

    if lower.startswith("set response style to "):
        style = user_text.split("to", 1)[1].strip().lower()
        if style not in ("quick", "balanced", "detailed"):
            return "Use: set response style to quick/balanced/detailed", True
        profile["preferences"]["response_style"] = style
        save_profile(profile)
        return f"Response style set to {style}.", True

    if lower.startswith("set followup tone to ") or lower.startswith("set follow up tone to "):
        tone_value = user_text.split("to", 1)[1].strip()
        tone = normalize_followup_tone(tone_value)
        profile.setdefault("preferences", {})["therapist_followup_tone"] = tone
        save_profile(profile)
        return (
            "Therapist follow-up tone set to "
            + tone
            + ". Options: soft, teen, islamic."
        ), True

    if lower in ("show followup tone", "show follow up tone", "what is followup tone", "what is follow up tone"):
        tone = normalize_followup_tone(profile.get("preferences", {}).get("therapist_followup_tone", "soft"))
        return f"Current therapist follow-up tone is {tone}.", True

    if lower.startswith("set thinking acknowledgements to "):
        mode = user_text.split("to", 1)[1].strip().lower().replace("-", "_").replace(" ", "_")
        if mode in ("off", "mute", "disabled", "disable"):
            mode = "off"
        elif mode in ("minimal", "smart"):
            mode = "minimal"
        elif mode in ("on", "always", "enabled", "enable"):
            mode = "always"
        else:
            return "Use: set thinking acknowledgements to off/minimal/always", True
        profile["preferences"]["thinking_ack_mode"] = mode
        save_profile(profile)
        return f"Thinking acknowledgement mode set to {mode}.", True

    if lower in ("mute thinking acknowledgements", "disable thinking acknowledgements", "no thinking acknowledgement"):
        profile["preferences"]["thinking_ack_mode"] = "off"
        save_profile(profile)
        return "Thinking acknowledgements are now off.", True

    if lower in ("enable thinking acknowledgements", "turn on thinking acknowledgements"):
        profile["preferences"]["thinking_ack_mode"] = "minimal"
        save_profile(profile)
        return "Thinking acknowledgements enabled in minimal mode.", True

    if lower.startswith("set tonight goal "):
        goal_title = user_text.split("set tonight goal", 1)[1].strip()
        if not goal_title:
            return "Use: set tonight goal <goal text>", True
        goal = goal_manager.add_goal(profile, goal_title, scope="tonight")
        ensure_progress_shape(profile)
        profile["progress"]["goals_created"] = int(profile["progress"].get("goals_created", 0)) + 1
        save_profile(profile)
        return f"Tonight goal saved: {goal['title']} (ID: {goal['id']}).", True

    if lower.startswith("set weekly goal "):
        goal_title = user_text.split("set weekly goal", 1)[1].strip()
        if not goal_title:
            return "Use: set weekly goal <goal text>", True
        goal = goal_manager.add_goal(profile, goal_title, scope="weekly")
        ensure_progress_shape(profile)
        profile["progress"]["goals_created"] = int(profile["progress"].get("goals_created", 0)) + 1
        save_profile(profile)
        return f"Weekly goal saved: {goal['title']} (ID: {goal['id']}).", True

    if lower in ("list goals", "show goals", "my goals"):
        goals = goal_manager.list_goals(profile)
        if not goals:
            return "No goals yet. Try: set tonight goal sleep by 11 PM", True
        lines = [f"{g['id']} -> {g['scope']} -> {g['status']} -> {g['title']}" for g in goals[:10]]
        return "Goals: " + " | ".join(lines), True

    if lower.startswith("complete goal "):
        ref = user_text.split("complete goal", 1)[1].strip()
        ok, message = goal_manager.complete_goal(profile, ref)
        if ok:
            ensure_progress_shape(profile)
            profile["progress"]["goals_completed"] = int(profile["progress"].get("goals_completed", 0)) + 1
            record_goal_completion(profile)
            save_profile(profile)
        return message, True

    if lower in ("clear completed goals", "clear done goals"):
        removed = goal_manager.clear_completed(profile)
        save_profile(profile)
        return f"Cleared {removed} completed goal(s).", True

    if lower in ("show progress", "progress report", "weekly review"):
        return format_progress_report(profile), True

    if lower in ("weekly personality review", "coach weekly review", "review my week"):
        return format_weekly_review(profile, goal_manager), True

    if lower.startswith("set engagement to "):
        level = user_text.split("to", 1)[1].strip().lower()
        if level not in ("low", "normal", "high"):
            return "Use: set engagement to low/normal/high", True
        profile["preferences"]["engagement_level"] = level
        save_profile(profile)
        return f"Engagement level set to {level}.", True

    if lower in ("enable super fast mode", "super fast mode", "set speed mode to super fast"):
        profile["preferences"]["speed_mode"] = "super_fast"
        profile["preferences"]["response_style"] = "quick"
        profile["preferences"]["engagement_level"] = "normal"
        save_profile(profile)
        return "Super fast mode enabled.", True

    if lower in ("disable super fast mode", "set speed mode to normal"):
        profile["preferences"]["speed_mode"] = "normal"
        save_profile(profile)
        return "Super fast mode disabled. Back to normal speed.", True

    if lower.startswith("set bedtime routine for "):
        hhmm, error = routine_engine.parse_time_from_text(user_text)
        if error:
            return error, True
        repeat_days = routine_engine.parse_repeat_days_from_text(user_text)
        alarm = schedule.add_alarm(hhmm, label="Bedtime Routine", repeat_days=repeat_days)
        repeat_text = format_repeat_days(repeat_days)
        return f"Bedtime routine set for {alarm.time_24h} ({repeat_text}). ID: {alarm.id}", True

    if lower in ("list morning routines", "show morning routines"):
        routines = [a for a in schedule.list_alarms() if a.label.lower().startswith("morning routine")]
        if not routines:
            return "No morning routines set.", True
        lines = [f"{a.id} -> {a.time_24h} ({format_repeat_days(a.repeat_days)})" for a in routines]
        return "Morning routines: " + " | ".join(lines), True

    if lower in ("list bedtime routines", "show bedtime routines"):
        routines = [a for a in schedule.list_alarms() if a.label.lower().startswith("bedtime routine")]
        if not routines:
            return "No bedtime routines set.", True
        lines = [f"{a.id} -> {a.time_24h} ({format_repeat_days(a.repeat_days)})" for a in routines]
        return "Bedtime routines: " + " | ".join(lines), True

    if lower.startswith("remove morning routine "):
        rid = user_text.split("remove morning routine", 1)[1].strip()
        if not rid:
            return "Use: remove morning routine <id>", True
        ok = schedule.remove_alarm(rid)
        if ok:
            return f"Removed morning routine {rid}.", True
        return f"Morning routine {rid} not found.", True

    if lower.startswith("remove bedtime routine "):
        rid = user_text.split("remove bedtime routine", 1)[1].strip()
        if not rid:
            return "Use: remove bedtime routine <id>", True
        ok = schedule.remove_alarm(rid)
        if ok:
            return f"Removed bedtime routine {rid}.", True
        return f"Bedtime routine {rid} not found.", True

    if lower in ("stop speaking", "stop voice"):
        tts_player.stop()
        return "", True

    if lower in ("stop", "stop now", "cancel"):
        tts_player.stop()
        runtime_flags["breathing_offer_active"] = False
        routine_engine.stop_breathing_guide_routine()
        return "", True

    if lower in ("pause voice", "pause speaking"):
        tts_player.pause()
        return "Paused voice playback.", True

    if lower in ("resume voice", "resume speaking"):
        tts_player.resume()
        return "Resumed voice playback.", True

    if lower in ("list local songs", "show local songs", "local songs"):
        songs = local_music.list_tracks()
        if not songs:
            return "No local songs found. Add files to the local_music folder.", True
        return "Local songs: " + " | ".join(songs[:20]), True

    if lower.startswith("play local"):
        ok_out, out_message = audio_output.ensure_output(profile)
        if not ok_out:
            save_profile(profile)
        query = user_text[len("play local") :].strip()
        ok, message = local_music.play_query(query)
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            save_profile(profile)
        if (not ok_out) and message:
            return f"{out_message} {message}".strip(), True
        return message, True

    if lower in ("pause local", "pause local music"):
        ok, message = local_music.pause()
        if ok:
            apply_music_led_preferences(led, profile, active=False)
            save_profile(profile)
        return message, True

    if lower in ("resume local", "resume local music"):
        ok, message = local_music.resume()
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            save_profile(profile)
        return message, True

    if lower in ("next local", "next local song"):
        ok, message = local_music.next_track()
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            save_profile(profile)
        return message, True

    if lower in ("stop local", "stop local music"):
        ok, message = local_music.stop()
        if ok:
            apply_music_led_preferences(led, profile, active=False)
            save_profile(profile)
        return message, True

    if lower.startswith("sleep timer "):
        parts = lower.split()
        minutes = parts[-1] if parts else ""
        if minutes.isdigit():
            message = sleep_routine.start_sleep_timer(int(minutes), on_sleep_timer_finish)
            return message, True
        return "Use: sleep timer 30", True

    if lower in ("cancel sleep timer", "stop sleep timer"):
        return sleep_routine.cancel_sleep_timer(), True

    if lower in ("sleep timer status", "bedtime status"):
        return sleep_routine.status_text(), True

    if lower.startswith("set alarm for "):
        t = user_text.split("for", 1)[1].strip()
        if not is_valid_time_24h(t):
            return "Use 24h format: set alarm for 07:30", True
        alarm = schedule.add_alarm(t, label="Bed Alarm")
        return (
            f"Alarm set for {alarm.time_24h}. ID: {alarm.id}",
            True,
        )

    if lower in ("list alarms", "show alarms", "my alarms"):
        alarms = schedule.list_alarms()
        if not alarms:
            return "No alarms set.", True
        lines = [f"{a.id} -> {a.time_24h} ({format_repeat_days(a.repeat_days)})" for a in alarms]
        return "Alarms: " + " | ".join(lines), True

    if lower.startswith("remove alarm "):
        alarm_id = user_text.split("remove alarm", 1)[1].strip()
        if not alarm_id:
            return "Use: remove alarm <id>", True
        ok = schedule.remove_alarm(alarm_id)
        if ok:
            return f"Removed alarm {alarm_id}.", True
        return f"Alarm {alarm_id} not found.", True

    if lower in ("pause music", "pause spotify", "pause song"):
        ok, message = spotify.pause()
        if (not ok) and should_use_local_music_fallback(message):
            ok, message = local_music.pause()
        if ok:
            apply_music_led_preferences(led, profile, active=False)
            save_profile(profile)
        return message, True

    if lower in ("resume music", "resume spotify", "play music"):
        ok, message = spotify.resume()
        if (not ok) and should_use_local_music_fallback(message):
            ok, message = local_music.resume()
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            save_profile(profile)
        return message, True

    if lower in ("next song", "next track", "skip song", "skip track"):
        ok, message = spotify.next_track()
        if (not ok) and should_use_local_music_fallback(message):
            ok, message = local_music.next_track()
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            save_profile(profile)
        return message, True

    if lower in ("previous song", "previous track", "go back song"):
        ok, message = spotify.previous_track()
        if not ok and should_use_local_music_fallback(message):
            ok, message = local_music.previous_track()
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            save_profile(profile)
        return message, True

    if lower.startswith("set volume to "):
        volume_match = re.search(r"(\d{1,3})", lower)
        if not volume_match:
            return "Use: set volume to 40", True
        percent = _clamp_percent(volume_match.group(1), default_value=40)
        ok, message = spotify.set_volume(percent)
        if ok:
            return message, True
        return message, True

    if lower in ("stop music", "stop spotify", "stop spotify music"):
        ok, message = spotify.pause()
        if not ok and should_use_local_music_fallback(message):
            ok, message = local_music.stop()
        if ok:
            apply_music_led_preferences(led, profile, active=False)
            save_profile(profile)
        return message, True

    if lower.startswith("play "):
        query = user_text.split("play", 1)[1].strip()
        if not query:
            return "Use: play <song name> or play local <song name>", True
        ok, message = spotify.play_track_query(query)
        if (not ok) and should_use_local_music_fallback(message):
            ok, message = local_music.play_query(query)
        if ok:
            apply_music_led_preferences(led, profile, active=True)
            save_profile(profile)
        return message, True

    if lower.startswith("log daily event "):
        title = user_text.split("log daily event", 1)[1].strip(" :.-")
        if not title:
            return "Use: log daily event <what happened today>", True
        stress_level = ""
        lowered_title = title.lower()
        if any(k in lowered_title for k in ("stress", "stressed", "overwhelmed", "مضغوط", "متوتر")):
            stress_level = "high"
        inserted = memory_store.inject_daily_events(
            [{"title": title, "stress_level": stress_level or "moderate", "source": "manual"}],
            source="manual",
        )
        if inserted:
            return "Saved daily event context. I will factor it into tonight responses.", True
        return "I could not save that daily event. Try a shorter line.", True

    if lower in ("daily events context", "show daily events", "stress day context"):
        line = memory_store.latest_daily_events_summary(hours=48, max_items=4)
        return (line or "No external daily events are saved yet."), True

    calendar_answer = get_online_calendar_answer(
        user_text,
        timezone="Asia/Kuwait",
        timeout_seconds=settings.ai_timeout_seconds,
    )
    if calendar_answer:
        return calendar_answer, True

    if lower.startswith("set animation to "):
        animation = user_text.split("to", 1)[1].strip()
        led.set_user_animation(animation)
        profile["preferences"]["user_strip_animation"] = animation
        save_profile(profile)
        return f"Set user strip animation to {animation}.", True

    if lower in ("list animations", "show animations", "what animations"):
        return "Available animations: solid, breathing, pulse, rainbow, wave, strobe. Music modes: pulse, wave, spectrum.", True

    if lower.startswith("set user strip to "):
        new_color = user_text.split("to", 1)[1].strip()
        profile["preferences"]["favorite_color"] = new_color
        save_profile(profile)
        led.set_color_value(new_color)
        return f"Set user strip color to {new_color}.", True

    if "time" in lower and ("pakistan" in lower or "karachi" in lower):
        now_pk = datetime.now(ZoneInfo("Asia/Karachi"))
        return (
            f"Current time in Pakistan is {now_pk.strftime('%I:%M %p')} on {now_pk.strftime('%Y-%m-%d')}.",
            True,
        )

    if (
        "manufacturer" in lower
        or "manufacurer" in lower
        or "manufactured" in lower
        or "builder" in lower
        or "built by" in lower
        or "builted" in lower
        or "built you" in lower
        or "made you" in lower
        or "created you" in lower
        or "creator" in lower
        or "who made you" in lower
        or "who built you" in lower
        or "who made" in lower
        or "who built" in lower
        or "who is the maker" in lower
    ):
        return "This bed is manufactured and built by Dana Abu Halifa.", True

    if lower.startswith("set my favourite color to "):
        new_color = user_text.split("to", 1)[1].strip()
        profile["preferences"]["favorite_color"] = new_color
        save_profile(profile)
        led.set_color_value(new_color)
        return f"Saved. I set your favorite color to {new_color}.", True

    personality = detect_personality_switch(user_text)
    if personality:
        profile["preferences"]["personality"] = personality
        save_profile(profile)
        return f"Switched to {personality} mode.", True

    action, color = detect_led_command(user_text)
    if action == "set_color":
        led.set_color_value(color)
        return f"Changed lights to {color}.", True
    if action == "brightness_up":
        led.brightness_up()
        return "Made the lights brighter.", True
    if action == "brightness_down":
        led.brightness_down()
        return "Dimmed the lights.", True

    breathing_start_intent = (
        lower.startswith("start breathing guide")
        or lower in ("breathing exercise", "4-7-8 breathing", "start breathing")
        or "start this technique" in normalized_lower
        or "start the technique" in normalized_lower
        or "begin this technique" in normalized_lower
        or (
            breathing_offer_active
            and normalized_lower.strip() in ("lets start", "let's start", "okay", "ok", "yes")
        )
    )

    if breathing_start_intent:
        minutes = routine_engine.parse_minutes_from_text(user_text, default_minutes=5)
        runtime_flags["breathing_offer_active"] = False
        return (
            routine_engine.start_breathing_guide_routine(
                led=led,
                tts_manager=tts,
                audio_player=tts_player,
                duration_minutes=minutes,
            ),
            True,
        )

    if lower in ("stop breathing guide", "stop breathing", "stop breathing exercise"):
        runtime_flags["breathing_offer_active"] = False
        return routine_engine.stop_breathing_guide_routine(), True

    if lower in ("dream journal", "dream prompt", "what did i dream"):
        if not dream_journal.should_prompt_dream(profile):
            return "Dream journal prompt is available in the morning window (6:00-11:59).", True
        msg = dream_journal.start_dream_prompt_session(profile, None, tts, tts_player)
        save_profile(profile)
        return msg, True

    if lower in ("dream insights", "dream patterns", "sleep dream analysis"):
        return dream_journal.get_dream_insights(profile), True

    if lower in ("enable dream journal", "disable dream journal"):
        enabled = lower.startswith("enable")
        msg = dream_journal.set_dream_prompt_enabled(profile, enabled)
        save_profile(profile)
        return msg, True

    if lower.startswith("i dreamed") or lower.startswith("my dream") or lower.startswith("i had a dream"):
        if dream_journal.is_prompting:
            msg, _ = dream_journal.capture_dream_response(user_text, profile)
            save_profile(profile)
            return msg, True

    if lower in ("adaptive personality insights", "adaptive personality", "personality insights"):
        return adaptive_personality.get_personality_insights(profile), True

    if lower in ("enable adaptive personality", "disable adaptive personality"):
        enabled = lower.startswith("enable")
        msg = adaptive_personality.set_adaptive_enabled(profile, enabled)
        save_profile(profile)
        return msg, True

    if lower.startswith("set adaptive personality to "):
        mode = user_text.split("set adaptive personality to", 1)[1].strip()
        msg = adaptive_personality.set_manual_override(profile, mode)
        save_profile(profile)
        return msg, True

    if lower in ("clear adaptive personality override", "clear personality override"):
        msg = adaptive_personality.clear_manual_override(profile)
        save_profile(profile)
        return msg, True

    return "", False

