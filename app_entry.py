"""Application entrypoint and startup bootstrap for Smart Bed AI runtime."""

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

import automation_engine

from automation_engine import (
    _parse_datetime_like,
    _has_pending_work_planning_reminder_today,
    init_automations,
    run_automations,
    format_planned_reminders,
    mark_reminder_completed,
    check_reminder_nudge,
    format_repeat_days
)
from led_controller import apply_led_hardware_config, apply_music_led_preferences
from prayer_handler import apply_fajr_gentle_light_scene, is_islamic_reminder_request, next_islamic_reminder
from voice_handler import (
    ensure_emotional_followup_shape,
    _is_meaningful_followup_turn,
    _extract_concern_emotion,
    _topic_summary,
    record_therapist_concern,
    build_bed_guide_steps,
    render_bed_guide_step,
    resolve_bed_guide_shortcut_intent,
    resolve_therapist_followup_if_answered,
    get_due_therapist_followup,
    _parse_yes_no,
    build_help_overview,
    build_sleep_help,
    _select_runtime_phrase,
    build_wake_greeting,
    build_transition_ack,
    should_use_local_music_fallback,
    _parse_health_summary_counts,
    _parse_health_warn_names,
    build_pilot_readiness_checklist,
    build_pilot_go_no_go,
    normalize_for_intent,
    has_any,
    _is_llm_fallback_response,
    _voice_offline_fallback_response,
    _is_voice_circuit_reset_command,
    _extract_openai_chat_text,
    _build_gpt_route_diagnostics,
    _request_openai_chat_reply,
    _looks_like_echo_capture,
    detect_natural_bed_intent,
    build_wake_aliases_from_profile,
    apply_bed_nickname,
    build_user_context,
    wants_detailed_answer,
    is_contextual_short_followup,
    clamp_non_detail_response,
    get_personality_voice,
    _execute_resolved_action,
    get_speed_tuning,
    get_turn_speed_tuning,
    ensure_progress_shape,
    _is_next_day,
    record_goal_completion,
    mark_session_started,
    build_progress_summary,
    format_progress_report,
    format_weekly_review,
    run_first_boot_intro,
    ensure_profile_shape,
    _is_simple_yes,
    _is_simple_no,
    _is_app_exit_command,
    _is_session_end_command,
    _is_wake_only_utterance,
    _resolve_followup_control_intent,
    _detect_compound_control_intents,
    _execute_compound_control_steps,
    _split_for_fast_tts_start,
    _infer_interim_intent_hint,
    play_tts_with_fast_start,
    run_streaming_voice_turn,
    get_query_text,
    handle_local_commands
)

