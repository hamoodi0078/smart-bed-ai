# Danah Smart Bed AI — Project Manual

> **Version**: 2.0.0
> **Last Updated**: 2025
> **Audience**: Developers who need to run, debug, and extend this project.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Directory Structure](#3-directory-structure)
4. [Technology Stack & Libraries](#4-technology-stack--libraries)
5. [Environment Setup](#5-environment-setup)
6. [Running the Project](#6-running-the-project)
7. [Configuration Reference](#7-configuration-reference)
8. [Database Layer](#8-database-layer)
9. [API Layer](#9-api-layer)
10. [Voice Runtime (app_entry.py)](#10-voice-runtime-app_entrypy)
11. [AI Modules](#11-ai-modules)
12. [Dana Voice Assistant](#12-dana-voice-assistant)
13. [Islamic Mode](#13-islamic-mode)
14. [Sleep Intelligence](#14-sleep-intelligence)
15. [LED & Scene System](#15-led--scene-system)
16. [Automation Engine](#16-automation-engine)
17. [Hardware & Sensors](#17-hardware--sensors)
18. [Integrations](#18-integrations)
19. [Notifications](#19-notifications)
20. [Subscriptions & Billing](#20-subscriptions--billing)
21. [Gamification](#21-gamification)
22. [Guest Mode](#22-guest-mode)
23. [Partner Sleep Mode](#23-partner-sleep-mode)
24. [QR Code & Device Pairing](#24-qr-code--device-pairing)
25. [Mobile App (Flutter)](#25-mobile-app-flutter)
26. [Web Admin Panel](#26-web-admin-panel)
27. [Authentication & Security](#27-authentication--security)
28. [Testing](#28-testing)
29. [Docker & Deployment](#29-docker--deployment)
30. [CI/CD Pipeline](#30-cicd-pipeline)
31. [Voice Commands Reference](#31-voice-commands-reference)
32. [API Endpoints Reference](#32-api-endpoints-reference)
33. [Troubleshooting](#33-troubleshooting)

---

## 1. System Overview

Danah Smart Bed AI is an AI-powered smart bed system that combines:
- **Voice assistant ("Dana")** with 3 personality modes (Coach, Guide, Therapist)
- **Sleep science intelligence** — tracking, scoring, recovery, consistency analysis
- **Islamic features** — prayer times, Quran recitation, Fajr gentle wake, hadith
- **LED lighting control** — WS2812 strips with animations, scenes, music-reactive modes
- **Hardware sensors** — dual-zone pressure pads, motion detection, occupancy tracking
- **Smart home integrations** — Philips Hue, TP-Link Kasa, Tuya, Zigbee, MQTT
- **Mobile app** (Flutter) for iOS/Android control
- **Web admin panel** for device management and analytics
- **Subscription billing** via PayPal
- **Gamification** with achievements, badges, and level progression

The system runs on a Raspberry Pi (production) or any Python 3.11+ machine (development).

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Mobile App (Flutter)                       │
│         iOS / Android — Riverpod state management            │
└─────────────────┬───────────────────────────────────────────┘
                  │ HTTPS / REST
┌─────────────────▼───────────────────────────────────────────┐
│              FastAPI Backend (api/app_factory.py)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Auth     │ │ Alarms   │ │ Scenes   │ │ Islamic       │  │
│  │ Router   │ │ Router   │ │ Router   │ │ Router        │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Sleep    │ │ Profile  │ │ Health   │ │ Metrics       │  │
│  │ Router   │ │ Router   │ │ Router   │ │ (Prometheus)  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │          web_server.py (legacy catch-all routes)       │ │
│  │  Mobile API, Spotify, Billing, Scenes, Chat, Admin    │ │
│  └────────────────────────────────────────────────────────┘ │
│  Middleware: CORS, Rate Limiting, Error Handler, Metrics     │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│           Voice Runtime (app_entry.py)                        │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────────────┐ │
│  │ STT    │ │ TTS    │ │ Wake   │ │ Conversation Engine  │ │
│  │Manager │ │Manager │ │ Word   │ │ (OpenAI / Claude)    │ │
│  └────────┘ └────────┘ └────────┘ └──────────────────────┘ │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────────────┐ │
│  │Emotion │ │Safety  │ │Memory  │ │ Personality Runtime   │ │
│  │Router  │ │Guards  │ │Store   │ │ Orchestrator          │ │
│  └────────┘ └────────┘ └────────┘ └──────────────────────┘ │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│              Data & Hardware Layer                            │
│  ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │PostgreSQL │ │ Redis    │ │ LED      │ │ Pressure     │  │
│  │+ SQLite   │ │ (cache/  │ │ WS2812   │ │ Sensors      │  │
│  │           │ │  queues) │ │ Strips   │ │              │  │
│  └───────────┘ └──────────┘ └──────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Directory Structure

```
smart bed by me/
├── ai/                     # 50+ AI modules (STT, TTS, emotion, intent, memory, etc.)
├── alembic/                # Database migration scripts
├── api/                    # FastAPI app factory, routers, middleware
│   ├── middleware/          # Rate limiter, error handler, tracing
│   ├── models/              # Pydantic response models
│   └── routers/             # Modular API route files
├── auth/                   # JWT signing/verification (authlib)
├── automations/            # Automation registry, defaults, triggers
├── commands/               # Voice command handlers (lights, sleep, reminders)
├── config/                 # Settings (Pydantic BaseSettings from .env)
├── constants/              # Limits, scenes, voice constants
├── core/                   # Shared utilities (logging, errors, types, arabic)
├── dana/                   # Dana personality system (Coach/Guide/Therapist)
├── data/                   # Local data files (SQLite DB, JSON stores)
├── database/               # SQLAlchemy models, connection, repositories
├── docs/                   # ADRs, improvement plans, feature docs
├── gamification/           # Achievement engine with milestone tracking
├── guest_mode/             # Guest mode activation/deactivation
├── hardware/               # Raspberry Pi GPIO, LED, pressure sensors
├── health/                 # Hydration tracker, stress detector, weekly reports
├── integrations/           # Fitbit, Garmin, Google Calendar, smart home, MQTT, Zigbee
├── islamic_mode/           # Prayer times, Quran, hadith, Islamic voice
├── led/                    # LED controller abstraction
├── local_music/            # Local MP3 files for offline playback
├── mobile_app/             # Flutter mobile application
│   ├── lib/                 # Dart source (screens, services, state)
│   ├── android/             # Android build config
│   └── ios/                 # iOS build config
├── notifications/          # Email (SendGrid/SES), FCM, Expo, WhatsApp, summaries
├── partner/                # Partner compromise engine, staggered wake
├── qr_code/                # QR generation and device pairing
├── reports/                # PDF/HTML report generation, chart rendering
├── scenes/                 # Scene store, circadian engine, default scenes
├── scripts/                # Startup scripts, systemd services, smoke tests
├── sleep_tracking/         # Sleep analyzer, nap optimizer, sleep API
├── spotify/                # Spotify client, prayer pause, sleep playlists
├── Storage/                # Cache manager, schedule manager, user profile I/O
├── subscriptions/          # Billing service, PayPal provider, subscription gate
├── tasks/                  # ARQ (async job queue) workers and task definitions
├── tests/                  # 86+ test files
├── utils/                  # General utilities
├── web/                    # Static HTML/CSS/JS for admin panel
├── winddown/               # Wind-down breathing exercises, LED scenes
│
├── main.py                 # Thin launcher → app_entry.main()
├── app_entry.py            # Voice runtime main loop (~1800 lines)
├── voice_handler.py        # Voice turn processing, intent handling (~4200 lines)
├── web_server.py           # Legacy FastAPI app (~10000 lines)
├── master_controller.py    # High-level coordinator (Dana, prayer, Spotify, guest)
├── master_api.py           # Master FastAPI app with routers
├── automation_engine.py    # Automation runtime (reminders, triggers, scheduling)
├── led_controller.py       # LED helper functions (color parsing, hardware config)
├── prayer_handler.py       # Prayer support helpers
├── scene_manager.py        # Scene payload creation and clarification
├── time_utils.py           # UTC time utilities
├── init_db.py              # Database initialization script
│
├── .env.example            # Environment variable template (347 variables)
├── requirements.txt        # Python dependencies (~100 packages)
├── requirements-dev.txt    # Dev/test dependencies
├── pyproject.toml          # pytest, coverage, mypy configuration
├── Dockerfile              # Python 3.11-slim production image
├── docker-compose.yml      # 5-service stack (api, voice, worker, redis, db)
├── ruff.toml               # Linter/formatter configuration
├── bandit.yml              # Security scanner configuration
└── .github/workflows/ci.yml # CI pipeline
```

---

## 4. Technology Stack & Libraries

### Backend Core
| Library | Version | Purpose |
|---------|---------|---------|
| **FastAPI** | latest | Web framework for REST API |
| **Uvicorn** | latest | ASGI server |
| **Gunicorn** | latest | Production process manager |
| **Pydantic** | v2 | Data validation, settings management |
| **pydantic-settings** | latest | Environment-based configuration |
| **SQLAlchemy** | latest | ORM for database models |
| **asyncpg** | latest | Async PostgreSQL driver |
| **psycopg2-binary** | latest | Sync PostgreSQL driver |
| **Alembic** | latest | Database migrations |
| **Redis** | latest | Caching, job queues |
| **ARQ** | latest | Async job queue (replaces Celery) |

### Voice & AI
| Library | Purpose |
|---------|---------|
| **deepgram-sdk** | Speech-to-text (Nova-2) and text-to-speech (Aura-2) |
| **faster-whisper** | Local STT fallback (CTranslate2 Whisper) |
| **speech_recognition** | Microphone capture abstraction |
| **PyAudio / sounddevice** | Audio I/O |
| **noisereduce** | Spectral-gate noise reduction for STT input |
| **pyloudnorm** | EBU R128 loudness normalization |
| **pyannote.audio** | Speaker diarization (optional) |
| **transformers** | Emotion classification (distilroberta) |
| **OpenAI API** | GPT chat completion (direct HTTP) |
| **Anthropic Claude** | Alternative AI chat provider |
| **litellm** | Universal LLM router |
| **chromadb** | Vector memory store |

### Integrations
| Library | Purpose |
|---------|---------|
| **spotipy** | Spotify Web API client |
| **phue** | Philips Hue bridge control |
| **python-kasa** | TP-Link Kasa smart devices |
| **python-miio** | Xiaomi Mi smart devices |
| **tuyapy / tuya-connector** | Tuya cloud smart devices |
| **pyatv** | Apple TV control |
| **pychromecast** | Chromecast control |
| **paho-mqtt** | MQTT messaging for IoT |
| **zigpy** | Zigbee protocol coordinator |
| **garminconnect** | Garmin health data |
| **fitbit** | Fitbit health data |
| **google-api-python-client** | Google Calendar sync |

### Notifications
| Library | Purpose |
|---------|---------|
| **sendgrid** | Transactional email |
| **boto3** | AWS SES email + S3 storage |
| **firebase-admin** | FCM push notifications |
| **twilio** | SMS OTP delivery |

### Security & Auth
| Library | Purpose |
|---------|---------|
| **authlib** | JWT signing/verification (HS256) |
| **bcrypt** | Password hashing |

### Monitoring & Quality
| Library | Purpose |
|---------|---------|
| **prometheus-client** | Metrics collection |
| **sentry-sdk** | Error tracking + performance monitoring |
| **opentelemetry** | Distributed tracing (optional) |
| **loguru** | Structured logging |
| **ruff** | Linter + formatter |
| **bandit** | Security scanner |
| **mypy** | Type checker |
| **pytest** | Test framework |

### Mobile App (Flutter)
| Package | Purpose |
|---------|---------|
| **flutter_riverpod** | State management |
| **sentry_flutter** | Crash reporting |
| **flutter_localizations** | l10n (Arabic/English) |

---

## 5. Environment Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 16 (or SQLite for local dev)
- Redis 7+
- Node.js (for Flutter web, optional)
- Flutter 3.x (for mobile app)
- PortAudio system library (for PyAudio/sounddevice)

### Step-by-Step

```bash
# 1. Clone the repository
git clone <repo_url>
cd "smart bed by me"

# 2. Create Python virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
# For development/testing:
pip install -r requirements-dev.txt

# 4. Copy and configure environment
copy .env.example .env    # Windows
# cp .env.example .env    # Linux/Mac
# Edit .env with your API keys (see Section 7)

# 5. Create runtime directories
mkdir runtime_data output_audio local_music

# 6. Initialize database
python init_db.py
# Or with Alembic:
alembic upgrade head

# 7. Start the API server
uvicorn api.app_factory:app --reload --host 0.0.0.0 --port 8000

# 8. Start the voice runtime (separate terminal)
python app_entry.py

# 9. (Optional) Start the ARQ worker
arq tasks.arq_app.WorkerSettings
```

### Docker Quick Start

```bash
# Set required secrets in .env first, then:
docker compose up --build

# Services exposed:
# - API:      http://localhost:8000
# - Redis:    localhost:6379
# - Postgres: localhost:5432
```

---

## 6. Running the Project

### Entry Points

| Command | What It Does |
|---------|-------------|
| `uvicorn api.app_factory:app --reload` | Starts the FastAPI backend (new app factory) |
| `python app_entry.py` | Starts the voice runtime loop (STT/TTS/wake word) |
| `python main.py` | Thin launcher that calls `app_entry.main()` |
| `arq tasks.arq_app.WorkerSettings` | Starts the async job worker |
| `python web_server.py` | Legacy standalone API (avoid — use app_factory instead) |
| `docker compose up` | Starts entire stack (api + voice + worker + redis + db) |

### Development Workflow

1. **Backend changes**: Edit code → Uvicorn auto-reloads
2. **Voice changes**: Edit code → Restart `app_entry.py` manually
3. **Database changes**: Create migration with `alembic revision --autogenerate -m "description"` → Apply with `alembic upgrade head`
4. **Run tests**: `pytest tests/ -q --tb=short`
5. **Lint**: `ruff check .` and `ruff format --check .`

---

## 7. Configuration Reference

All configuration is loaded from `.env` via Pydantic `BaseSettings` in `config/settings.py`.

### Critical Variables (must be set for full functionality)

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql://user:pass@localhost:5432/danah` |
| `SECRET_KEY` | JWT signing key (32+ chars in prod) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DEEPGRAM_API_KEY` | STT + TTS voice services | From console.deepgram.com |
| `DEEPGRAM_TTS_API_KEY` | TTS (falls back to DEEPGRAM_API_KEY) | Same or separate key |
| `OPENAI_API_KEY` | GPT chat (if USE_OPENAI_DIRECT=1) | From platform.openai.com |
| `ANTHROPIC_API_KEY` | Claude chat (alternative) | From console.anthropic.com |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |

### Voice Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WAKE_WORD_MODE` | `keyboard` | `keyboard` (type to wake) or `voice` (microphone) |
| `WAKE_WORD_PHRASE` | `hey smart bed` | Wake phrase the system listens for |
| `STT_MODE` | `api` | `api` (Deepgram cloud), `local` (Whisper), or `hybrid` |
| `DEEPGRAM_STT_MODEL` | `nova-2` | STT model name |
| `DEEPGRAM_TTS_MODEL` | `aura-2-thalia-en` | TTS voice model |
| `DEEPGRAM_TTS_VOICE_THERAPIST` | `aura-2-thalia-en` | Voice for Therapist personality |
| `DEEPGRAM_TTS_VOICE_COACH` | `aura-2-orion-en` | Voice for Coach personality |
| `DEEPGRAM_TTS_VOICE_GUIDE` | `aura-2-asteria-en` | Voice for Guide personality |
| `SMART_BED_LANGUAGE` | `auto` | Language hint: `auto`, `en`, `ar` |

### Islamic Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `ISLAMIC_PRAYER_CITY` | `Kuwait City` | City for prayer time calculation |
| `ISLAMIC_PRAYER_COUNTRY` | `Kuwait` | Country |
| `ISLAMIC_PRAYER_METHOD` | `8` | Aladhan calculation method (8=Kuwait) |
| `ISLAMIC_PRAYER_AUTO_LOCATION` | `0` | Auto-detect location from IP |

### LED Hardware (Raspberry Pi)

| Variable | Default | Description |
|----------|---------|-------------|
| `LED_HARDWARE_ENABLED` | `0` | Enable real WS2812 hardware (set 1 on Pi) |
| `USER_STRIP_PIN` | `18` | GPIO pin for user LED strip |
| `STATE_STRIP_PIN` | `13` | GPIO pin for state LED strip |
| `USER_STRIP_LED_COUNT` | `120` | Number of LEDs on user strip |
| `STATE_STRIP_LED_COUNT` | `60` | Number of LEDs on state strip |

See `.env.example` for the complete list of 347 configuration variables.

---

## 8. Database Layer

### Location
- **File**: `database/models.py` — ORM models
- **File**: `database/connection.py` — Connection management (sync + async)
- **File**: `database/repositories.py` — Data access layer

### ORM Models

| Model | Table | Purpose |
|-------|-------|---------|
| `User` | `users` | User accounts with subscription status, trial dates |
| `Bed` | `beds` | Registered bed devices with firmware info |
| `Event` | `events` | System events (voice turns, automations, errors) |
| `SleepSession` | `sleep_sessions` | Sleep tracking records |
| `SceneRecord` | `scene_records` | Applied lighting scenes |
| `MobileCommandRecord` | `mobile_commands` | Commands from mobile app |
| `MobileCommandFeedback` | `mobile_command_feedback` | User feedback on commands |
| `MobileAuthSession` | `mobile_auth_sessions` | JWT session tracking with revocation |
| `SpotifyToken` | `spotify_tokens` | Per-user Spotify OAuth tokens |
| `FeatureFlag` | `feature_flags` | Feature toggle system |
| `UserRoutine` | `user_routines` | Bedtime/morning routines |
| `UserPreference` | `user_preferences` | Key-value preference store |
| `UserSocialIdentity` | `user_social_identities` | Google/Apple/Facebook social logins |
| `PhoneAuth` | `phone_auth` | Phone number verification records |
| `OtpRequest` | `otp_requests` | OTP delivery tracking |

### Connection Strategy
- **Sync**: SQLAlchemy `QueuePool` via psycopg2 (used by web_server.py)
- **Async**: asyncpg pool (used by app_factory.py async routes)
- **Fallback**: SQLite at `data/manues.db` when PostgreSQL is unavailable
- **Retry**: Exponential backoff on connection failures (3 attempts)
- **Health check**: `SELECT 1` ping with configurable interval

### Repositories

| Repository | Methods |
|-----------|---------|
| `UserRepository` | `get_user_by_id`, `get_user_by_email`, `create_user`, `update_subscription`, `delete_user`, etc. |
| `EventRepository` | `log_event`, `get_events_by_user`, `get_events_by_type`, `count_events` |
| `SleepSessionRepository` | `create_session`, `end_session`, `get_recent_sessions`, `get_stats` |
| `MobileCommandRepository` | `log_command`, `get_history`, `log_feedback` |
| `MobileAuthRepository` | `create_session`, `revoke_session`, `revoke_all_for_user`, `is_revoked` |

---

## 9. API Layer

### Dual App Architecture

The API has two FastAPI applications being unified:

1. **`api/app_factory.py`** (new, recommended):
   - Created via `create_app()` factory function
   - Routers in `api/routers/`: `health`, `metrics`, `islamic`, `auth`, `alarms`, `sleep`, `scenes`, `profile`
   - Prometheus metrics middleware
   - Async DB + Redis + Firebase initialized in lifespan
   - Mounts `web_server.py` as catch-all fallback

2. **`web_server.py`** (legacy, 10,000+ lines):
   - Contains all original routes not yet migrated
   - Mobile API, Spotify OAuth, billing, scenes CRUD, chat, admin, sleep tracking
   - Sentry integration, structured logging
   - Being incrementally migrated to `api/routers/`

### Middleware Stack

| Middleware | File | Purpose |
|-----------|------|---------|
| **RateLimitMiddleware** | `api/middleware/rate_limiter.py` | Token-bucket rate limiting per IP |
| **CORSMiddleware** | FastAPI built-in | Cross-origin request handling |
| **ErrorHandlerMiddleware** | `api/middleware/error_handler.py` | Global exception → JSON response |
| **TracingMiddleware** | `api/middleware/tracing.py` | Request ID propagation |
| **MetricsMiddleware** | `api/app_factory.py` | Prometheus request instrumentation |
| **GzipMiddleware** | FastAPI built-in | Response compression |

---

## 10. Voice Runtime (app_entry.py)

### Overview
`app_entry.py` is the main voice interaction loop (~1800 lines). It runs as a standalone process (or Docker `voice` service).

### Startup Sequence

1. **Load user profile** from `runtime_data/user_profile.json`
2. **Initialize components**:
   - LED controller (hardware or simulated)
   - Cache manager, schedule manager, goal manager
   - Environment orchestrator, sleep intelligence engine
   - Personality runtime orchestrator
   - Music managers (Spotify + local)
   - STT manager (Deepgram Nova-2 or local Whisper)
   - TTS manager (Deepgram Aura-2)
   - Wake word manager (keyboard or voice mode)
   - Voice circuit breaker (fault tolerance)
   - Long-term memory store
   - Backend API client
3. **Register command handlers**: lights, sleep, reminders, chat, bed commands
4. **Initialize automations** from defaults
5. **Enter main loop**

### Main Loop Flow

```
Wake Word Detection
       │
       ▼
Alarm Check → Fire any due alarms
       │
       ▼
Sensor Update → Read pressure/motion data
       │
       ▼
Proactive Check → Morning/evening briefs, drift alerts, recovery cards
       │
       ▼
STT Capture → Listen for user speech (with interim results)
       │
       ▼
Intent Detection → Local command match or open question
       │
       ▼
┌─ Local Command ─────── Execute directly (lights, alarms, routines)
│
└─ Open Question ──────── GPT/Claude chat with context
                              │
                              ▼
                    Quality Gate + Brevity Control
                              │
                              ▼
                    TTS Synthesis → Audio Playback
                              │
                              ▼
                    Barge-In Detection → Allow interruption
```

### Key Functions in app_entry.py

| Function | Purpose |
|----------|---------|
| `main()` | Bootstrap and main loop |
| `_build_gpt_route_diagnostics()` | Check which AI providers are available |
| `_request_openai_chat_reply()` | Direct OpenAI API call |
| `play_tts_with_fast_start()` | Stream TTS audio with fast playback start |
| `build_user_context()` | Assemble context string for AI (goals, sleep, emotion, etc.) |
| `build_progress_summary()` | Format goal progress for AI context |

---

## 11. AI Modules

Located in `ai/` — 50+ modules covering all AI functionality.

### Speech Processing

| Module | Class/Function | Purpose |
|--------|---------------|---------|
| `stt_manager.py` | `STTManager` | Speech-to-text via Deepgram API or local Whisper |
| `tts_manager.py` | `TTSManager` | Text-to-speech via Deepgram Aura-2 with caching |
| `wake_word_manager.py` | `WakeWordManager` | Wake word detection (keyboard or voice mode) |
| `local_wake_word.py` | `LocalWakeWordDetector` | Offline wake word matching |
| `vad_filter.py` | `VadFilter` | Voice Activity Detection (WebRTC VAD) |
| `speaker_diarization.py` | `SpeakerDiarizer` | Who-spoke-when detection (pyannote) |
| `acoustic_echo_guard.py` | `AcousticEchoGuard` | Prevent STT from hearing TTS playback |
| `barge_in_monitor.py` | `ContinuousBargeInMonitor` | Detect user interruptions during TTS |

### Conversation & Intent

| Module | Class/Function | Purpose |
|--------|---------------|---------|
| `conversation_engine.py` | `ConversationEngine` | Multi-turn chat with context management |
| `intent_classifier.py` | `detect_led_command`, `detect_personality_switch` | Classify user intents |
| `action_resolver.py` | `resolve_action` | Map intents to executable actions |
| `emotion_router.py` | `detect_emotion_state` | Emotion detection (transformer + keyword fallback) |
| `offline_intent_pack.py` | `OfflineIntentPack` | Handle commands when AI is offline |
| `realtime_info.py` | `fetch_realtime_context` | Fetch live data for real-time queries |
| `safety_guardrails.py` | `evaluate_safety` | Content safety evaluation |
| `crisis_protocol.py` | `should_run_fast_protocol` | Crisis detection and response |

### Personality & Behavior

| Module | Class/Function | Purpose |
|--------|---------------|---------|
| `personality_runtime.py` | `PersonalityRuntimeOrchestrator` | Manage conversation quality, pacing, variety |
| `adaptive_personality_engine.py` | `AdaptivePersonalityEngine` | Learn and adapt to user preferences |
| `response_quality_gate.py` | `ResponseQualityGate` | Ensure response quality standards |
| `conversational_fillers.py` | `ConversationalFillerManager` | Natural filler phrases |
| `signature_experiences.py` | `SignatureExperienceEngine` | Deep recovery, couple harmony, 90-second reset |

### Memory & Learning

| Module | Class/Function | Purpose |
|--------|---------------|---------|
| `long_term_memory.py` | `LongTermMemoryStore` | Persistent conversation memory |
| `pgvector_memory_index.py` | `PgVectorMemoryIndex` | Vector similarity search for memory |
| `session_goal_manager.py` | `SessionGoalManager` | Track and manage user goals |
| `goal_compass.py` | `GoalCompass` | Goal prioritization and guidance |
| `goal_strategy_engine.py` | `GoalStrategyEngine` | Strategy coaching for goal achievement |

### Environment & Hardware

| Module | Class/Function | Purpose |
|--------|---------------|---------|
| `environment_orchestrator.py` | `EnvironmentOrchestrator` | Scene selection based on emotion/recovery/challenge |
| `sensor_bridge.py` | `SensorBridge` | Abstract sensor data access |
| `device_health.py` | `run_device_health_checks` | System diagnostics |
| `audio_output_manager.py` | `AudioOutputManager` | Audio device routing |
| `audio_playback_controller.py` | `AudioPlaybackController` | MP3 playback with pygame |

### Other AI Modules

| Module | Purpose |
|--------|---------|
| `breathing_guide_engine.py` | 4-7-8 breathing exercise guide |
| `dream_journal_manager.py` | Dream recording and analysis |
| `daily_life_support.py` | Daily coaching and support |
| `proactive_automation_engine.py` | Suggest automations proactively |
| `routine_engine.py` | Bedtime/morning routine management |
| `sleep_routine_manager.py` | Sleep routine scheduling |
| `spotify_manager.py` | Spotify playback control |
| `local_music_manager.py` | Local MP3 file playback |
| `voice_circuit_breaker.py` | Fault tolerance for voice pipeline |
| `realtime_voice_pipeline.py` | Low-latency voice processing |
| `bed_backend_client.py` | Communication with backend API |
| `online_calendar.py` | Calendar query answering |

---

## 12. Dana Voice Assistant

### Location
- `dana/dana_core.py` — Core coordinator
- `dana/personality.py` — Personality definitions
- `dana/coach.py` — Coach personality behavior
- `dana/guide.py` — Guide personality behavior
- `dana/therapist.py` — Therapist personality behavior
- `dana/dana_api.py` — API routes for Dana
- `dana/dana_islamic_voice.py` — Islamic voice integration

### Personalities

| Personality | Tone | Voice | Color | Use Case |
|-------------|------|-------|-------|----------|
| **Coach** | Motivational, energetic, data-driven | `aura-2-orion-en` | `#FF6B35` | Sleep performance optimization |
| **Guide** | Calm, warm, spiritual, peaceful | `aura-2-asteria-en` | `#7B68EE` | Gentle sleep companion |
| **Therapist** | Professional, empathetic, analytical | `aura-2-thalia-en` | `#00D4FF` | Sleep wellness, emotional support |

### Personality Switching
Users can switch by voice: "switch to coach mode", "be my therapist", etc. The system detects personality switch intent via `ai/intent_classifier.py:detect_personality_switch()`.

### Emotional Follow-Up System
When in Therapist mode, the system:
1. Detects distress keywords (English + Arabic)
2. Records the concern with topic summary
3. Next day, asks a caring follow-up question
4. User can opt out: "don't ask about this"

---

## 13. Islamic Mode

### Location
- `islamic_mode/prayer_times.py` — Prayer time fetching (Aladhan API)
- `islamic_mode/geolocation.py` — IP-based location detection
- `islamic_mode/quran_schedule.py` — Quran reading schedule
- `islamic_mode/hadith_daily.py` — Daily hadith
- `islamic_mode/dana_islamic_voice.py` — Islamic voice responses
- `islamic_mode/audio/quran_recitation.py` — Quran audio playback
- `islamic_mode/audio/reciter_catalog.py` — Available reciters
- `islamic_mode/content/prophet_stories.py` — Prophet stories content

### Prayer Times
- **API**: Aladhan.com (free, no key required)
- **Calculation methods**: 15 supported (MWL, ISNA, Egypt, Makkah, Kuwait, etc.)
- **Fiqh schools**: Hanafi, Shafi'i, Maliki, Hanbali (affects Asr timing)
- **Location**: City/country OR lat/lon coordinates
- **Auto-detection**: Optional IP geolocation
- **Cache**: Local JSON file with fallback when API is unavailable
- **Retry**: Exponential backoff (3 attempts) via tenacity

### Prayer-Time LED Colors
| Prayer | Color | Hex |
|--------|-------|-----|
| Fajr | Warm white | `#FFF5E0` |
| Dhuhr | White | `#FFFFFF` |
| Asr | Gold | `#FFD700` |
| Maghrib | Orange | `#FF6B35` |
| Isha | Purple | `#7B68EE` |

### Fajr Gentle Light
`prayer_handler.py:apply_fajr_gentle_light_scene()` — Sets breathing animation, orange color, 12% brightness for a gentle pre-Fajr wake.

---

## 14. Sleep Intelligence

### Location
- `ai/sleep_intelligence.py` — `SleepIntelligenceEngine` class
- `sleep_tracking/sleep_analyzer.py` — Sleep analysis
- `sleep_tracking/nap_optimizer.py` — Nap timing optimization
- `sleep_tracking/sleep_api.py` — Sleep data API

### Features

| Feature | Method | Description |
|---------|--------|-------------|
| **Bedtime tracking** | `record_bedtime_now()` | Log bedtime to history |
| **Wake tracking** | `record_wake_now()` | Log wake time to history |
| **Bedtime window** | `estimate_bedtime_window()` | Calculate optimal window from history |
| **Consistency score** | `sleep_consistency_score()` | Score 0-100 based on bedtime variation |
| **Quality score** | `sleep_quality_score()` | Composite score (duration + consistency + wakes + debt) |
| **Drift alert** | `bedtime_drift_alert()` | Detect if bedtime is sliding later |
| **Wind-down autopilot** | `build_wind_down_autopilot()` | Enable automated wind-down sequence |
| **Night wake recovery** | `night_wake_recovery_protocol()` | Protocol for middle-of-night wakes |
| **Recovery mode** | `evaluate_recovery_mode()` | Auto-activate when user is struggling |
| **Challenge ladder** | `adjust_challenge_level()` | Dynamic difficulty (levels 1-5) |
| **Partner mode** | `set_partner_mode_enabled()` | Dual-sleeper conflict-safe routines |
| **Sleep debt** | `sleep_debt_recovery_plan()` | Calculate debt and recovery plan |
| **Weekly insights** | `weekly_sleep_insights()` | Weekly coaching summary |
| **Weekly recovery card** | `weekly_recovery_score_card()` | Detailed weekly analysis with triggers |
| **Morning brief** | `build_morning_brief()` | Morning goal + sleep summary |
| **Evening brief** | `build_evening_brief()` | Evening coaching + bedtime target |

---

## 15. LED & Scene System

### Location
- `led/led_control.py` — `LEDController` class (abstraction over hardware)
- `led_controller.py` — Helper functions (color parsing, hardware config)
- `scenes/scene_store.py` — Scene persistence
- `scenes/circadian_engine.py` — Time-of-day automatic lighting
- `scenes/default_scenes.py` — Built-in scene definitions
- `scene_manager.py` — Scene payload creation

### LED Controller Features
- **Dual strip**: User strip (decorative) + State strip (system status)
- **Named colors**: 12+ named colors + hex code support + Arabic color names
- **Animations**: solid, breathing, rainbow, pulse, wave, spectrum, fireworks
- **Music reactive**: Pulse/wave/spectrum modes synced to audio playback
- **Brightness control**: Per-strip, 0-100%
- **Hardware backends**: WS2812 (rpi_ws281x), simulated (development)

### Arabic Color Support
| Arabic | English |
|--------|---------|
| احمر | red |
| اخضر | green |
| ازرق | blue |
| اصفر | yellow |
| بنفسجي | purple |
| ابيض | white |
| سماوي | cyan |
| برتقالي | orange |
| وردي | pink |

### Scene System
Scenes are combinations of color + animation + brightness applied to the LED strips. Scenes can be:
- **Default**: Built-in scenes (Cozy Night, Ocean Waves, Morning Light)
- **Custom**: User-created via API
- **Circadian**: Automatically selected based on time of day
- **Emotion-driven**: Selected by the environment orchestrator based on user emotion state
- **Premium**: Require subscription (gated by `SubscriptionGate`)

---

## 16. Automation Engine

### Location
- `automation_engine.py` — Runtime utilities
- `automations/registry.py` — `AutomationRegistry` class
- `automations/defaults.py` — Default automations
- `automations/base.py` — Base automation class
- `automations/bathroom_automation.py` — Bathroom trip detection

### How It Works
1. **Registration**: Automations are registered at startup from `build_default_automations()`
2. **Evaluation**: `run_automations()` is called periodically in the main loop
3. **Context**: Each run passes current time, timezone, sleep mode status, quiet hours, etc.
4. **Effects**: Automations produce effects: `say` (voice), `led` (lighting), `store` (state change)
5. **Cooldowns**: Each automation has a cooldown to prevent repetition

### Default Automations
- **Quiet hours**: Suppress notifications during configured window (default 22:00-07:00)
- **Fajr light**: Gentle orange breathing animation before Fajr prayer
- **Work planning reminder**: Nudge for work planning if no reminder exists
- **Sleep mode**: Auto-enable sleep mode at bedtime

### Reminders
- Voice-created reminders stored in `planned_reminders` list
- Nudge system: if a reminder is not completed within 10 minutes, send a gentle follow-up
- Completion: say "done with [task]" to mark complete

---

## 17. Hardware & Sensors

### Location
- `hardware/pi_sensors.py` — Raspberry Pi GPIO sensor reading
- `hardware/pi_led.py` — WS2812 LED strip driver
- `hardware/pressure_intelligence.py` — `PressureIntelligence` class

### Pressure Intelligence
Dual-zone pressure analysis for:
- **Occupancy detection**: Empty, left only, right only, both
- **Bed entry/exit events**: With duration tracking
- **Partner detection**: Arrival/departure events
- **Restlessness scoring**: Events per hour → deep_sleep / normal / light_sleep / restless
- **Movement summary**: Micro movements, major movements, position changes
- **Bathroom trip detection**: Short nighttime absence (< 10 min)
- **Extended absence**: Bed empty for > 72 hours

### Sensor Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `SENSOR_PRESSURE_ENABLED` | `0` | Enable pressure sensor |
| `SENSOR_MOTION_ENABLED` | `0` | Enable motion sensor |
| `SENSOR_PRESSURE_PIN` | `-1` | GPIO pin |
| `SENSOR_POLL_INTERVAL_SECONDS` | `0.2` | Polling interval |

---

## 18. Integrations

### Location: `integrations/`

| Module | Service | Description |
|--------|---------|-------------|
| `fitbit_client.py` | Fitbit | Sleep data, heart rate, activity via OAuth2 |
| `garmin_client.py` | Garmin Connect | Sleep and wellness data via garminconnect library |
| `google_calendar_client.py` | Google Calendar | Calendar event sync for scheduling |
| `calendar_sync.py` | Calendar abstraction | Unified calendar interface |
| `smart_home.py` | Smart home hub | Philips Hue, TP-Link Kasa, Xiaomi, Tuya, Apple TV, Chromecast |
| `mqtt_client.py` | MQTT | IoT device communication |
| `zigbee_coordinator.py` | Zigbee | Zigbee device mesh coordination |
| `fitness_tracker_api.py` | Fitness API | Unified fitness data access |
| `geofence_manager.py` | Geofencing | Location-based automation triggers |

### Spotify Integration
Located in `spotify/`:
- `spotify_api.py` — Spotify Web API client with OAuth flow
- `sleep_playlists.py` — Curated sleep/relaxation playlists
- `prayer_pause.py` — Auto-pause music during prayer times
- `spotify_volume.py` — Gradual volume control

---

## 19. Notifications

### Location: `notifications/`

| Module | Channel | Description |
|--------|---------|-------------|
| `email_service.py` | Email | SendGrid + AWS SES with template support |
| `fcm_sender.py` | Push (Android) | Firebase Cloud Messaging |
| `expo_sender.py` | Push (Expo) | Expo push notifications |
| `push_service.py` | Push (unified) | Abstract push interface |
| `whatsapp_sender.py` | WhatsApp | WhatsApp message delivery |
| `summaries.py` | Summary builder | `build_daily_summary()`, `build_monthly_summary()` |
| `notification_manager.py` | Router | Route notification to correct channel |
| `template_renderer.py` | Templates | Notification template rendering |

---

## 20. Subscriptions & Billing

### Location: `subscriptions/`

| Module | Purpose |
|--------|---------|
| `gate.py` | `SubscriptionGate` — check feature access (free/trial/premium) |
| `billing.py` | `BillingService` — subscription lifecycle management |
| `paypal_provider.py` | PayPal subscription integration |
| `plans.py` | Plan definitions (Standard Monthly/Yearly, Pro Monthly/Yearly) |

### Subscription Tiers

| Tier | Scene Limit | Features |
|------|-------------|----------|
| **Free** | 3 default scenes | Basic sleep tracking, voice commands |
| **Trial** | All scenes (time-limited + 2 day grace) | Full features for trial period |
| **Premium** | Unlimited | All features, advanced analytics, priority support |

### PayPal Flow
1. User initiates subscription via mobile app or admin panel
2. Backend creates PayPal subscription via API
3. PayPal redirects user for approval
4. Webhook confirms activation → update user status in DB
5. Recurring billing handled by PayPal

---

## 21. Gamification

### Location: `gamification/achievement_engine.py`

### Achievement Categories

| Category | Examples |
|----------|---------|
| **Sleep** | First Week (7 nights), Monthly Champion (30), Sleep Master (100), Year of Excellence (365) |
| **Quality** | Quality Sleeper (7 nights >80 score), Elite Sleeper (30 nights >85) |
| **Prayer** | Prayer Streak 7, Devoted Worshipper (30), Prayer Warrior (90) |
| **Features** | Explorer (5 features), Power User (10 features) |
| **Automation** | Automation Believer (50 accepted), Fully Automated (100) |
| **Streaks** | Consistent Sleeper (7 nights), Iron Discipline (30 nights) |
| **Wellness** | Zen Beginner (10 breathing), Debt Free (cleared sleep debt) |

### Rewards
Each achievement unlocks a reward:
- Custom scene builder, advanced analytics, exclusive scene packs
- Beta access, special prayer scenes, Ramadan scenes
- Extended breathing library, celebration animations
- Points system with leveling (200 points per level)

### Celebration
On unlock: LED fireworks animation (gold, 10 seconds) + push notification + voice announcement.

---

## 22. Guest Mode

### Location: `guest_mode/`

| Module | Purpose |
|--------|---------|
| `guest_manager.py` | `GuestModeManager` — activate/deactivate guest mode |
| `guest_api.py` | API routes for guest mode |
| `auto_guest_detection.py` | Automatic guest detection from pressure patterns |
| `guest_settings.py` | Guest-safe settings restrictions |

### How It Works
1. **Activation**: Voice command "enable guest mode" or API call
2. **Auto-reset**: Automatically deactivates at 6:00 AM next day
3. **Privacy**: Guest mode restricts access to personal data, memory, and preferences
4. **Detection**: Optional auto-detection from unusual pressure patterns (different person)

---

## 23. Partner Sleep Mode

### Location
- `ai/sleep_intelligence.py` (partner mode methods)
- `partner/compromise_engine.py` — Conflict resolution for partners
- `partner/staggered_wake.py` — Staggered wake-up for partners

### Features
- **Dual profiles**: Partner 1 and Partner 2 with independent wake styles
- **Wake styles**: gentle, balanced, energizing
- **Conflict-safe routines**: Staged wake when partners have different preferences
- **Staggered wake**: Wake one partner first, then the other after delay

### Voice Commands
- "enable partner sleep mode"
- "set partner 1 wake style gentle"
- "set partner 2 wake style energizing"
- "partner sleep mode status"

---

## 24. QR Code & Device Pairing

### Location: `qr_code/`

| Module | Purpose |
|--------|---------|
| `generate_qr.py` | Generate QR codes for device pairing |
| `pair_device.py` | `pair_device()`, `unpair_device()`, `get_device_status()` |
| `qr_api.py` | API routes for QR/pairing operations |

### Pairing Flow
1. **Device registration**: Bed device is registered with a unique `device_id`
2. **QR generation**: QR code encodes the `device_id` for scanning
3. **Mobile scan**: User scans QR with mobile app
4. **Pairing**: API call `pair_device(device_id, user_id, user_name)`
5. **Claim token**: A secure token is generated and rotated on each pair/unpair
6. **Generation counter**: Tracks how many times the device has been paired/unpaired
7. **Unpairing**: Admin or user can unpair; claim token is rotated

---

## 25. Mobile App (Flutter)

### Location: `mobile_app/`

### Tech Stack
- **Framework**: Flutter 3.x
- **State management**: flutter_riverpod
- **Error tracking**: sentry_flutter
- **Localization**: Flutter l10n (Arabic + English)
- **Local storage**: JournalStore (hive/shared_preferences)
- **Notifications**: Local notification service

### Key Screens
- **Main Shell**: Bottom navigation container
- **Onboarding**: First-time user setup flow
- **Dashboard**: Sleep summary, quick controls, today's goals
- **Sleep Tracking**: Log bedtime/wake, view history, quality scores
- **Scenes**: Browse, apply, and customize lighting scenes
- **Settings**: Profile, preferences, device management

### Building

```bash
cd mobile_app

# Install dependencies
flutter pub get

# Generate localizations
flutter gen-l10n

# Run in debug
flutter run

# Build APK
flutter build apk

# Build iOS
flutter build ios

# Analyze code
flutter analyze

# Run tests
flutter test
```

### Configuration
Sentry DSN and environment are passed via `--dart-define`:
```bash
flutter build apk \
  --dart-define=SENTRY_DSN=your_dsn \
  --dart-define=ENV=production
```

---

## 26. Web Admin Panel

### Location: `web/`

| File | Purpose |
|------|---------|
| `admin.html` | Main admin dashboard |
| `admin-panel.html` | Extended admin panel with device management |
| `admin-billing.html` | Billing and subscription management |
| `login.html` | Admin login page |
| `setup.html` | Initial setup wizard |
| `assets/app.js` | Frontend JavaScript |
| `assets/styles.css` | Stylesheets |

### Features
- Device status monitoring
- User management
- Scene management
- Sleep data viewing
- Subscription management
- System health dashboard
- Automation configuration

### Access
- Served by the FastAPI backend at `http://localhost:8000/admin.html`
- Authentication required (JWT-based)

---

## 27. Authentication & Security

### Location: `auth/jwt_handler.py`

### JWT Authentication
- **Algorithm**: HS256
- **Library**: authlib (replaces python-jose)
- **Access token**: Contains `sub` (user_id), `jti` (revocation key), `exp`, `iat`
- **Refresh token**: Longer-lived, stored in `mobile_auth_sessions` table
- **Revocation**: Per-session revocation via JTI lookup in database

### Security Features
- **Secret key validation**: Refuses weak keys in production
- **Rate limiting**: Per-IP token-bucket (configurable per endpoint category)
- **CORS**: Configurable origins with regex support
- **Sentry scrubbing**: Strips passwords, tokens, API keys from error reports
- **Sensitive key filtering**: Automatic redaction in logs
- **Bandit scanning**: Static security analysis in CI
- **Gitleaks**: Secret scanning in CI
- **OTP**: Phone number verification with Twilio SMS

### Social Login
- Google, Apple, Facebook identity verification
- Tokens decoded (unverified) for claim extraction, then verified upstream

---

## 28. Testing

### Location: `tests/`

### Running Tests

```bash
# Full test suite with coverage
pytest tests/ --cov --cov-report=term-missing -q --tb=short

# Specific test file
pytest tests/test_sleep_intelligence.py -v

# Specific test
pytest tests/test_action_resolver.py::test_resolve_light_command -v

# With parallel execution
pytest tests/ -n auto
```

### Test Structure

| Directory/File | Coverage |
|---------------|----------|
| `tests/test_*.py` | 86+ test files for individual modules |
| `tests/integration/` | Integration tests |
| `tests/fixtures/` | Test data fixtures |
| `tests/final_system_check.py` | End-to-end system validation |

### Key Test Files
- `test_sleep_intelligence.py` — Sleep engine tests
- `test_action_resolver.py` — Intent-to-action mapping
- `test_acoustic_echo_guard.py` — Echo cancellation
- `test_admin_mobile_beta_acceptance.py` — Mobile API acceptance tests
- `test_automation_engine.py` — Automation trigger tests

### CI Test Configuration
- **Database**: SQLite in-memory (`DATABASE_URL=sqlite://`)
- **Coverage**: XML report uploaded as artifact
- **Markers**: Custom pytest markers in `pyproject.toml`

---

## 29. Docker & Deployment

### Docker Services (docker-compose.yml)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `api` | Custom (Dockerfile) | 8000 | FastAPI backend |
| `voice` | Custom (Dockerfile) | — | Voice runtime (app_entry.py) |
| `worker` | Custom (Dockerfile) | — | ARQ job worker |
| `redis` | redis:7-alpine | 6379 | Cache + job queue |
| `db` | postgres:16-alpine | 5432 | Primary database |

### Resource Limits

| Service | CPU | Memory |
|---------|-----|--------|
| api | 2.0 cores | 2 GB |
| voice | 1.5 cores | 1 GB |
| worker | 1.0 core | 512 MB |
| redis | 0.5 core | 256 MB |
| db | 1.0 core | 1 GB |

### Dockerfile Details
- **Base**: `python:3.11-slim`
- **System deps**: portaudio19-dev, libatlas-base-dev, gcc, curl
- **Server**: Gunicorn with 4 Uvicorn workers
- **Health check**: `curl -f http://localhost:8000/healthz` every 30s
- **Worker recycling**: 1000 requests max per worker (prevents memory leaks)

### Production Deployment

```bash
# Set required environment variables
export POSTGRES_PASSWORD=<secure_password>

# Build and start
docker compose up -d --build

# Check health
curl http://localhost:8000/healthz

# View logs
docker compose logs -f api

# Run migrations
docker compose exec api alembic upgrade head
```

### Systemd (Raspberry Pi)
Service files in `scripts/systemd/`:
- `smart-bed-api.service` — API server
- `smart-bed-runtime.service` — Voice runtime

---

## 30. CI/CD Pipeline

### Location: `.github/workflows/ci.yml`

### Jobs

| Job | Trigger | Steps |
|-----|---------|-------|
| **backend** | Push/PR to main, develop | Checkout → Python 3.11 → Install deps → Ruff lint → Ruff format → Bandit security → mypy → pytest with coverage |
| **smoke** | After backend passes | Start API server → Run mobile smoke tests |
| **mobile** | Push/PR to main, develop | Flutter setup → pub get → gen-l10n → analyze → test |
| **secrets** | Push/PR to main, develop | Gitleaks secret scanning |

### Concurrency
- Cancel in-progress runs on new pushes to same branch
- Prevents wasted CI minutes

---

## 31. Voice Commands Reference

### Wake & Session
| Command | Action |
|---------|--------|
| "wake" / "hello" / "hey smart bed" | Start listening session |
| "sleep mode" | End active listening |
| "exit" / "quit" / "bye" | Exit system |

### Lights
| Command | Action |
|---------|--------|
| "set user strip to blue" | Change user strip color |
| "set user strip to #00ffaa" | Set hex color |
| "set animation to rainbow" | Change animation mode |
| "dim lights" / "set brightness to 50" | Adjust brightness |
| "turn on music lights" | Enable music-reactive mode |
| "set music lights to wave mode" | Change music light mode |
| "set music lights brightness to 30" | Music lights brightness |

### Sleep
| Command | Action |
|---------|--------|
| "log bedtime" | Record current time as bedtime |
| "log wake" | Record current time as wake |
| "sleep consistency" | Get consistency score |
| "sleep quality score" | Get quality score |
| "predictive bedtime drift" | Check for drift alert |
| "weekly sleep insights" | Get weekly analysis |
| "start wind down autopilot 45" | 45-min wind-down |
| "optimize my room for sleep" | One-command sleep setup |
| "night wake recovery" | Night wake protocol |
| "sleep debt recovery plan" | Debt calculation + plan |
| "weekly recovery score card" | Weekly detailed analysis |

### Partner Sleep
| Command | Action |
|---------|--------|
| "enable partner sleep mode" | Activate dual-sleeper mode |
| "set partner 1 wake style gentle" | Configure partner 1 |
| "set partner 2 wake style energizing" | Configure partner 2 |
| "partner sleep mode status" | View current config |

### Routines
| Command | Action |
|---------|--------|
| "set bedtime routine for 22:30" | Schedule bedtime routine |
| "set morning routine for 07:00" | Schedule morning routine |

### Wellness
| Command | Action |
|---------|--------|
| "start breathing guide" | Begin 4-7-8 breathing exercise |
| "dream journal" | Record a dream |
| "dream insights" | Analyze dream patterns |

### Signature Experiences
| Command | Action |
|---------|--------|
| "start deep recovery" | Deep recovery mode |
| "run couple harmony wake" | Partner harmony wake |
| "90 second reset" | Quick reset experience |

### System & Privacy
| Command | Action |
|---------|--------|
| "run health check" | System diagnostics |
| "pilot readiness report" | Full readiness check |
| "bed phase status" | Current system phase |
| "privacy status" | View data retention |
| "set retention to 30 days" | Configure data retention |
| "delete all my data" | Delete user data |
| "help" | Show command overview |
| "sleep help" | Show sleep commands |
| "bed tutorial" | Start guided tour |

### Audio
| Command | Action |
|---------|--------|
| "use bed speaker" | Switch to bed speaker |
| "scan bluetooth speakers" | Discover BT speakers |
| "connect bluetooth speaker [name]" | Connect to BT speaker |

### Personality
| Command | Action |
|---------|--------|
| "switch to coach mode" | Activate Coach personality |
| "be my therapist" | Activate Therapist personality |
| "switch to guide" | Activate Guide personality |
| "adaptive personality insights" | View personality adaptation data |

---

## 32. API Endpoints Reference

### Health & Monitoring
| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe (DB + Redis) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/v1/system/status` | Full system status |

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/auth/register` | Create new user |
| POST | `/v1/auth/login` | Login with email/password |
| POST | `/v1/auth/refresh` | Refresh access token |
| POST | `/v1/auth/logout` | Revoke session |
| POST | `/v1/auth/phone/request-otp` | Request phone OTP |
| POST | `/v1/auth/phone/verify-otp` | Verify phone OTP |
| POST | `/v1/auth/social/google` | Google social login |
| POST | `/v1/auth/social/apple` | Apple social login |

### Profile
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/profile` | Get user profile |
| PUT | `/v1/profile` | Update profile |
| DELETE | `/v1/profile` | Delete account and data |

### Sleep
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/sleep/log-bedtime` | Log bedtime |
| POST | `/v1/sleep/log-wake` | Log wake time |
| GET | `/v1/sleep/history` | Get sleep history |
| GET | `/v1/sleep/score` | Get sleep quality score |
| GET | `/v1/sleep/insights` | Get weekly insights |

### Scenes
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/scenes` | List all scenes |
| POST | `/v1/scenes` | Create custom scene |
| PUT | `/v1/scenes/{id}` | Update scene |
| POST | `/v1/scenes/{id}/apply` | Apply scene to bed |
| DELETE | `/v1/scenes/{id}` | Delete scene |

### Alarms
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/alarms` | List alarms |
| POST | `/v1/alarms` | Create alarm |
| PUT | `/v1/alarms/{id}` | Update alarm |
| DELETE | `/v1/alarms/{id}` | Delete alarm |

### Islamic Mode
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/islamic/prayer-times` | Today's prayer times |
| GET | `/v1/islamic/next-prayer` | Next upcoming prayer |
| GET | `/v1/islamic/quran/schedule` | Quran reading schedule |
| GET | `/v1/islamic/hadith/daily` | Daily hadith |
| GET | `/v1/islamic/fiqh-info` | Current Fiqh school info |
| PUT | `/v1/islamic/fiqh-school` | Change Fiqh school |
| PUT | `/v1/islamic/location` | Update prayer location |

### Spotify
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/spotify/auth-url` | Get Spotify OAuth URL |
| GET | `/v1/spotify/callback` | OAuth callback handler |
| POST | `/v1/spotify/play` | Play music |
| POST | `/v1/spotify/pause` | Pause music |
| GET | `/v1/spotify/status` | Current playback status |

### QR / Device Pairing
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/qr/generate` | Generate pairing QR code |
| POST | `/v1/qr/pair` | Pair device to user |
| POST | `/v1/qr/unpair` | Unpair device |
| GET | `/v1/qr/status/{device_id}` | Device pairing status |

### Billing
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/billing/subscribe` | Create PayPal subscription |
| POST | `/v1/billing/webhook` | PayPal webhook receiver |
| GET | `/v1/billing/status` | Current subscription status |
| POST | `/v1/billing/cancel` | Cancel subscription |

### Guest Mode
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/guest/activate` | Activate guest mode |
| POST | `/v1/guest/deactivate` | Deactivate guest mode |
| GET | `/v1/guest/status` | Guest mode status |

---

## 33. Troubleshooting

### Common Issues

**Problem**: `ModuleNotFoundError: No module named 'pyaudio'`
**Fix**: Install PortAudio system library first:
```bash
# Windows: pip install pyaudio
# Linux: sudo apt-get install portaudio19-dev && pip install pyaudio
# Mac: brew install portaudio && pip install pyaudio
```

**Problem**: `ValueError: Duplicated timeseries in CollectorRegistry`
**Fix**: Prometheus metrics are registered twice. Only run one of `web_server.py` or `api.app_factory:app`, not both standalone.

**Problem**: Voice commands not working in keyboard mode
**Fix**: Ensure `WAKE_WORD_MODE=keyboard` in `.env`. Type "wake" + Enter to start, then type commands.

**Problem**: TTS audio not playing
**Fix**: Check `DEEPGRAM_TTS_API_KEY` is set. Verify `output_audio/` directory exists. Check pygame audio device.

**Problem**: Prayer times returning empty
**Fix**: Check internet connectivity. Verify `ISLAMIC_PRAYER_CITY` and `ISLAMIC_PRAYER_COUNTRY` in `.env`. Check `runtime_data/prayer_times_cache.json` for cached data.

**Problem**: Database connection refused
**Fix**: Ensure PostgreSQL is running. Check `DATABASE_URL` in `.env`. For local dev, SQLite fallback is automatic if PostgreSQL URL is invalid.

**Problem**: JWT tokens rejected
**Fix**: Ensure `SECRET_KEY` is set consistently across restarts. In production, must be 32+ characters.

**Problem**: LED hardware not responding
**Fix**: Ensure `LED_HARDWARE_ENABLED=1` and correct GPIO pins. Must run with `sudo` on Raspberry Pi for hardware access.

**Problem**: Docker compose fails on `POSTGRES_PASSWORD`
**Fix**: Set `POSTGRES_PASSWORD` in your `.env` file. The compose file requires it: `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env}`.

---

*End of Project Manual*
