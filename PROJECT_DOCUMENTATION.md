# Smart Bed AI (Danah) — Complete Project Documentation

> **Project Name:** Smart Bed AI (Danah)  
> **Author:** Hamoud  
> **Type:** Full-Stack AI-Powered Smart Bed System  
> **Stack:** Python (FastAPI) + Flutter (Dart) + Raspberry Pi 5  
> **Target Market:** Kuwait (initial), expandable globally  
> **Last Updated:** May 2026

---

## 1. Executive Summary

**Smart Bed AI (Danah)** is a production-grade AI-powered smart bed platform combining:

- A **voice-controlled AI assistant** ("Danah") with 3 adaptive personalities
- **Sleep tracking & intelligence** — ML-based analytics, anomaly detection, debt tracking
- **IoT hardware** — LED strips, temperature/humidity/heart-rate sensors via Raspberry Pi 5
- **Flutter mobile app** — full-featured cross-platform client (Android/iOS/Windows)
- **FastAPI backend** — REST, WebSocket, SSE streaming, 17 API routers
- **Islamic lifestyle features** — prayer times, Quran, Ramadan mode, Tahajjud
- **Smart home integration** — Spotify, Fitbit, Garmin, Calendar, Zigbee, MQTT

### What Makes This Unique

| Feature | Description |
|---|---|
| AI Personality System | 3 personalities (Guide, Coach, Therapist) — auto-switches on emotion |
| Long-Term Memory | pgvector semantic search — Danah remembers past conversations |
| Sleep Science Engine | Bedtime drift, sleep debt, nap optimization, circadian scenes |
| Islamic Integration | Prayer automations, Fajr wake, Ramadan mode, Tahajjud, daily Hadith |
| Multi-Sensor Fusion | Pressure, motion, temperature, humidity, heart rate, SpO2 |
| Full Voice Pipeline | Wake word → STT → LLM → TTS with barge-in, echo cancel, circuit breaker |

---

## 2. System Architecture

```
USER INTERFACES: Flutter App | Web Admin | Voice (Mic)
        │
        ▼
FASTAPI BACKEND (Port 8000)
├── 17 API Routers (auth, devices, sleep, chat, admin, etc.)
├── AI Engine (54 modules)
├── Automation Engine (bedtime, wake, Islamic, bathroom)
├── Hardware Bridge (LED, sensors, GPIO)
        │
        ▼
DATA LAYER: PostgreSQL+pgvector | Redis (pub/sub + jobs) | External APIs
```

**Docker Compose runs 7 services:**
1. `api` — FastAPI (Gunicorn, 4 workers)
2. `voice` — Voice assistant runtime
3. `worker` — arq background job worker
4. `migrations` — Alembic DB migrations
5. `db` — PostgreSQL 16
6. `redis` — Redis 7 (pub/sub + queue)
7. `prometheus` + `grafana` — Monitoring

---

## 3. Technology Stack

### Backend
| Tech | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Runtime |
| FastAPI | 0.115.0 | Web framework |
| Gunicorn + Uvicorn | latest | Production server |
| PostgreSQL | 16 | Primary database |
| pgvector | 0.3.2 | Semantic memory |
| Redis | 7 | Cache, pub/sub, job queue |
| SQLAlchemy | 2.0.35 | ORM (sync + async) |
| Alembic | 1.13.1 | Migrations |
| arq | 0.26.1 | Async job queue |

### AI & Voice
| Tech | Purpose |
|---|---|
| Deepgram Nova-2 (SDK 3.7.7) | Speech-to-text |
| Deepgram Aura-2 | Text-to-speech (3 voice personas) |
| Claude/Anthropic (0.40.0) | Primary LLM |
| GPT-4o-mini (OpenAI) | Fallback LLM |
| LiteLLM (1.83.0) | Universal LLM router |
| sentence-transformers (3.0.1) | Embedding vectors |
| pyannote.audio (3.3.0) | Speaker diarization |
| webrtcvad (2.0.14) | Voice activity detection |
| faster-whisper (1.0.3) | Local/offline STT |

