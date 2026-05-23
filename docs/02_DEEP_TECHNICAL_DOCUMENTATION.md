# Smart Bed AI — Deep Technical Documentation (Part 1)

> Every module explained in simple English. See Part 2 for remaining sections.

---

## 1. How the System Starts

Two programs run together:

**Program 1 — Voice Runtime** (`main.py` → `app_entry.py`):
1. Logging starts (loguru JSON logs)
2. All 54 AI modules load
3. Automation engine starts (bedtime, prayer reminders)
4. Sensor polling begins (pressure, temp, heart rate)
5. Wake word listener starts ("Hey Smart Bed")
6. Main loop: wake word → listen → STT → intent → AI → TTS → speak → repeat

**Program 2 — Web API** (`api/app_factory.py`):
1. FastAPI app created with CORS
2. Database pools initialized (sync psycopg2 + async asyncpg)
3. pgvector memory index created
4. arq job queue connects to Redis
5. Firebase FCM initialized
6. 17 API routers mounted
7. Server listens on port 8000

Both programs share the same PostgreSQL database and sync via Redis pub/sub.

---

## 2. Configuration (`config/settings.py` — 495 lines)

All settings loaded from `.env` via Pydantic Settings. Key categories:

| Category | Examples |
|---|---|
| Security | `SECRET_KEY`, JWT algorithm/expiry |
| Deepgram | API key, STT model (nova-2), TTS voices (3 personas) |
| Wake Word | Mode (keyboard/voice), phrase, timeouts |
| Sensors | GPIO pins, poll intervals, enable flags |
| LED | Pins (18, 13), LED counts (120, 60), brightness |
| Spotify | Client ID/secret, scopes, redirect URI |
| PayPal | Client ID/secret, plan IDs |
| Database | Pool size (10), overflow (20), async min/max |
| Islamic | City, country, prayer method (8 = Kuwait) |
| AI | Claude (primary), GPT (fallback), model names |

**Safety:** Rejects weak SECRET_KEY in production. Validates sensitive file paths. Warns on missing API keys at startup.

---

## 3. AI Engine — All 54 Modules

### Conversation & Language

**conversation_engine.py (39.5KB)** — The brain. Sends user text to Claude AI, gets response. Token budget 160K, auto-trims history. Retry 3x with backoff. Falls back to LiteLLM → OpenAI if Claude fails. Streaming word-by-word responses.

**structured_extraction.py (14.6KB)** — Extracts structured data from AI responses using Instructor + Pydantic. Converts "set alarm for 7 AM" into `{time: "07:00"}`.

**conversational_fillers.py (1.2KB)** — Plays "Hmm...", "Let me think..." while AI processes. Makes conversation feel natural.

**offline_intent_pack.py (2KB)** — Handles basic commands offline: "what time is it", "turn off lights". No cloud needed.

### Voice Pipeline

**stt_manager.py (35.2KB)** — Ears. Deepgram Nova-2 (cloud) + faster-whisper (local fallback). Noise reduction + loudness normalization before transcription. Returns text + confidence score (0-1). Below 0.50 = "please repeat", 0.50-0.58 = confirmation.

**tts_manager.py (14.3KB)** — Mouth. Deepgram Aura-2 with 3 voices: Guide (asteria), Coach (orion), Therapist (thalia). Speed/pitch adjusted by emotion. Streaming playback.

**wake_word_manager.py (10.8KB)** — Listens for "Hey Smart Bed". Keyboard mode for PC, voice mode for Pi. Local-only detection (privacy-first).

**vad_filter.py (6.1KB)** — WebRTC Voice Activity Detection. Filters silence before STT. Saves API costs.

**voice_circuit_breaker.py (9KB)** — If voice pipeline fails 3x, stops trying. Backs off: 3s → 6s → 12s → max 60s. Prevents flooding APIs during outages.

**acoustic_echo_guard.py (718B)** — Prevents mic from hearing speaker output. Confidence threshold 0.72 during TTS playback.

**barge_in_monitor.py (1.3KB)** — Detects user interruption during TTS. Stops playback, starts listening immediately.

**realtime_voice_pipeline.py (5.3KB)** — Coordinates full pipeline: mic → VAD → STT → AI → TTS → speaker. State machine: idle → listening → processing → speaking.

**audio_output_manager.py (5.7KB)** — Audio playback queue. Priority system (emergency > TTS > music). Volume management.