def main():
    led = LEDController(
        user_strip_pin=settings.user_strip_pin,
        state_strip_pin=settings.state_strip_pin,
        user_strip_led_count=settings.user_strip_led_count,
        state_strip_led_count=settings.state_strip_led_count,
    )
    cache = CacheManager(ttl_seconds=settings.cache_ttl_seconds)
    schedule = ScheduleManager()
    goal_manager = SessionGoalManager()
    daily_life_support = DailyLifeSupport()
    goal_compass = GoalCompass()
    goal_strategy = GoalStrategyEngine()
    environment_orchestrator = EnvironmentOrchestrator()
    sleep_engine = SleepIntelligenceEngine()
    runtime_orchestrator = PersonalityRuntimeOrchestrator()
    sleep_routine = SleepRoutineManager()
    routine_engine = RoutineEngine()
    audio_output = AudioOutputManager()
    offline_pack = OfflineIntentPack()
    response_quality_gate = ResponseQualityGate(max_chars=500)
    voice_circuit_breaker = VoiceCircuitBreaker(
        failure_threshold=settings.voice_circuit_failure_threshold,
        backoff_base_seconds=settings.voice_circuit_backoff_base_seconds,
        backoff_max_seconds=settings.voice_circuit_backoff_max_seconds,
        reset_signal_path=settings.voice_circuit_reset_signal_path,
    )
    local_music = LocalMusicManager(music_dir=settings.local_music_dir)
    tts_player = AudioPlaybackController()
    breathing_guide = BreathingGuideEngine()
    dream_journal = DreamJournalManager()
    adaptive_personality = AdaptivePersonalityEngine()
    proactive_engine = ProactiveAutomationEngine()
    signature_engine = SignatureExperienceEngine()
    filler_manager = ConversationalFillerManager()
    safety_valve = SafetyValve()
    memory_store = LongTermMemoryStore()
    sensor_bridge = SensorBridge()
    echo_guard = AcousticEchoGuard(
        min_confidence_when_playing=settings.aec_min_confidence_when_playing,
    )
    wake_word_manager = WakeWordManager(
        mode=settings.wake_word_mode,
        wake_word=settings.wake_word_phrase,
        enforce_local_wake=settings.wake_word_enforce_local,
        voice_timeout_seconds=settings.wake_word_voice_timeout_seconds,
        voice_phrase_limit_seconds=settings.wake_word_phrase_limit_seconds,
        barge_in_timeout_seconds=settings.wake_word_barge_in_timeout_seconds,
        barge_in_phrase_limit_seconds=settings.wake_word_barge_in_phrase_limit_seconds,
        mic_device_index=settings.wake_word_mic_index,
    )
    stt = STTManager(
        api_key=settings.deepgram_api_key,
        model=settings.stt_model,
        timeout_seconds=max(10, int(settings.ai_timeout_seconds)),
        language_hint=settings.language_hint,
        mode=settings.stt_mode,
        local_model_size=settings.stt_local_model_size,
        local_device=settings.stt_local_device,
        local_compute_type=settings.stt_local_compute_type,
    )
    chat = ConversationEngine(
        api_key=settings.deepgram_api_key,
        model=settings.deepgram_voice_agent_model,
        timeout_seconds=settings.ai_timeout_seconds,
        voice_agent_url=settings.deepgram_voice_agent_url,
    )
    tts = TTSManager(
        api_key=settings.deepgram_tts_api_key,
        model=settings.tts_model,
        voice=settings.tts_voice,
        timeout_seconds=settings.ai_timeout_seconds,
    )
    realtime_voice_pipeline = RealtimeVoicePipeline(tts, tts_player)
    barge_in_monitor = ContinuousBargeInMonitor(wake_word_manager)
    stt.warm_up()
    routine_engine.set_breathing_guide(breathing_guide)
    breathing_guide.set_led_controller(led)
    breathing_guide.set_tts_manager(tts)
    breathing_guide.set_audio_player(tts_player)
    spotify = SpotifyManager(
        access_token=settings.spotify_access_token,
        device_id=settings.spotify_device_id,
        timeout_seconds=settings.ai_timeout_seconds,
    )
    backend_client = BedBackendClient(
        base_url=settings.app_backend_base_url,
        device_id=settings.bed_device_id,
        firmware_version=settings.bed_firmware_version,
        timeout_seconds=settings.ai_timeout_seconds,
    )

    def build_health_report() -> str:
        results = run_device_health_checks(settings, spotify, local_music, tts_player=tts_player)
        return format_health_report(results)

    def on_sleep_timer_finish():
        spotify.pause()
        local_music.pause()
        apply_music_led_preferences(led, profile, active=False)
        led.set_user_animation("breathing")
        led.set_user_brightness(0.2)
        led.set_state("sleep")
        print("Bed: Sleep timer ended. Music paused and lights dimmed.")

    def process_due_alarms():
        due = schedule.pop_due_alarms()
        for alarm in due:
            print(f"Bed: Alarm ringing now ({alarm.time_24h})!")
            if alarm.label.lower().startswith("morning routine"):
                if bool(profile.get("preferences", {}).get("adaptive_wake_enabled", True)):
                    print(f"Bed: {sleep_engine.adaptive_wake_routine_plan(profile)}")
                    led.set_user_animation("breathing")
                    led.set_user_brightness(0.35)
                print(f"Bed: {routine_engine.trigger_morning_routine(led, local_music)}")
            elif alarm.label.lower().startswith("bedtime routine"):
                sleep = profile.get("sleep", {})
                minutes = int(sleep.get("wind_down_minutes", 30) or 30)
                if bool(sleep.get("wind_down_enabled", False)):
                    print(f"Bed: {sleep_engine.environment_intelligence_tip(profile)}")
                print(
                    f"Bed: {routine_engine.start_bedtime_routine(led, local_music, sleep_routine, minutes=minutes)}"
                )
            else:
                led.set_state("speaking")
                ok, _ = local_music.play_query("")
                if ok:
                    apply_music_led_preferences(led, profile, active=True)
                led.set_state("listening")

    if not settings.deepgram_api_key:
        print("[WARN] DEEPGRAM_API_KEY is missing. Running with fallback responses.")
    if not settings.deepgram_tts_api_key:
        print("[WARN] DEEPGRAM_TTS_API_KEY/TTS_API_KEY is missing. TTS audio may be unavailable.")
    if not spotify.is_configured():
        print("[WARN] Spotify is not configured. Music commands will not work yet.")
    if not local_music.is_ready():
        print("[WARN] Local music is unavailable. Install pygame: pip install pygame")
    if not tts_player.is_ready():
        print("[WARN] TTS playback controller is unavailable. Install pygame for live voice playback.")
    if wake_word_manager.is_voice_mode() and (not wake_word_manager.is_voice_available()):
        print(
            "[WARN] Voice wake mode requested but microphone backend is unavailable. "
            "Falling back to keyboard mode. Try setting WAKE_WORD_MIC_INDEX in .env (use -1 for default)."
        )

    gpt_diag = _build_gpt_route_diagnostics(backend_client)
    if gpt_diag["openai_ready"]:
        print(f"[GPT] OpenAI direct route enabled with model={settings.openai_chat_model}")
    elif gpt_diag["backend_ready"]:
        print("[GPT] Backend cloud route enabled (cloud_chat entitlement required).")
    else:
        print("[GPT] No GPT route enabled; open questions will use fallback message.")

    print("Bed: Startup health -> " + build_health_report())

    profile = load_profile()
    if profile is None:
        profile = run_first_boot_intro(tts=tts, tts_player=tts_player)
        if profile is None:
            led.set_state("sleep")
            print("Bed: Setup cancelled. Exiting now.")
            return
    else:
        profile = ensure_profile_shape(profile)
        print(
            f"Bed: Welcome back, {profile.get('name', 'friend')} "
            f"({profile.get('age', '?')} years old)."
        )
    apply_led_hardware_config(led, profile)
    automation_engine.automation_profile_ref = profile
    wake_word_manager.set_wake_aliases(build_wake_aliases_from_profile(profile))
    print(f"Bed: {led.hardware_status()}")
    goal_manager.ensure_shape(profile)
    daily_life_support.ensure_shape(profile)
    goal_compass.ensure_shape(profile)
    goal_strategy.ensure_shape(profile)
    ensure_progress_shape(profile)
    environment_orchestrator.ensure_shape(profile)
    sleep_engine.ensure_shape(profile)
    runtime_orchestrator.ensure_shape(profile)
    proactive_engine.ensure_shape(profile)
    safety_valve.ensure_shape(profile)
    profile.setdefault("runtime_flags", {})
    profile["runtime_flags"].setdefault("sensor_pressure_active", False)
    profile["runtime_flags"].setdefault("sensor_motion_active", False)
    stt.language_hint = str(profile.get("preferences", {}).get("language", "auto") or "auto")
    output_ok, _ = audio_output.ensure_output(profile)
    if not output_ok:
        save_profile(profile)
    print(f"Bed: {audio_output.output_status(profile)}")
    save_profile(profile)
    automation_engine.sleep_mode_active = bool(profile.get("runtime_flags", {}).get("sleep_mode", False))

    def _automation_wake_up_led_scene():
        profile.setdefault("runtime_flags", {})["sleep_mode"] = False
        led.set_user_animation("breathing")
        led.set_user_brightness(0.45)
        led.set_state("listening")
        save_profile(profile)

    def _automation_fajr_gentle_light_scene():
        apply_fajr_gentle_light_scene(led)

    automation_engine.automation_runtime_hooks["wake_up_scene"] = _automation_wake_up_led_scene
    automation_engine.automation_runtime_hooks["wake_up_led_scene"] = _automation_wake_up_led_scene
    automation_engine.automation_runtime_hooks["fajr_gentle_light_scene"] = _automation_fajr_gentle_light_scene
    init_automations()

    favorite_color = profile.get("preferences", {}).get("favorite_color")
    user_animation = profile.get("preferences", {}).get("user_strip_animation", "solid")
    led.set_user_animation(user_animation)
    apply_music_led_preferences(led, profile)
    if favorite_color:
        led.set_color_value(favorite_color)
        print(f"Bed: Set your lights to your favorite color, {favorite_color}.")

    print("Smart Bed MVP (API-first STT/TTS + GPT + cache)")
    if wake_word_manager.is_voice_available():
        print("Type 'exit' to quit. Voice wake mode is active.")
    else:
        print('Type "exit" to quit. Type "wake" to simulate wake word.')
        print('Bed: Keyboard text mode is active. Type your message and I will reply using current speakers.')
    print("Bed: Wake phrases -> " + " | ".join(wake_word_manager.get_wake_phrases()))
    led.set_state("standby")

    while True:
        process_due_alarms()
        if settings.enable_sensor_bridge:
            runtime_flags = profile.get("runtime_flags", {})
            pressure_active = bool(runtime_flags.get("sensor_pressure_active", False)) and bool(settings.sensor_pressure_enabled)
            motion_active = bool(runtime_flags.get("sensor_motion_active", False)) and bool(settings.sensor_motion_enabled)
            sensor_event = sensor_bridge.classify_event(
                pressure_active=pressure_active,
                motion_active=motion_active,
                now=datetime.now(),
            )
            if sensor_event:
                proactive_greeting = sensor_bridge.proactive_greeting(sensor_event, user_name=profile.get("name", ""))
                if proactive_greeting:
                    sensor_tts = sensor_bridge.tts_profile_for_time(datetime.now())
                    led.set_state("speaking")
                    proactive_audio = play_tts_with_fast_start(
                        tts,
                        tts_player,
                        proactive_greeting,
                        voice_override=get_personality_voice(profile),
                        pace_override=float(sensor_tts.get("pace_multiplier", 1.0) or 1.0),
                        profile_override=str(sensor_tts.get("profile_override", "") or ""),
                    )
                    print(f"Bed: {proactive_greeting}")
                    if proactive_audio:
                        print(f"Bed: Audio saved at {proactive_audio}")
                    led.set_state("standby")
        wake_text = wake_word_manager.wait_for_wake_text()
        runtime_orchestrator.record_wake_phrase(profile, wake_text)
        save_profile(profile)
        if wake_text in ("exit", "quit", "bye"):
            led.set_state("sleep")
            print("Bed: Good night, sleep well.")
            break

        if not wake_word_manager.matches_wake_text(wake_text):
            print("Bed: Waiting for wake word...")
            continue

        greeting_line = build_wake_greeting(profile, runtime_orchestrator)
        environment_orchestrator.preload_transition_for_response(led, profile, greeting_line)
        led.set_state("speaking")
        print(f"Bed: {greeting_line}")
        greeting_audio = play_tts_with_fast_start(
            tts,
            tts_player,
            greeting_line,
            voice_override=get_personality_voice(profile),
        )
        if greeting_audio:
            print(f"Bed: Audio saved at {greeting_audio}")
        interrupt_text = wake_word_manager.capture_barge_in_text()
        if interrupt_text and _is_wake_only_utterance(wake_word_manager, interrupt_text):
            print("Bed: Wake word acknowledged. I am already listening.")
            pending_user_text = ""
            led.set_state("listening")
        elif interrupt_text:
            tts_player.stop()
            led.set_state("listening")
            pending_user_text = interrupt_text
        else:
            pending_user_text = ""
            led.set_state("listening")
        mark_session_started(profile)
        save_profile(profile)
        last_focus_user_text = ""
        last_assistant_response = ""
        session_turn_count = 0

        def _play_automation_reply(reply_text: str):
            nonlocal pending_user_text, last_assistant_response
            text = str(reply_text or "").strip()
            if not text:
                return
            print(f"Bed: {text}")
            last_assistant_response = text
            environment_orchestrator.preload_transition_for_response(led, profile, text)
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(
                text,
                voice_override=get_personality_voice(profile),
            )
            if not audio_file:
                print("[TTS][WARN] No audio generated for automation reply.")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file and tts_player.play_file(audio_file):
                print("Bed: Playing response audio now.")
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
                return
            led.set_state("listening")

        automation_engine.automation_reply_handler = _play_automation_reply

        def maybe_emit_proactive() -> str:
            now = datetime.now()
            invisible_routine = memory_store.infer_invisible_routine(now=now, days=7)
            session_state = {
                "interrupt_count_today": runtime_orchestrator.current_interrupt_count(profile, now=now),
                "active_goals_count": len([g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]),
                "bedtime_drift_alert": sleep_engine.bedtime_drift_alert(profile),
                "invisible_routine": invisible_routine,
            }
            suggestions = proactive_engine.evaluate(profile, now=now, session_state=session_state)
            if not suggestions:
                return ""
            top = suggestions[0]
            line = str(top.get("line", "")).strip()
            prompt_level = runtime_orchestrator.proactive_prompt_level(profile, now=now)
            if prompt_level == "minimal" and "." in line:
                line = line.split(".", 1)[0].strip() + "."
            if not line:
                return ""
            if str(top.get("type", "")).strip().lower() == "action_bundle" and str(top.get("intent", "")).strip().lower():
                _execute_resolved_action(
                    {
                        "intent": str(top.get("intent", "")).strip().lower(),
                        "slots": top.get("slots", {}) if isinstance(top.get("slots", {}), dict) else {},
                    },
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
            proactive_engine.mark_executed(profile, {"key": top.get("key", ""), "line": line}, now=now)
            save_profile(profile)
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(line, voice_override=get_personality_voice(profile))
            print(f"Bed: {line}")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file:
                tts_player.play_file(audio_file)
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                runtime_orchestrator.record_interrupt(profile)
                save_profile(profile)
                tts_player.stop()
                led.set_state("listening")
                return interrupt_text
            led.set_state("listening")
            return ""

        personality_for_session = profile.get("preferences", {}).get("personality", "therapist")
        continuity_callback = runtime_orchestrator.continuity_callback_line(profile, personality_for_session)
        if continuity_callback:
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(
                continuity_callback,
                voice_override=get_personality_voice(profile),
            )
            print(f"Bed: {continuity_callback}")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file:
                tts_player.play_file(audio_file)
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
            else:
                led.set_state("listening")

        proactive_interrupt = maybe_emit_proactive()
        if proactive_interrupt:
            pending_user_text = proactive_interrupt

        if goal_manager.should_prompt_nightly_checkin(profile):
            checkin_prompt = goal_manager.build_nightly_checkin_prompt(profile)
            if checkin_prompt:
                goal_manager.mark_nightly_checkin_prompted(profile)
                save_profile(profile)
                led.set_state("speaking")
                audio_file = tts.synthesize_to_mp3(
                    checkin_prompt,
                    voice_override=get_personality_voice(profile),
                )
                print(f"Bed: {checkin_prompt}")
                print(f"Bed: Audio saved at {audio_file}")
                if audio_file:
                    tts_player.play_file(audio_file)
                interrupt_text = wake_word_manager.capture_barge_in_text()
                if interrupt_text:
                    tts_player.stop()
                    led.set_state("listening")
                    pending_user_text = interrupt_text
                else:
                    led.set_state("listening")

        emotion_state_session = runtime_orchestrator.latest_emotion_state(profile)
        active_goals = [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]
        if goal_strategy.should_trigger_recovery_protocol(profile, days=7, threshold=2):
            recovery_msg = goal_strategy.build_recovery_protocol_dialogue(profile, active_goals)
            goal_strategy.mark_recovery_prompted_today(profile)
            save_profile(profile)
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(
                recovery_msg,
                voice_override=get_personality_voice(profile),
            )
            print(f"Bed: {recovery_msg}")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file:
                tts_player.play_file(audio_file)
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
            else:
                led.set_state("listening")

        if runtime_orchestrator.should_send_priority_reminder(
            profile,
            active_goals=active_goals,
            emotion_state=emotion_state_session,
        ):
            reminder = runtime_orchestrator.build_priority_reminder(active_goals)
            if reminder:
                runtime_orchestrator.mark_priority_reminder_sent(profile)
                save_profile(profile)
                led.set_state("speaking")
                audio_file = tts.synthesize_to_mp3(reminder, voice_override=get_personality_voice(profile))
                print(f"Bed: {reminder}")
                print(f"Bed: Audio saved at {audio_file}")
                if audio_file:
                    tts_player.play_file(audio_file)
                interrupt_text = wake_word_manager.capture_barge_in_text()
                if interrupt_text:
                    tts_player.stop()
                    led.set_state("listening")
                    pending_user_text = interrupt_text
                else:
                    led.set_state("listening")

        active_goals = [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"]
        top_goals = ", ".join(g.get("title", "") for g in active_goals[:2]) or "none"
        progress_report = format_progress_report(profile)
        auto_brief_enabled = bool(profile.get("preferences", {}).get("auto_brief_enabled", False))

        if auto_brief_enabled and sleep_engine.should_send_morning_brief(profile):
            dream_insights = dream_journal.get_dream_insights(profile)
            brief = sleep_engine.build_morning_brief(
                profile,
                top_goals=top_goals,
                progress_report=progress_report,
                dream_insights=dream_insights,
            )
            sleep_engine.mark_morning_brief_sent(profile)
            save_profile(profile)
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(brief, voice_override=get_personality_voice(profile))
            print(f"Bed: {brief}")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file:
                tts_player.play_file(audio_file)
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                runtime_orchestrator.record_interrupt(profile)
                save_profile(profile)
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
            else:
                led.set_state("listening")

        elif auto_brief_enabled and sleep_engine.should_send_evening_brief(profile):
            brief = sleep_engine.build_evening_brief(profile, top_goals=top_goals, progress_report=progress_report)
            sleep_engine.mark_evening_brief_sent(profile)
            save_profile(profile)
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(brief, voice_override=get_personality_voice(profile))
            print(f"Bed: {brief}")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file:
                tts_player.play_file(audio_file)
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
            else:
                led.set_state("listening")

        if auto_brief_enabled and sleep_engine.should_send_bedtime_drift_alert(profile):
            drift_alert = sleep_engine.bedtime_drift_alert(profile)
            sleep_engine.mark_bedtime_drift_alert_sent(profile)
            save_profile(profile)
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(drift_alert, voice_override=get_personality_voice(profile))
            print(f"Bed: {drift_alert}")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file:
                tts_player.play_file(audio_file)
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
            else:
                led.set_state("listening")

        elif auto_brief_enabled and sleep_engine.should_send_weekly_recovery_score_card(profile):
            recovery_card = sleep_engine.weekly_recovery_score_card(profile)
            sleep_engine.mark_weekly_recovery_score_card_sent(profile)
            save_profile(profile)
            led.set_state("speaking")
            audio_file = tts.synthesize_to_mp3(recovery_card, voice_override=get_personality_voice(profile))
            print(f"Bed: {recovery_card}")
            print(f"Bed: Audio saved at {audio_file}")
            if audio_file:
                tts_player.play_file(audio_file)
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
            else:
                led.set_state("listening")

        def _dispatch_local_command(text: str) -> tuple[str, bool]:
            return handle_local_commands(
                text,
                profile,
                led,
                spotify,
                local_music,
                schedule,
                goal_manager,
                daily_life_support,
                goal_compass,
                sleep_engine,
                environment_orchestrator,
                runtime_orchestrator,
                goal_strategy,
                sleep_routine,
                routine_engine,
                tts_player,
                audio_output,
                backend_client,
                build_health_report,
                on_sleep_timer_finish,
                breathing_guide,
                dream_journal,
                adaptive_personality,
                proactive_engine,
                signature_engine,
                tts,
                wake_word_manager,
                memory_store,
            )

        def _log_intent(intent_name: str, original_text: str):
            print(f"[INTENT][{intent_name}] {str(original_text or '').strip()}")

        def set_user_led_color(name: str):
            led.set_user_animation("solid")
            led.set_color_value(name)

        def activate_sleep_scene():
            scene = {
                "key": "intent_sleep_mode",
                "animation": "breathing",
                "color": "orange",
                "brightness": 0.18,
                "line": "Environment scene: sleep mode.",
            }
            scene_line = environment_orchestrator.apply_scene(led, profile, scene)
            profile.setdefault("runtime_flags", {})["sleep_mode"] = True
            automation_engine.sleep_mode_active = True
            # Reuse existing sleep tracking so sleep-mode intent updates bedtime context.
            bedtime_line = sleep_engine.record_bedtime_now(profile)
            # Optional: dim state LEDs by using the existing sleep state profile.
            led.set_state("sleep")
            save_profile(profile)
            return f"{scene_line} {bedtime_line}".strip()

        def handle_light_intent(text: str) -> str:
            result = handle_light_intent_result(text)
            return apply_command_result_effects(result)

        def handle_time_intent(text: str) -> str:
            _log_intent("TIME", text)
            lowered = str(text or "").lower()
            now = datetime.now()
            time_text = now.strftime("%I:%M %p").lstrip("0")
            day_name = now.strftime("%A")
            date_text = now.strftime("%B %d, %Y")
            has_time = "time" in lowered
            has_day_or_date = ("day" in lowered) or ("date" in lowered) or ("today" in lowered)
            if has_day_or_date and not has_time:
                return f"Today is {day_name}, {date_text}."
            if has_time and not has_day_or_date:
                return f"It is {time_text} on {day_name}."
            return f"It is {time_text} on {day_name}, {date_text}."

        def handle_sleep_intent(text: str) -> str:
            raw_text = str(text or "").strip()
            print(f"[INTENT][SLEEP] activating sleep scene for text='{raw_text}'")
            result = handle_sleep_intent_result(text)
            return apply_command_result_effects(result)

        def apply_command_result_effects(result: CommandResult) -> str:
            """Apply command effects emitted by pure command handlers."""
            response_text = str(result.text or "")
            for effect in result.effects:
                kind = str(effect.kind or "").strip().lower()
                payload = effect.payload if isinstance(effect.payload, dict) else {}
                if kind == "say":
                    response_text = str(payload.get("text", response_text) or response_text)
                    continue
                if kind == "led":
                    op = str(payload.get("op", "") or "").strip().lower()
                    if op == "set_user_color":
                        color = str(payload.get("color", "") or "").strip().lower()
                        if color:
                            set_user_led_color(color)
                        continue
                    if op == "set_user_brightness":
                        brightness = payload.get("brightness")
                        if isinstance(brightness, (int, float)):
                            led.set_user_brightness(float(brightness))
                        continue
                    target_state = str(payload.get("state", "") or "").strip().lower()
                    if target_state in {"listening", "speaking", "sleep", "standby"}:
                        led.set_state(target_state)
                    continue
                if kind != "store":
                    continue

                op = str(payload.get("op", "") or "").strip().lower()
                if op == "append_planned_reminder":
                    reminder = payload.get("reminder", {})
                    if isinstance(reminder, dict):
                        automation_engine.planned_reminders.append(reminder)
                elif op == "set_automation_engine.reminder_nudge_state":
                    state = payload.get("state", {})
                    if isinstance(state, dict):
                        automation_engine.reminder_nudge_state.update(state)
                elif op == "activate_sleep_scene":
                    sleep_mode_line = activate_sleep_scene()
                    if sleep_mode_line:
                        print(f"[INTENT][SLEEP] {sleep_mode_line}")
            return response_text

        def handle_reminder_intent(text: str) -> str:
            result = handle_reminder_intent_result(
                text,
                reminders_summary=format_automation_engine.planned_reminders(),
                now_provider=datetime.now,
            )
            return apply_command_result_effects(result)

        register_command_handler(
            "lights",
            handle_light_intent,
            aliases=("light", "lights"),
        )
        register_command_handler(
            "sleep",
            handle_sleep_intent,
            aliases=("sleep mode", "go to sleep", "bedtime mode"),
        )
        register_command_handler(
            "reminders",
            handle_reminder_intent,
            aliases=(
                "show my reminders",
                "list reminders",
                "remind me",
                "wake me up",
            ),
        )

        def handle_chat_intent(text: str) -> str:
            _log_intent("CHAT", text)
            local_response, handled = _dispatch_local_command(text)
            if handled:
                return str(local_response or "")

            logger = __import__("logging").getLogger(__name__)
            user_text = str(text or "").strip()
            lowered_user_text = user_text.lower()
            if not user_text:
                return "I did not catch that. Please say it again."

            # ...existing code for other chat intents...
            completion_phrases = (
                "i finished",
                "i'm done",
                "i am done",
                "i finished my work and planning",
            )
            if any(phrase in lowered_user_text for phrase in completion_phrases):
                print(f"[INTENT][CHAT] reminder_completion for text='{user_text}'")
                for reminder in reversed(automation_engine.planned_reminders):
                    if bool(reminder.get("completed", False)):
                        continue
                    reminder["completed"] = True
                    reminder["nudge_sent"] = True
                    done_task = str(reminder.get("task", "") or "").strip()
                    print(f"[REMINDER] Marked completed: task='{done_task}'.")
                    break
                automation_engine.reminder_nudge_state["active"] = False
                automation_engine.reminder_nudge_state["task"] = ""
                automation_engine.reminder_nudge_state["nudge_sent"] = False
                automation_engine.reminder_nudge_state["nudge_time"] = None
                try:
                    activate_sleep_scene()
                except NameError:
                    # TODO: trigger relax LED scene here
                    pass
                except Exception as exc:
                    print(f"[INTENT][CHAT][WARN] Could not trigger relax scene: {exc}")
                return "Good, your work and planning are done for today. Now you can rest."

            if "joke" in lowered_user_text:
                print(f"[INTENT][CHAT] local_joke for text={user_text!r}")
                return "Why did the bed stay calm? Because it knew rest is part of winning."

            if ("motivate me" in lowered_user_text) or ("motivation" in lowered_user_text):
                print(f"[INTENT][CHAT] local_motivation for text={user_text!r}")
                return "Stay disciplined, be patient, and keep working hard; small steps every day create big results."

            if "how are you" in lowered_user_text:
                print(f"[INTENT][CHAT] local_status for text={user_text!r}")
                return "I am running well and ready to help you."

            # ...existing code for other chat intents...

            if is_islamic_reminder_request(lowered_user_text):
                print(f"[INTENT][CHAT] local_islamic_reminder for text={user_text!r}")
                return next_islamic_reminder(profile)

            print(f"[INTENT][CHAT] GPT route for text='{user_text}'")

            speed_tuning = get_turn_speed_tuning(profile, user_text)
            realtime_context = ""
            if is_realtime_query(user_text) and speed_tuning["allow_realtime_context"]:
                realtime_context = fetch_realtime_context(
                    user_text,
                    timeout_seconds=settings.ai_timeout_seconds,
                )

            personality = str(profile.get("preferences", {}).get("personality", "therapist") or "therapist")
            memory_context_line = memory_store.memory_prompt_line(user_text)
            user_context = build_user_context(
                profile,
                goals_context=goal_manager.context_summary(profile),
                compass_context=goal_compass.summary_line(
                    profile,
                    [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"],
                ),
                progress_context=build_progress_summary(profile),
                emotion_context="",
                sleep_context=sleep_engine.summary_line(profile),
                runtime_context=runtime_orchestrator.emotion_trend_summary(profile),
                goal_strategy_context=goal_strategy.context_summary(profile),
                environment_context="",
                daily_life_context=str(profile.get("daily_life", {}).get("last_coaching_tone", "")),
                detailed_mode=False,
            )
            if memory_context_line:
                user_context = (user_context + "\n" + memory_context_line).strip()
            daily_events_line = memory_store.latest_daily_events_summary(hours=36, max_items=3)
            if daily_events_line:
                user_context = (user_context + "\n" + daily_events_line).strip()

            response_text = ""
            gpt_diag = _build_gpt_route_diagnostics(backend_client)
            if gpt_diag["openai_ready"]:
                print(f"[FLOW] GPT provider: direct OpenAI API (model={settings.openai_chat_model}).")
                ok_openai, openai_text = _request_openai_chat_reply(
                    user_text_for_ai=user_text,
                    personality=personality,
                    user_context=user_context,
                    realtime_context=realtime_context,
                    max_response_tokens=speed_tuning["max_tokens"],
                )
                if ok_openai:
                    response_text = str(openai_text or "").strip()
                else:
                    print(f"[FLOW][WARN] Direct OpenAI GPT failed: {openai_text}")

            if (not response_text) and gpt_diag["backend_ready"] and (backend_client is not None):
                ent_ok, _ = backend_client.fetch_entitlement()
                if (not ent_ok) or (not backend_client.is_feature_allowed("cloud_chat")):
                    print("[FLOW][WARN] Backend GPT route unavailable: cloud_chat entitlement is inactive.")
                else:
                    print("[FLOW] GPT provider: backend cloud_chat proxy.")
                    ok_cloud, cloud_text, _ = backend_client.request_ai_chat(
                        text=user_text,
                        personality=personality,
                        user_context=user_context,
                        realtime_context=realtime_context,
                        max_response_tokens=speed_tuning["max_tokens"],
                    )
                    if ok_cloud:
                        response_text = str(cloud_text or "").strip()
                    else:
                        print(f"[FLOW][WARN] Backend GPT request failed: {cloud_text}")
                        offline_response, handled_offline = offline_pack.handle(user_text)
                        response_text = offline_response if handled_offline else str(cloud_text or "").strip()

            if not response_text:
                offline_response, handled_offline = offline_pack.handle(user_text)
                if handled_offline:
                    response_text = offline_response
                else:
                    missing = " | ".join(gpt_diag["issues"]) if gpt_diag["issues"] else "no GPT route is currently available"
                    response_text = f"GPT route is unavailable right now. {missing}"
                print(f"[FLOW][WARN] GPT route unavailable. {response_text}")

            return str(response_text or "")

        def handle_bed_command(text: str) -> str:
            lowered = str(text or "").lower()
            matched_handler = match_command_handler(text)
            if matched_handler is handle_light_intent:
                return matched_handler(text)
            if ("time" in lowered) or ("day" in lowered) or ("date" in lowered) or ("today" in lowered):
                return handle_time_intent(text)
            if matched_handler is not None:
                return matched_handler(text)
            return handle_chat_intent(text)

        while True:
            if voice_circuit_breaker.consume_manual_reset_signal():
                breaker_state = voice_circuit_breaker.snapshot()
                emit_json_log(
                    logger,
                    level="info",
                    event_type="voice_circuit_manual_reset",
                    trace_id="voice_runtime",
                    metadata={
                        "source": "control_signal",
                        "state": str(breaker_state.get("state", "")),
                        "failure_count": int(breaker_state.get("failure_count", 0) or 0),
                    },
                )
                print(
                    "[VOICE][CIRCUIT] Manual reset applied from control signal. "
                    f"state={breaker_state.get('state')} failures={breaker_state.get('failure_count')}"
                )
            process_due_alarms()
            run_automations()
            nudge_text = check_reminder_nudge()
            if nudge_text:
                print(f"Bed: {nudge_text}")
                last_assistant_response = nudge_text
                environment_orchestrator.preload_transition_for_response(led, profile, nudge_text)
                led.set_state("speaking")
                nudge_audio = tts.synthesize_to_mp3(
                    nudge_text,
                    voice_override=get_personality_voice(profile),
                )
                if not nudge_audio:
                    print("[TTS][WARN] No audio generated for reminder nudge.")
                print(f"Bed: Audio saved at {nudge_audio}")
                if nudge_audio and tts_player.play_file(nudge_audio):
                    print("Bed: Playing response audio now.")
                interrupt_text = wake_word_manager.capture_barge_in_text()
                if interrupt_text:
                    tts_player.stop()
                    led.set_state("listening")
                    pending_user_text = interrupt_text
                    continue
                led.set_state("listening")
                continue
            stt.language_hint = str(profile.get("preferences", {}).get("language", "auto") or "auto")
            priority_followup_turn = bool(pending_user_text)
            interim_intent_hint = {}
            if pending_user_text:
                user_text, _query_confidence = pending_user_text, 1.0
            else:
                def _capture_interim_hint(hint: dict):
                    nonlocal interim_intent_hint
                    candidate = dict(hint or {})
                    if not candidate:
                        return
                    if candidate == interim_intent_hint:
                        return
                    interim_intent_hint = candidate
                    print(f"Bed (intent-prep): {candidate.get('intent', 'unknown')}")

                user_text, _query_confidence = get_query_text(
                    stt,
                    wake_word_manager,
                    interim_intent_callback=_capture_interim_hint,
                    require_api_stream=settings.stt_require_api_stream,
                )
            pending_user_text = ""
            lower_text = user_text.lower().strip()

            if _is_voice_circuit_reset_command(user_text):
                breaker_state = voice_circuit_breaker.manual_reset(reason="runtime_command")
                emit_json_log(
                    logger,
                    level="info",
                    event_type="voice_circuit_manual_reset",
                    trace_id="voice_runtime",
                    metadata={
                        "source": "runtime_command",
                        "state": str(breaker_state.get("state", "")),
                        "failure_count": int(breaker_state.get("failure_count", 0) or 0),
                    },
                )
                print(
                    "[VOICE][CIRCUIT] Manual reset requested from runtime command. "
                    f"state={breaker_state.get('state')} failures={breaker_state.get('failure_count')}"
                )
                print("Bed: Voice pipeline recovery circuit reset. Normal voice processing is restored.")
                led.set_state("listening")
                continue

            if _is_wake_only_utterance(wake_word_manager, user_text):
                print("Bed: I am already awake. Please tell me your command.")
                led.set_state("listening")
                continue

            if _looks_like_echo_capture(user_text, last_assistant_response, _query_confidence):
                print("Bed: Ignoring likely speaker-echo capture. Please speak again.")
                led.set_state("listening")
                continue

            if _is_app_exit_command(user_text):
                routine_engine.stop_breathing_guide_routine()
                led.set_state("sleep")
                print("Bed: Good night, sleep well.")
                return

            if _is_session_end_command(user_text):
                routine_engine.stop_breathing_guide_routine()
                led.set_state("standby")
                print("Bed: Session ended. Say 'wake', 'hey smart bed', or 'hello' when you need me.")
                break

            if not user_text:
                led.set_state("listening")
                continue

            runtime_orchestrator.record_cognitive_load_signal(profile, user_text)
            cognitive_load_mode = runtime_orchestrator.cognitive_load_mode(profile)

            session_turn_count += 1
            if session_turn_count % 3 == 0:
                proactive_interrupt = maybe_emit_proactive()
                if proactive_interrupt:
                    pending_user_text = proactive_interrupt

            if should_run_fast_protocol(user_text, safety_level="none"):
                protocol = build_fast_protocol_message()
                led.set_state("speaking")
                audio_file = tts.synthesize_to_mp3(
                    protocol,
                    voice_override=get_personality_voice(profile),
                )
                print(f"Bed: {protocol}")
                print(f"Bed: Audio saved at {audio_file}")
                if audio_file:
                    tts_player.play_file(audio_file)
                interrupt_text = wake_word_manager.capture_barge_in_text()
                if interrupt_text:
                    runtime_orchestrator.record_interrupt(profile)
                    save_profile(profile)
                    tts_player.stop()
                    led.set_state("listening")
                    pending_user_text = interrupt_text
                    continue
                led.set_state("listening")
                continue

            print(f"[FLOW] STT captured chars={len(user_text)}")
            voice_failure_type = {"name": ""}
            voice_trace_id = f"voice_{time.time_ns()}"

            def _run_voice_pipeline_operation() -> dict:
                raw_response_text = str(handle_bed_command(user_text) or "").strip()
                response_text_inner, quality_gate = response_quality_gate.apply(raw_response_text)
                if not response_text_inner:
                    raise RuntimeError("empty_reply_after_quality_gate")

                audio_file_inner = tts.synthesize_to_mp3(
                    response_text_inner,
                    voice_override=get_personality_voice(profile),
                )
                if not audio_file_inner:
                    raise RuntimeError("tts_unavailable")

                environment_orchestrator.preload_transition_for_response(led, profile, response_text_inner)
                led.set_state("speaking")
                played = bool(tts_player.play_file(audio_file_inner))
                return {
                    "response_text": response_text_inner,
                    "audio_file": str(audio_file_inner),
                    "played": played,
                    "quality_gate": quality_gate,
                }

            def _voice_fallback(reason: str) -> dict:
                fallback_text, quality_gate = response_quality_gate.apply(
                    _voice_offline_fallback_response(offline_pack, user_text)
                )
                return {
                    "response_text": fallback_text,
                    "audio_file": "",
                    "played": False,
                    "reason": reason,
                    "quality_gate": quality_gate,
                }

            def _on_voice_failure(exc: Exception):
                voice_failure_type["name"] = type(exc).__name__
                emit_json_log(
                    logger,
                    level="error",
                    event_type="voice_pipeline_failure",
                    trace_id=voice_trace_id,
                    metadata={
                        "error_type": voice_failure_type["name"],
                    },
                )

            turn_result, used_fallback, breaker_reason, breaker_snapshot = voice_circuit_breaker.run(
                operation=_run_voice_pipeline_operation,
                fallback=_voice_fallback,
                on_failure=_on_voice_failure,
            )

            response_text = str(turn_result.get("response_text", "") or "").strip()
            quality_gate_meta = turn_result.get("quality_gate", {})
            if isinstance(quality_gate_meta, dict):
                if bool(quality_gate_meta.get("used_fallback", False)):
                    print(f"[QUALITY_GATE] safe fallback applied reason={quality_gate_meta.get('reason', 'unknown')}")
                elif bool(quality_gate_meta.get("trimmed", False)):
                    print(
                        "[QUALITY_GATE] response trimmed "
                        f"original_len={quality_gate_meta.get('original_length', 0)} "
                        f"final_len={quality_gate_meta.get('final_length', 0)}"
                    )
            if not response_text:
                print("[FLOW][WARN] Voice pipeline fallback returned empty text.")
                led.set_state("listening")
                continue

            if used_fallback:
                tts_player.stop()
                cooldown_remaining = float(breaker_snapshot.get("cooldown_seconds_remaining", 0.0) or 0.0)
                failure_suffix = (
                    f" failure_type={voice_failure_type['name']}" if voice_failure_type["name"] else ""
                )
                emit_json_log(
                    logger,
                    level="warning",
                    event_type="voice_pipeline_fallback",
                    trace_id=voice_trace_id,
                    metadata={
                        "reason": breaker_reason,
                        "state": str(breaker_snapshot.get("state", "")),
                        "failure_count": int(breaker_snapshot.get("failure_count", 0) or 0),
                        "cooldown_seconds_remaining": round(cooldown_remaining, 2),
                        "failure_type": str(voice_failure_type["name"] or ""),
                    },
                )
                print(
                    "[VOICE][CIRCUIT] Offline fallback engaged "
                    f"reason={breaker_reason} "
                    f"state={breaker_snapshot.get('state')} "
                    f"failures={breaker_snapshot.get('failure_count')} "
                    f"cooldown_remaining={cooldown_remaining:.2f}s"
                    f"{failure_suffix}"
                )
                print(f"Bed: {response_text}")
                print("Bed: Voice pipeline offline fallback is active. Audio playback skipped.")
                last_assistant_response = response_text
                led.set_state("listening")
                continue

            audio_file = str(turn_result.get("audio_file", "") or "")
            emit_json_log(
                logger,
                level="info",
                event_type="voice_pipeline_success",
                trace_id=voice_trace_id,
                metadata={
                    "used_fallback": False,
                    "breaker_state": str(breaker_snapshot.get("state", "")),
                    "audio_played": bool(turn_result.get("played", False)),
                    "audio_file_present": bool(audio_file),
                    "response_chars": len(response_text),
                },
            )
            print(f"[FLOW] Reply text chars={len(response_text)}")
            last_assistant_response = response_text

            print(f"Bed: {response_text}")
            print(f"Bed: Audio saved at {audio_file}")
            if bool(turn_result.get("played", False)):
                print("Bed: Playing response audio now.")
            interrupt_text = wake_word_manager.capture_barge_in_text()
            if interrupt_text:
                tts_player.stop()
                led.set_state("listening")
                pending_user_text = interrupt_text
                continue
            led.set_state("listening")
            continue

            safety_level, safety_message = evaluate_safety(user_text)
            if safety_level in ("high", "moderate"):
                fast_protocol = build_fast_protocol_message()
                combined = f"{safety_message} {fast_protocol}".strip()
                led.set_state("speaking")
                audio_file = tts.synthesize_to_mp3(
                    combined,
                    voice_override=get_personality_voice(profile),
                )
                print(f"Bed: {combined}")
                print(f"Bed: Audio saved at {audio_file}")
                if audio_file:
                    tts_player.play_file(audio_file)
                interrupt_text = wake_word_manager.capture_barge_in_text()
                if interrupt_text:
                    tts_player.stop()
                    led.set_state("listening")
                    pending_user_text = interrupt_text
                    continue
                led.set_state("listening")
                continue

            quick_response, quick_handled = offline_pack.handle(user_text)
            if quick_handled:
                response_text = quick_response
                environment_orchestrator.preload_transition_for_response(led, profile, response_text)
                led.set_state("speaking")
                audio_file = play_tts_with_fast_start(
                    tts,
                    tts_player,
                    response_text,
                    voice_override=get_personality_voice(profile),
                )
                print(f"Bed: {response_text}")
                print(f"Bed: Audio saved at {audio_file}")
                interrupt_text = wake_word_manager.capture_barge_in_text()
                if interrupt_text:
                    tts_player.stop()
                    led.set_state("listening")
                    pending_user_text = interrupt_text
                    continue
                led.set_state("listening")
                continue

            personality = profile.get("preferences", {}).get("personality", "therapist")
            speed_tuning = get_turn_speed_tuning(profile, user_text)
            emotion_state = detect_emotion_state(user_text)
            chosen_personality, _, _ = adaptive_personality.choose_personality(profile, emotion_state)
            if chosen_personality in ("therapist", "coach", "guide"):
                personality = chosen_personality
            personality, _safety_reason = safety_valve.apply(
                profile,
                base_personality=personality,
                emotion_state=emotion_state,
                safety_level="none",
            )

            if personality == "coach":
                tts_voice_for_turn = settings.tts_voice_coach
            elif personality == "guide":
                tts_voice_for_turn = settings.tts_voice_guide
            else:
                tts_voice_for_turn = settings.tts_voice_therapist

            runtime_orchestrator.record_continuity_hint(profile, personality, user_text)
            runtime_orchestrator.record_emotion_state(profile, emotion_state)
            resolve_therapist_followup_if_answered(profile, user_text)
            record_therapist_concern(profile, user_text, personality)
            therapist_followup_prompt = get_due_therapist_followup(profile, personality, user_text)
            followup_active_turn = bool(therapist_followup_prompt)
            emotion_hint = emotion_response_hint(emotion_state)
            prosody_profile = emotion_tts_profile(emotion_state)
            wake_quality = runtime_orchestrator.wake_quality_state(profile)
            pacing_name, pacing_speed, pacing_line = runtime_orchestrator.determine_voice_pacing(
                emotion_state=emotion_state,
                wake_quality=wake_quality,
            )
            pace_override_for_turn = float(prosody_profile.get("pace_multiplier", 1.0) or 1.0) * float(pacing_speed)
            profile_override_for_turn = str(prosody_profile.get("profile_override", "") or "")
            runtime_orchestrator.set_last_voice_pacing(profile, pacing_name)
            if wake_quality == "fragile":
                emotion_hint = (
                    f"{emotion_hint} Wake quality looks fragile; use calmer therapeutic pacing and gentle language."
                )
            active_goals_count = len([g for g in goal_manager.list_goals(profile) if g.get("status") == "active"])
            sleep_engine.evaluate_recovery_mode(profile, active_goals_count=active_goals_count)
            recent_misses = goal_strategy.recent_miss_count(profile, days=7)
            current_streak_days = int(profile.get("progress", {}).get("current_streak_days", 0))
            sleep_engine.adjust_challenge_level(
                profile,
                recent_misses=recent_misses,
                current_streak_days=current_streak_days,
            )
            scene = environment_orchestrator.choose_scene(
                emotion_state=emotion_state,
                recovery_mode=bool(profile.get("sleep", {}).get("recovery_mode", False)),
                challenge_level=int(profile.get("sleep", {}).get("challenge_level", 1)),
                personality=personality,
            )
            scene_line = environment_orchestrator.apply_scene(led, profile, scene)
            save_profile(profile)
            normalized_user_text = normalize_for_intent(user_text)
            interim_normalized = str(interim_intent_hint.get("normalized", "")).strip()
            preparsed_control_turn = bool(
                interim_intent_hint.get("category") == "control"
                and interim_normalized
                and normalized_user_text
                and (
                    normalized_user_text in interim_normalized
                    or interim_normalized in normalized_user_text
                )
            )

            if preparsed_control_turn:
                print(f"Bed: Fast path using preparsed intent '{interim_intent_hint.get('intent', 'control')}'.")

            realtime_query = (not preparsed_control_turn) and is_realtime_query(user_text)
            realtime_context = ""
            effective_realtime_query = realtime_query and speed_tuning["allow_realtime_context"]
            if effective_realtime_query:
                led.set_state("thinking")
                realtime_context = fetch_realtime_context(
                    user_text, timeout_seconds=settings.ai_timeout_seconds
                )

            detailed_mode = (not preparsed_control_turn) and wants_detailed_answer(user_text)
            short_followup_mode = is_contextual_short_followup(user_text) or priority_followup_turn
            if detailed_mode:
                speed_tuning["max_tokens"] = max(int(speed_tuning.get("max_tokens", 120)), 220)
                speed_tuning["total_timeout"] = max(int(speed_tuning.get("total_timeout", 10)), 14)
            ultra_short_mode = len([w for w in normalized_user_text.split(" ") if w]) <= 2
            short_question_followup = normalized_user_text in {
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
            }
            short_affirmation_followup = normalized_user_text in {
                "yes",
                "yeah",
                "yep",
                "ok",
                "okay",
                "sure",
                "true",
                "right",
                "exactly",
            }
            long_prompt_mode = len((user_text or "").split()) >= 12
            if (not detailed_mode) and (not short_followup_mode):
                last_focus_user_text = user_text

            user_text_for_ai = user_text
            if priority_followup_turn and last_assistant_response:
                user_text_for_ai = (
                    f"Previous assistant reply being interrupted: {last_assistant_response}\n"
                    f"User interruption request: {user_text}\n"
                    "Treat this as a high-priority follow-up. Stop prior topic expansion and answer this interruption directly first. "
                    "If it is a control/action request, keep the reply short and actionable."
                )
            elif detailed_mode and len((user_text or "").split()) <= 5 and last_focus_user_text:
                user_text_for_ai = (
                    f"Topic from previous user turn: {last_focus_user_text}\n"
                    f"User follow-up: {user_text}\n"
                    "Expand on the same topic with practical detail."
                )
            elif short_followup_mode and short_affirmation_followup and last_assistant_response.strip().endswith("?"):
                user_text_for_ai = (
                    f"Previous assistant question: {last_assistant_response}\n"
                    f"User affirmation: {user_text}\n"
                    "Continue naturally in the same context. "
                    "Acknowledge briefly and ask one specific follow-up tied to that same question. "
                    "Do not switch topics. Keep it short and human."
                )
            elif short_followup_mode and short_question_followup and last_assistant_response:
                user_text_for_ai = (
                    f"Previous assistant reply: {last_assistant_response}\n"
                    f"User short follow-up question: {user_text}\n"
                    "Answer directly and continue the same context in one concise line. "
                    "If the previous reply was a joke setup question, provide the punchline. "
                    "Do not switch topics and do not ask a new follow-up question."
                )
            elif short_followup_mode and last_focus_user_text:
                user_text_for_ai = (
                    f"Topic from previous user turn: {last_focus_user_text}\n"
                    f"User acknowledgement/follow-up: {user_text}\n"
                    "Reply on the same topic in 1 concise practical line. Do not ask a new follow-up question."
                )

            if followup_active_turn:
                user_text_for_ai = (
                    f"Start with this caring check-in first: {therapist_followup_prompt}\n"
                    f"Then answer the user's current message: {user_text}\n"
                    "Be warm, genuine, and concise. Do not sound scripted."
                )

            response_audio_already_played = False
            stream_interrupt_text = ""
            cached = None if (effective_realtime_query or detailed_mode or short_followup_mode or ultra_short_mode or long_prompt_mode or followup_active_turn) else cache.get(user_text, personality)

            if cached is not None:
                response_style = str(
                    profile.get("preferences", {}).get("response_style", "quick") or "quick"
                ).strip().lower()
                response_text = clamp_non_detail_response(
                    cached,
                    detailed_mode=detailed_mode,
                    response_style=response_style,
                )
                print("Bed: (cache hit)")
            else:
                ack_mode = str(profile.get("preferences", {}).get("thinking_ack_mode", "minimal") or "minimal").lower().strip()
                if ack_mode in ("off", "mute", "disabled"):
                    should_play_ack = False
                elif ack_mode in ("always", "on"):
                    should_play_ack = effective_realtime_query or detailed_mode or long_prompt_mode
                else:
                    should_play_ack = effective_realtime_query or detailed_mode
                if should_play_ack and tts_player.is_ready():
                    ack_text = build_transition_ack(profile, runtime_orchestrator)
                    ack_audio_file = tts.synthesize_to_mp3(
                        ack_text,
                        filename="ack_quick.mp3",
                        voice_override=tts_voice_for_turn,
                    )
                    if ack_audio_file:
                        tts_player.play_file(ack_audio_file)

                memory_context_line = memory_store.memory_prompt_line(user_text)
                user_context = build_user_context(
                    profile,
                    goals_context=goal_manager.context_summary(profile),
                    compass_context=goal_compass.summary_line(
                        profile,
                        [g for g in goal_manager.list_goals(profile) if g.get("status") == "active"],
                    ),
                    progress_context=build_progress_summary(profile),
                    emotion_context=emotion_hint,
                    sleep_context=sleep_engine.summary_line(profile),
                    runtime_context=runtime_orchestrator.emotion_trend_summary(profile),
                    goal_strategy_context=(
                        goal_strategy.context_summary(profile)
                        + " "
                        + goal_strategy.blocker_coaching_line(profile)
                        + " "
                        + pacing_line
                    ).strip(),
                    environment_context=scene_line,
                    daily_life_context=str(profile.get("daily_life", {}).get("last_coaching_tone", "")),
                    detailed_mode=detailed_mode,
                )
                if memory_context_line:
                    user_context = (user_context + "\n" + memory_context_line).strip()
                daily_events_line = memory_store.latest_daily_events_summary(hours=36, max_items=3)
                if daily_events_line:
                    user_context = (user_context + "\n" + daily_events_line).strip()
                gpt_diag = _build_gpt_route_diagnostics(backend_client)
                if not effective_realtime_query:
                    led.set_state("thinking")
                print(f"[FLOW] STT captured chars={len(user_text)}")
                print("[FLOW] Open-question route -> GPT completion")

                response_text = ""
                if gpt_diag["openai_ready"]:
                    print(f"[FLOW] GPT provider: direct OpenAI API (model={settings.openai_chat_model}).")
                    ok_openai, openai_text = _request_openai_chat_reply(
                        user_text_for_ai=user_text_for_ai,
                        personality=personality,
                        user_context=user_context,
                        realtime_context=realtime_context,
                        max_response_tokens=speed_tuning["max_tokens"],
                    )
                    if ok_openai:
                        response_text = str(openai_text or "").strip()
                        print(f"[FLOW] GPT reply text chars={len(response_text)}")
                    else:
                        print(f"[FLOW][WARN] Direct OpenAI GPT failed: {openai_text}")

                if (not response_text) and gpt_diag["backend_ready"] and (backend_client is not None):
                    ent_ok, _ = backend_client.fetch_entitlement()
                    if (not ent_ok) or (not backend_client.is_feature_allowed("cloud_chat")):
                        print("[FLOW][WARN] Backend GPT route unavailable: cloud_chat entitlement is inactive.")
                    else:
                        print("[FLOW] GPT provider: backend cloud_chat proxy.")
                        ok_cloud, cloud_text, _ = backend_client.request_ai_chat(
                            text=user_text_for_ai,
                            personality=personality,
                            user_context=user_context,
                            realtime_context=realtime_context,
                            max_response_tokens=speed_tuning["max_tokens"],
                        )
                        if ok_cloud:
                            response_text = str(cloud_text or "").strip()
                            print(f"[FLOW] GPT reply text chars={len(response_text)}")
                        else:
                            print(f"[FLOW][WARN] Backend GPT request failed: {cloud_text}")
                            offline_response, handled_offline = offline_pack.handle(user_text)
                            response_text = offline_response if handled_offline else str(cloud_text or "").strip()

                if not response_text:
                    offline_response, handled_offline = offline_pack.handle(user_text)
                    if handled_offline:
                        response_text = offline_response
                    else:
                        missing = " | ".join(gpt_diag["issues"]) if gpt_diag["issues"] else "no GPT route is currently available"
                        response_text = (
                            "GPT route is unavailable right now. "
                            f"{missing}"
                        )
                    print(f"[FLOW][WARN] GPT route unavailable. {response_text}")

                if stream_interrupt_text:
                    runtime_orchestrator.record_interrupt(profile)
                    save_profile(profile)
                    pending_user_text = stream_interrupt_text
                    led.set_state("listening")
                    continue

                quality_tag = ""
                if not response_audio_already_played:
                    tts_player.stop()

                    response_text, quality_tag = runtime_orchestrator.enforce_conversation_quality(
                        profile,
                        response_text=response_text,
                        personality=personality,
                        emotion_state=emotion_state,
                    )
                    response_style = str(
                        profile.get("preferences", {}).get("response_style", "quick") or "quick"
                    ).strip().lower()
                    response_text = clamp_non_detail_response(
                        response_text,
                        detailed_mode=detailed_mode,
                        response_style=response_style,
                    )
                    response_text, brevity_tag = runtime_orchestrator.apply_cognitive_brevity(
                        profile,
                        response_text=response_text,
                        emotion_state=emotion_state,
                    )
                    if brevity_tag:
                        quality_tag = brevity_tag
                    if followup_active_turn and therapist_followup_prompt.lower() not in response_text.lower():
                        response_text = f"{therapist_followup_prompt} {response_text}".strip()
                    if quality_tag:
                        save_profile(profile)

                adaptive_personality.record_interaction(
                    profile,
                    personality=personality,
                    emotion_state=emotion_state,
                    user_text=user_text,
                    score=0.8 if not quality_tag else 0.6,
                )
                save_profile(profile)

                if (
                    (not effective_realtime_query)
                    and (not detailed_mode)
                    and (not short_followup_mode)
                    and (not ultra_short_mode)
                    and (not long_prompt_mode)
                    and (not followup_active_turn)
                    and (not _is_llm_fallback_response(response_text))
                ):
                    cache.set(user_text, response_text, personality)

            memory_store.record_turn(
                user_text=user_text,
                assistant_text=response_text,
                emotion_state=emotion_state,
                personality=personality,
            )
            last_assistant_response = response_text

            led.set_state("speaking")
            response_lower = response_text.lower()
            profile.setdefault("runtime_flags", {})["breathing_offer_active"] = (
                ("4-7-8" in response_lower)
                or ("inhale for 4" in response_lower)
                or ("breathing" in response_lower and "inhale" in response_lower and "exhale" in response_lower)
            )
            save_profile(profile)
            if response_audio_already_played:
                print(f"Bed: {response_text}")
                if tts_player.is_playing():
                    print("Bed: Streaming response audio now.")
            else:
                environment_orchestrator.preload_transition_for_response(led, profile, response_text)
                print("[FLOW] Routing GPT reply -> TTS -> pygame playback")
                audio_file = play_tts_with_fast_start(
                    tts,
                    tts_player,
                    response_text,
                    voice_override=tts_voice_for_turn,
                    pace_override=pace_override_for_turn,
                    emotion_state=emotion_state,
                    profile_override=profile_override_for_turn,
                )
                print(f"Bed: {response_text}")
                print(f"Bed: Audio saved at {audio_file}")
                if tts_player.is_playing():
                    print("Bed: Playing response audio now.")

                interrupt_text = wake_word_manager.capture_barge_in_text()
                if interrupt_text:
                    runtime_orchestrator.record_interrupt(profile)
                    save_profile(profile)
                    tts_player.stop()
                    led.set_state("listening")
                    pending_user_text = interrupt_text
                    continue

            led.set_state("listening")