### Analytics & ML
| Tech | Purpose |
|---|---|
| pandas, numpy | Data analysis |
| scikit-learn | Anomaly detection, clustering |
| statsmodels | Time-series forecasting |
| antropy | Signal entropy (sleep depth) |
| plotly | Interactive charts |
| reportlab + weasyprint | PDF reports |

### Mobile
| Tech | Purpose |
|---|---|
| Flutter 3.41+ | Cross-platform app |
| Riverpod | State management |
| Sentry Flutter | Crash reporting |

### Infrastructure
| Tech | Purpose |
|---|---|
| Docker + docker-compose | Containerization |
| Prometheus + Grafana | Monitoring |
| Sentry + OpenTelemetry | Error tracking + tracing |
| GitHub Actions | CI/CD |
| AWS S3 + SES | Storage + email |
| Firebase FCM | Push notifications |

---

## 4. AI Engine — 54 Modules

### 4.1 Core AI Modules

| Module | Size | Function |
|---|---|---|
| `conversation_engine.py` | 39.5KB | LLM chat (Claude/GPT), streaming, token budget |
| `stt_manager.py` | 35.2KB | Speech-to-text orchestration |
| `sleep_intelligence.py` | 28.7KB | Sleep analytics core |
| `long_term_memory.py` | 21.8KB | Persistent conversational memory |
| `personality_runtime.py` | 18.8KB | Personality orchestration |
| `online_calendar.py` | 18.2KB | Google Calendar integration |
| `personality_evolution.py` | 14.2KB | Personality learning over time |
| `structured_extraction.py` | 14.6KB | Structured LLM output parsing |
| `tts_manager.py` | 14.3KB | Text-to-speech with 3 voices |
| `automation_learning_engine.py` | 13KB | Learns automation preferences |
| `wake_word_manager.py` | 10.8KB | Wake word detection |
| `activity_predictor.py` | 10.2KB | User activity pattern prediction |
| `speaker_diarization.py` | 9.9KB | Who-spoke-when identification |
| `sensor_bridge.py` | 9.3KB | Unified sensor interface |
| `voice_circuit_breaker.py` | 9KB | Fault tolerance for voice |
| `emotion_router.py` | 8.5KB | Emotion detection from text |
| `pgvector_memory_index.py` | 8.1KB | PostgreSQL vector similarity |
| `goal_strategy_engine.py` | 8.1KB | Goal decomposition |
| `bed_backend_client.py` | 7KB | HTTP client for bed device |
| `daily_life_support.py` | 7KB | Daily event context injection |

### 4.2 Personality System

Danah has **3 adaptive personalities**:

| Personality | TTS Voice | Behavior | Trigger |
|---|---|---|---|
| **Guide** | aura-2-asteria-en | Calm, informative | Default |
| **Coach** | aura-2-orion-en | Motivational, energetic | Goals, challenges |
| **Therapist** | aura-2-thalia-en | Empathetic, gentle | Stress, anxiety |

### 4.3 Safety Systems

| Module | Function |
|---|---|
| `safety_guardrails.py` | Content filtering, topic blocking |
| `safety_valve.py` | Emergency output shutdown |
| `crisis_protocol.py` | Crisis detection + emergency resources |
| `response_quality_gate.py` | Validates LLM output before delivery |

### 4.4 Voice Pipeline

```
Wake Word → VAD Filter → STT (Deepgram) → Intent Classify → LLM (Claude)
    → Response Quality Gate → TTS (Deepgram Aura-2) → Speaker Output
```

Features: barge-in detection, echo cancellation, noise reduction, loudness normalization, circuit breaker with exponential backoff.

---

## 5. Sleep Intelligence System

### 5.1 Core Engine (`ai/sleep_intelligence.py` — 28.7KB)
- Bedtime/wake history tracking
- Sleep duration validation (2-16h range)
- Bedtime drift detection (>30min variance alert)
- Recovery mode for sleep debt
- Challenge system (levels 1-5)
- Partner mode (dual profiles)