**audio_playback_controller.py (3.8KB)** — Low-level speaker control. Play, pause, stop, volume.

**speaker_diarization.py (9.9KB)** — Identifies WHO is speaking using pyannote.audio. Distinguishes Partner 1 from Partner 2. Routes commands to correct profile.

**local_wake_word.py (3KB)** — On-device wake word detection. No audio sent to cloud for wake word.

### Emotion & Personality

**emotion_router.py (8.5KB)** — Detects emotion from text: neutral, happy, stressed, anxious, sad, angry, tired. Adjusts AI prompt, TTS voice, and may trigger personality switch.

**adaptive_personality_engine.py (4.4KB)** — Decides which personality to use. Stressed → Therapist. Goals → Coach. Default → Guide.

**personality_runtime.py (18.8KB)** — Orchestrates smooth personality transitions. Manages greetings, tracks user preference.

**personality_evolution.py (14.2KB)** — Learns personality preference over time. Longer conversations = user likes this mode. Adjusts defaults.

### Memory & Context

**long_term_memory.py (21.8KB)** — Remembers past conversations. Stores in PostgreSQL + pgvector. Each turn vectorized via sentence-transformers. Cosine similarity search finds relevant past talks. Enables "Last week you mentioned your exam."

**pgvector_memory_index.py (8.1KB)** — PostgreSQL vector similarity search. Primary memory store.

**chroma_memory_index.py (4.5KB)** — ChromaDB fallback when PostgreSQL unavailable.

**embedding_service.py (1.6KB)** — Generates vector embeddings from text using sentence-transformers.

**daily_life_support.py (7KB)** — Injects real-life events ("stressful meeting", "exercised 30 min") into AI context.

### Sleep Intelligence

**sleep_intelligence.py (28.7KB)** — Core engine. Tracks bedtime/wake history, sleep duration, bedtime drift (>30min variance alert), recovery mode, challenge levels 1-5, partner mode, wind-down tracking.

### Safety

**safety_guardrails.py (1.3KB)** — Content filtering. Blocks dangerous topics.

**safety_valve.py (1.6KB)** — Emergency output shutdown. Last line of defense.

**crisis_protocol.py (4KB)** — Detects severe distress. Provides emergency contacts. Does NOT try to "be a therapist" for real crises.

**response_quality_gate.py (3.4KB)** — Validates AI responses before delivery. Checks for hallucinations, relevance, length.

### Actions & Intent

**action_resolver.py (5.4KB)** — Maps intent to action. "turn lights blue" → LED controller call.

**intent_classifier.py (4.4KB)** — Classifies: is this a LED command? A personality switch? A system command?

**activity_predictor.py (10.2KB)** — Predicts user behavior patterns. "User always plays Spotify at 10 PM."

### Goals & Routines

**goal_compass.py (1.3KB)** — Tracks user goals. "Sleep before 11 PM every night."

**goal_strategy_engine.py (8.1KB)** — Breaks goals into steps. "Improve sleep" → "consistent bedtime + wind-down + reduce screen time."

**session_goal_manager.py (4.9KB)** — Tracks what user wants to accomplish in THIS conversation.

**routine_engine.py (4.1KB)** — Manages daily routines. Triggers automations at routine times.

**sleep_routine_manager.py (1.4KB)** — Orchestrates bedtime/wake sequences.

### Environment & Health

**sensor_bridge.py (9.3KB)** — Unified sensor interface. Polls all sensors, normalizes data, publishes via Redis.

**environment_orchestrator.py (5.4KB)** — Combines sensors + scenes + LED into unified state.

**device_health.py (3.8KB)** — Checks all hardware health. Powers `/healthz/detailed`.

**realtime_info.py (4KB)** — Fetches live weather, time for AI context.

### Special Features

**breathing_guide_engine.py (5.9KB)** — 4-7-8 breathing: inhale 4s, hold 7s, exhale 8s. LED syncs. Voice prompts.

**dream_journal_manager.py (5.3KB)** — Records dreams via voice.

**dream_journal_enhanced.py (11.5KB)** — ML dream analysis. Detects emotional themes, recurring patterns.

**spotify_manager.py (5KB)** — Spotify playback via OAuth. Play, pause, skip.

**local_music_manager.py (4.5KB)** — Offline music from `local_music/` folder.