### 5.2 Sleep Tracking Modules

| Module | Size | Function |
|---|---|---|
| `sleep_analyzer.py` | 35.9KB | Stages, efficiency, anomaly detection |
| `wake_optimizer.py` | 20.6KB | Optimal wake time (sleep cycle alignment) |
| `sleep_debt_tracker.py` | 13.2KB | Cumulative debt + recovery recommendations |
| `nap_optimizer.py` | 13.1KB | Nap timing based on circadian rhythm |
| `weekly_report.py` | 6.5KB | Weekly sleep summary |
| `sleep_score.py` | 2.3KB | Composite quality score (0-100) |

### 5.3 Wind-Down System (`winddown/`)
- 30-60 min pre-sleep routine management
- Guided breathing exercises (4-7-8, box breathing)
- Gradual LED dimming sequences
- REST API for session control

---

## 6. Islamic Mode (14 files)

| Module | Size | Function |
|---|---|---|
| `prayer_times.py` | 17KB | Multi-method prayer calculation, offline cache |
| `ramadan_mode.py` | 15.2KB | Suhoor/Iftar, reduced AI during fasting |
| `prayer_automation.py` | 14.6KB | Fajr gentle-light, adhan notifications |
| `hadith_daily.py` | 18.1KB | Daily hadith with Arabic text |
| `tahajjud_manager.py` | 11.9KB | Night prayer automation |
| `islamic_calendar.py` | 7.5KB | Hijri calendar (offline conversion) |
| `islamic_api.py` | 16.7KB | REST API for all Islamic features |
| `sunnah_tips.py` | 4.6KB | Daily lifestyle tips |
| `geolocation.py` | 4.2KB | Auto-detect location for prayers |
| `dana_islamic_voice.py` | 2.1KB | Islamic personality adjustments |

---

## 7. Hardware & IoT

### 7.1 Sensors (Raspberry Pi 5)

| Sensor | Module | Protocol | Data |
|---|---|---|---|
| AM2301A/DHT22 | `pi_temperature.py` (8.5KB) | GPIO | Temp °C, Humidity % |
| MAX30102 | `pi_heart_rate.py` (7.8KB) | I2C | Heart rate BPM, SpO2 % |
| Pressure Pad | `pi_sensors.py` (7.9KB) | GPIO | Bed occupancy |
| Motion Sensor | `pi_sensors.py` | GPIO | Movement |

### 7.2 LED System
- **User Strip**: GPIO 18, 120 LEDs — ambient lighting
- **State Strip**: GPIO 13, 60 LEDs — status indicators
- NeoPixel/WS2812B driver (`pi_led.py`, 10.8KB)
- Animation FPS: 20, max brightness: 255

### 7.3 Scenes (`scenes/`)
| Module | Function |
|---|---|
| `circadian_engine.py` (14.8KB) | Time-of-day color temp (2700K→6500K) |
| `weather_adaptive.py` (14KB) | Dynamic scenes from weather data |
| `scene_store.py` (5.7KB) | Scene CRUD |

### 7.4 Pressure Intelligence (`pressure_intelligence.py`, 14.4KB)
- Restlessness scoring from pressure data
- Bed entry/exit detection
- Sleep position change analysis

---

## 8. Mobile App (Flutter)

### 8.1 Architecture
- **State**: Riverpod
- **Screens**: 19 main screens + 21 additional screen folders
- **Platforms**: Android, iOS, Windows
- **Error tracking**: Sentry Flutter

### 8.2 Key Screens

| Screen | Size | Purpose |
|---|---|---|
| Settings | 52.2KB | Full settings (bed, notifications, Islamic, automation) |
| Dashboard | 21.4KB | Sleep stats, quick actions, sensor data |
| Auth | 20.1KB | Login, register, social, OTP |
| Bed Controls | 14.8KB | LED, scenes, manual commands |
| Alarm | 13.2KB | Smart alarm with wake styles |
| Connect Bed | 12.8KB | Device pairing |
| Islamic | 12.7KB | Prayer times, Quran, Hadith |
| Dana Chat | 12.1KB | AI chat interface |
| Report | 11.9KB | Sleep reports |
| Spotify | 11.3KB | Music integration |
| Scenes | 10.7KB | Scene browsing |
| Timeline | 10.8KB | Activity timeline |
| Subscription | 9.2KB | Billing |
| Onboarding | 7.9KB | First-time flow |

Additional screens: Achievements, Journal, Health, LED Picker, Partner, QR Pairing, Sleep Tips, Sounds, Wind-Down.

---

## 9. Database — 28 Tables

### Key Tables

| Table | Purpose |
|---|---|
| `users` | Accounts (email, role, subscription, timezone) |
| `beds` | Physical devices (device_id, firmware, online status) |
| `sleep_sessions` | Nightly data (bedtime, wake, duration, restlessness) |
| `events` | Audit trail (type, metadata JSON, trace_id) |
| `alarms` | Smart alarms (time, days, wake_style, smart_window) |
| `user_memory_entries` | AI conversation memory (text, emotion, personality) |
| `subscription_records` | Billing (tier, provider, price_kwd, renewal) |
| `feature_flags` | Feature toggles with rollout % |
| `beta_cohort_members` | Beta testing groups |
| `app_versions` | App version management with forced updates |
| `firmware_versions` | OTA firmware updates |

### Database Features
- PostgreSQL 16 with pgvector extension
- Connection pools: sync (10+20 overflow) + async (2-10)
- Alembic migrations
- All FKs with CASCADE delete
- Composite indexes on frequently queried columns
- UUID primary keys (string format)

---

## 10. Authentication & Security

### Auth Flow
- JWT tokens (HS256): access (15-60 min) + refresh (7-30 days)
- Token rotation on refresh (old token revoked)
- bcrypt password hashing (12 rounds)
- RBAC: `user`, `admin`, `superadmin`
- Phone OTP with hashed codes + attempt limits
- Social auth: Google, Apple, Facebook

### Security Measures
- Rate limiting (slowapi): 5/min login, 3/hr register
- CORS: HTTPS-only in production, regex validation
- Secret validation on startup (rejects weak keys)
- Pydantic input validation on all endpoints
- Token blacklisting on logout
- Sentry error tracking
- Production secret audit function

---

## 11. Automation Engine

### Built-In Automations
| Automation | Trigger | Action |
|---|---|---|
| Bedtime Reminder | bedtime - 30min | Notification + light shift |
| Smart Wake | Optimal wake time | Gradual light + audio |
| Bedtime Drift Alert | >30min variance | User notification |
| Wind-Down Start | bedtime - 45min | Dim lights |
| Quiet Hours | 22:00-07:00 | Mute + dim |
| Bathroom Night Light | Bed exit detected | Dim pathway lighting |

### Islamic Automations
| Automation | Action |
|---|---|
| Fajr Wake | Gentle light + Quran |
| Prayer Reminder | Push notification per prayer |
| Tahajjud | Soft wake in last third of night |
| Suhoor (Ramadan) | Pre-dawn meal alarm |

### Learning Engine (`automation_learning_engine.py`, 13KB)
- Learns from user patterns
- Adjusts timing based on actual behavior
- Suggests new automations

---

## 12. Notifications

| Channel | Provider | Module |
|---|---|---|
| Push (Android/iOS) | Firebase FCM | `fcm_sender.py` (13.8KB) |
| Push (Expo) | Expo | `expo_sender.py` (6.9KB) |
| Email | AWS SES | `ses_sender.py` (6.3KB) |
| WhatsApp | WhatsApp Business | `whatsapp_notifier.py` (2.3KB) |

Features: scheduling, digest summaries, re-engagement campaigns (11.7KB).

---

## 13. Subscription & Billing

| Tier | Features |
|---|---|
| **Free** | Basic sleep, 1 alarm, limited scenes |
| **Standard** | Full analytics, unlimited alarms, all scenes, Spotify |
| **Pro** | Everything + Islamic, partner mode, advanced AI |