**signature_experiences.py (3.2KB)** — Special moments: first-time greeting, milestones.

**reflection.py (3.2KB)** — End-of-day prompts: "What are you grateful for?"

**proactive_automation_engine.py (7.5KB)** — Anticipates needs. "You usually lower lights now. Should I?"

**automation_learning_engine.py (13KB)** — Learns automation preferences from behavior.

**online_calendar.py (18.2KB)** — Google Calendar integration for schedule context.

**bed_backend_client.py (7KB)** — HTTP client for bed device communication.

---

## 4. Dana Personality System (`dana/`)

### Three Personalities

**Guide** (`guide.py`): Calm, spiritual, peaceful. Color: purple (#7B68EE). Says Islamic good night dua. Gratitude prompts. Wind-down guidance.

**Coach** (`coach.py`): Motivational, energetic. Color: orange (#FF6B35). Streak tracking ("7-night streak!"). Score commentary ("PERFECT score!"). Performance reports.

**Therapist** (`therapist.py`): Empathetic, supportive. Color: cyan (#00D4FF). Stress check-ins (1-10). Pattern detection. Affirmations. Follow-up on bad nights.

### Configuration (`personality.py`)
Each personality has: name, tagline, tone, emoji, greeting, sleep message, wake message, color hex. Stored as frozen dataclass.

---

## 5. Sleep System — Complete

### Core (`ai/sleep_intelligence.py` — 28.7KB)
Tracks: bedtime_history[], wake_history[], recovery_mode, challenge_level (1-5), night_wake_count, partner_mode. Bedtime drift alert at >30min variance.

### Tracking Modules (`sleep_tracking/`)

| Module | What It Does |
|---|---|
| `sleep_analyzer.py` (35.9KB) | Sleep stages from movement, efficiency, anomaly detection (scikit-learn), pattern clustering |
| `wake_optimizer.py` (20.6KB) | Calculates best wake time using 90-min sleep cycles. Smart window up to 30 min early |
| `sleep_debt_tracker.py` (13.2KB) | Cumulative debt = target - actual. Recovery plan: "add 30 min for 12 nights" |
| `nap_optimizer.py` (13.1KB) | Should you nap? How long? No naps after 3 PM. Power (20 min) or full cycle (90 min) |
| `weekly_report.py` (6.5KB) | Weekly summary: avg duration, best/worst night, consistency, debt trend |
| `sleep_score.py` (2.3KB) | 0-100 score from: duration, consistency, night wakes, restlessness, efficiency |
| `sleep_session.py` (3.3KB) | Sleep session data model |

### Wind-Down (`winddown/`)
- `winddown_session.py` (4.1KB) — 30-60 min pre-sleep routine
- `breathing_exercise.py` (2KB) — Guided breathing patterns
- `led_scenes.py` (1.8KB) — Gradual dimming sequences
- `winddown_api.py` (2.7KB) — REST endpoints

---

## 6. Hardware & Sensors

| Sensor | File | Connection | Data |
|---|---|---|---|
| AM2301A/DHT22 | `pi_temperature.py` (8.5KB) | GPIO pin 4 | Temp °C, Humidity % |
| MAX30102 | `pi_heart_rate.py` (7.8KB) | I2C | Heart rate BPM, SpO2 % |
| Pressure pad | `pi_sensors.py` (7.9KB) | GPIO | Bed occupancy, movement |
| Motion sensor | `pi_sensors.py` | GPIO | Movement detection |

**Pressure Intelligence** (`pressure_intelligence.py`, 14.4KB): Restlessness scoring, position tracking, bed entry/exit, guest detection.

**LED** (`pi_led.py`, 10.8KB): WS2812B NeoPixel. Pins 18+13. 120+60 LEDs. DMA for smooth animation. 20 FPS. Max brightness 255.

---

## 7. Scenes

| Module | Function |
|---|---|
| `circadian_engine.py` (14.8KB) | Auto color temp: 6500K morning → 2700K night |
| `weather_adaptive.py` (14KB) | Warmer on cold days, cooler on hot days |
| `default_scenes.py` (2.5KB) | Presets: deep sleep, reading, romance, Fajr |
| `scene_store.py` (5.7KB) | Scene CRUD, premium flag, usage tracking |

---

*Continued in `02_DEEP_TECHNICAL_DOCUMENTATION_PART2.md`*