- **PayPal** integration (sandbox + production)
- Webhook verification
- Trial automation with conversion flows
- Feature gating (`subscriptions/gate.py`)

---

## 14. Integrations

| Integration | Module | Capabilities |
|---|---|---|
| Fitbit | `fitbit_client.py` (16.4KB) | Sleep stages, HR, SpO2, steps |
| Garmin | `garmin_client.py` (13.8KB) | Sleep, HRV, body battery |
| Google Calendar | `google_calendar_client.py` (6.2KB) | Schedule-aware automations |
| Smart Home | `smart_home.py` (30.8KB) | Third-party device control |
| MQTT | `mqtt_client.py` (11.7KB) | IoT messaging |
| Zigbee | `zigbee_coordinator.py` (12.1KB) | Zigbee devices |
| Geofence | `geofence_manager.py` (8.9KB) | Location-based automations |
| Spotify | OAuth + playback | Sleep playlists |

---

## 15. Monitoring & Observability

| Tool | Purpose |
|---|---|
| Prometheus | Metrics (request count, latency, errors) |
| Grafana | Dashboards (API perf, resources, business) |
| Sentry | Error tracking + performance monitoring |
| OpenTelemetry | Distributed tracing |
| Loguru | Structured JSON logging |
| Health endpoints | `/healthz`, `/healthz/detailed` |

### Alert Rules
- High error rate (>5% for 5min)
- High latency (P95 >2s for 5min)
- Service downtime (>2min)
- High memory (>1GB for 10min)
- Auth failure spike (>5/s for 10min)

---

## 16. Deployment

### Docker Production
```yaml
# 7 services: api, voice, worker, migrations, db, redis, prometheus+grafana
# Resource limits: api (2 CPU, 2GB), voice (1.5 CPU, 1GB), db (1 CPU, 1GB)
# Health checks on all services
# Volume persistence for data, audio, music, postgres
```

### Raspberry Pi 5 (Edge)
- Runs voice runtime + API server
- Connects to phone app via local network
- GPIO sensor access
- LED hardware control
- Offline-capable (local STT, cached prayer times)

### CI/CD (GitHub Actions)
- Backend: Python 3.11 + ruff lint + unittest
- Mobile: Flutter 3.41 + analyze + test
- Blocks merge if either lane fails

---

## 17. Testing — 90 Test Files

### Test Categories
| Category | Example Files |
|---|---|
| AI modules | `test_conversation_engine`, `test_intent_classifier`, `test_emotion_router` |
| Auth | `test_mobile_auth_api`, `test_web_auth_flows` |
| Database | `test_database_models`, `test_profile_repository` |
| Voice | `test_stt_manager`, `test_tts_manager`, `test_vad_filter` |
| Automation | `test_automation_registry`, `test_proactive_automation` |
| Sleep | `test_sleep_quality_score`, `test_sleep_overview` |
| Subscriptions | `test_subscription_endpoints`, `test_subscription_gate` |
| Mobile API | `test_mobile_*` (12+ files) |
| Hardware | `test_pi_sensors`, `test_led_hardware_backend` |
| Integration | `test_online_calendar`, `test_spotify` |

### Testing Tools
- **pytest** + pytest-asyncio
- **hypothesis** — property-based testing
- **freezegun** — time mocking
- **Coverage target**: 70%+ (configured in `.coveragerc`)

---

## 18. Project Audit Summary

### Current Scores (from action plan)

| Area | Score | Key Strengths | Key Gaps |
|---|---|---|---|
| Backend | 68/100 | 54 AI modules, full voice pipeline | `web_server.py` monolith (397KB) |
| Flutter App | 62/100 | 19+ screens, Riverpod, theming | Dual screen systems need merge |
| Hardware/IoT | 35/100 | Driver code exists | Needs real sensor testing on Pi |
| Database | 82/100 | 28 tables, migrations, async | Legacy SQLite remnants |
| Security | 72/100 | JWT, bcrypt, RBAC, rate limiting | Some hardcoded values |
| **Overall MVP** | **55/100** | — | — |

### Strengths
- **54 AI modules** with production-grade patterns (retry, circuit breaker, streaming)
- **Full voice pipeline** end-to-end (wake word → TTS)
- **28-table PostgreSQL schema** with proper indexes and constraints
- **JWT + RBAC + OTP** authentication system
- **Docker-compose** production deployment with health checks
- **Prometheus + Grafana + Sentry** monitoring stack
- **90 test files** with hypothesis property testing
- **Islamic features** — deeply integrated, not bolted on
- **Multi-provider AI** — Claude primary, GPT fallback, LiteLLM routing

### Areas for Improvement
- Migrate remaining routes from `web_server.py` (397KB monolith) to dedicated routers
- Merge duplicate Flutter screen systems
- Test hardware sensors on actual Raspberry Pi
- Remove hardcoded secrets from docker-compose
- Expand smaller AI modules (crisis_protocol, goal_compass)
- Achieve 80%+ test coverage

---

## 19. Specifications Summary

| Specification | Value |
|---|---|
| **Total Python Modules** | ~120+ files |
| **AI Modules** | 54 |
| **Database Tables** | 28 |
| **API Routers** | 17 |
| **Flutter Screens** | 40+ |
| **Test Files** | 90 |
| **Python Dependencies** | 108 packages |
| **Docker Services** | 7 |
| **Supported Sensors** | 5 types (pressure, motion, temp, humidity, HR/SpO2) |
| **LED Count** | 180 (120 user + 60 state) |
| **Voice Personas** | 3 (Guide, Coach, Therapist) |
| **Auth Methods** | 4 (email, phone OTP, social, session) |
| **Notification Channels** | 4 (FCM, Expo, SES email, WhatsApp) |
| **LLM Providers** | 3 (Claude, GPT, LiteLLM universal) |
| **Subscription Tiers** | 3 (Free, Standard, Pro) |
| **Target Platform** | Raspberry Pi 5 (64-bit ARM) |
| **Primary Language** | English (Arabic support for Islamic content) |
| **Target Region** | Kuwait (expandable) |
| **Min Python Version** | 3.11 |
| **Min Flutter Version** | 3.41 |
| **Database** | PostgreSQL 16 + pgvector |
| **API Port** | 8000 |
| **Default Wake Word** | "Hey Smart Bed" |

---

## 20. How to Explain This Project

### One-Liner
> "An AI-powered smart bed system with voice assistant, sleep tracking, IoT sensors, and Islamic lifestyle features — built on Raspberry Pi 5 with a Flutter mobile app."

### Elevator Pitch (30 seconds)
> "Smart Bed AI is a complete smart bed platform. It has a voice assistant named Danah that adapts her personality based on your emotions — she can be a guide, coach, or therapist. The system tracks your sleep using real sensors (heart rate, pressure, temperature), controls LED lighting scenes, and integrates with your Spotify, Fitbit, and calendar. It also has deep Islamic features — automatic prayer times, Fajr gentle-wake, Ramadan mode. Everything runs on a Raspberry Pi 5 at your bedside, with a Flutter mobile app to control it all."

### Technical Pitch (2 minutes)
> "The backend is Python/FastAPI with 54 AI modules using Claude as the primary LLM, Deepgram for STT/TTS, and PostgreSQL with pgvector for long-term memory. The voice pipeline has wake word detection, VAD, noise reduction, streaming STT, intent classification, response quality gating, and a circuit breaker for fault tolerance. Sleep intelligence uses scikit-learn for anomaly detection, statsmodels for time-series forecasting, and antropy for signal entropy sleep-depth scoring. The mobile app is Flutter with Riverpod state management, 40+ screens, and Sentry crash reporting. Infrastructure is Docker-compose with 7 services, Prometheus/Grafana monitoring, and GitHub Actions CI/CD. It runs on Raspberry Pi 5 with GPIO sensors and NeoPixel LED strips."

---

*بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ*

*"And say: My Lord, increase me in knowledge." — Quran 20:114*
