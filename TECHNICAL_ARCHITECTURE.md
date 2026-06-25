# Technical Architecture Overview: Danah AbuHalifa
## A Guide for New Engineering Interns

Welcome to the engineering team! This document explains the technical architecture of the Danah Smart Bed and Bedside Assistant system. It covers the subsystems, how they communicate, data flows, and where you can start contributing.

---

## 1. System Architecture Diagram

Danah is a distributed system combining **Edge Hardware** (Raspberry Pi 5), **Cloud/Local Backend Services** (FastAPI, Postgres, Redis), and **Client Applications** (Flutter Mobile App).

```
                      ┌─────────────────────────────────┐
                      │        FLUTTER MOBILE APP       │
                      │  - Controls lights/scenes       │
                      │  - Displays sleep & prayer stats│
                      │  - Riverpod State Management    │
                      └────────────────┬────────────────┘
                                       │
                              (HTTPS / WebSockets)
                                       │
                                       ▼
                      ┌─────────────────────────────────┐
                      │       FASTAPI BACKEND API       │
                      │  - 17 Routers (Auth, Bed, etc.) │
                      │  - Sleep Intelligence Engine    │
                      │  - Islamic Mode calculation     │
                      └────────┬───────────────┬────────┘
                               │               │
                               ▼               ▼
           ┌───────────────────────┐       ┌───────────────────────┐
           │   POSTGRESQL DATABASE │       │     REDIS SERVER      │
           │  - 28 Relational Tables│       │  - Cache & Job Queue  │
           │  - pgvector for Memory│       │  - Pub/Sub Messaging  │
           └───────────────────────┘       └───────────────────────┘
                               ▲
                               │
                       (JSON over HTTP)
                               │
                               ▼
                      ┌─────────────────────────────────┐
                      │    RASPBERRY PI 5 EDGE CORE     │
                      │  - Runs Voice Assistant Agent   │
                      │  - Communicates with Sensors    │
                      │  - Drives LED Controller        │
                      └─┬──────────────┬──────────────┬─┘
                        │              │              │
                        ▼              ▼              ▼
           ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
           │  LED STRIPS    │ │ PHYSICAL SENSORS│ │ AUDIO HARDWARE │
           │ - WS2812B      │ │ - Pressure Pad │ │ - USB Microphone│
           │ - User strip   │ │ - Temperature  │ │ - Audio Speaker│
           │ - State strip  │ │ - Heart Rate   │ │ (Wake word/TTS)│
           └────────────────┘ └────────────────┘ └────────────────┘
```

---

## 2. Subsystems Breakdown

### A. Mobile Application (Flutter)
*   **What it does:** The primary user interface. It allows users to register accounts, view sleep score charts, configure smart alarms, preview LED lighting scenes, and access Islamic lifestyle settings.
*   **Key Tech:** Flutter (Dart) for cross-platform support (Android, iOS, Windows), and Riverpod for app state management.
*   **How it interacts:** Polls the backend API endpoint `/v1/bed/state` every 2–5 seconds to show real-time changes on the dashboard and sends command requests (like changing an LED color scene) to `/v1/mobile/device-commands`.

### B. Backend API Server (FastAPI)
*   **What it does:** The central brain of the application. It manages user authentication, aggregates sensor data, calculates sleep quality scores, computes prayer times, and routes instructions between the mobile app and the physical bed.
*   **Key Tech:** Python 3.11, FastAPI (web server framework), SQLAlchemy (ORM), and Uvicorn.
*   **How it interacts:** Receives requests from the mobile app and Raspberry Pi, stores/retrieves persistent data in PostgreSQL, and queues background tasks (like generating weekly sleep reports) in Redis.

### C. Database & Caching Layer
*   **PostgreSQL:** Stores user accounts, bed pairings, historical sleep sessions, alarms, and conversations. It uses the `pgvector` extension to save vector embeddings of the user's past conversations, enabling Danah to search and "remember" facts about the user.
*   **Redis:** Acts as a rapid message broker and background task manager (`arq` job worker). It cache-stores session tokens and tracks immediate system statuses.

### D. Raspberry Pi 5 Edge Hardware
*   **What it does:** The physical hardware controller situated at the bedside. It interfaces with the sensors and lights, and runs the voice capture pipeline.
*   **Physical Sensors:**
    *   *Pressure Pads:* Placed under the mattress to detect if the user is in bed and measure restlessness.
    *   *AM2301A/DHT22:* Measures ambient bedroom temperature and humidity.
    *   *MAX30102:* Placed on the bedside or bed frame to monitor heart rate (BPM) and blood oxygen levels (SpO2).
*   **LED Controller:**
    *   Drives the WS2812B NeoPixel strips (120 LEDs for ambient user lighting, 60 LEDs for state indicators). It runs at 20 FPS to provide smooth light animations (like simulating sunset or a gentle morning sunrise).
*   **Voice Pipeline:**
    *   Combines local Wake Word Detection ("Hey Smart Bed"), Voice Activity Detection (VAD) to filter background noise, Speech-to-Text (STT via Deepgram), LLM orchestration (Claude/GPT), and Text-to-Speech (TTS via Deepgram Aura-2) to play Danah's response through the bedside speakers.

---

## 3. Core Data Flows

### Flow A: Voice Interaction (Saying "Hey Smart Bed, I'm stressed")
1.  The Pi's microphone continuously listens locally. It detects the **Wake Word** ("Hey Smart Bed").
2.  **Voice Activity Detection (VAD)** filters out background noise and streams the user's spoken audio ("I'm stressed") to the **Speech-to-Text (STT)** engine.
3.  The converted text is sent to the backend **AI Conversation Engine**.
4.  The **Emotion Router** detects that the user is stressed.
5.  The system switches Danah's active personality to **Therapist** (which uses a gentle, empathetic voice tone).
6.  The backend looks up the user's history in **PostgreSQL Vector Memory** for context, queries the LLM for a supportive response, and formats it.
7.  The text response is sent to **Text-to-Speech (TTS)** to generate audio.
8.  The audio is streamed back to the Pi's speaker, while a command is sent to the LED strip to glow in a soft, calming color.

### Flow B: Sensor Data Reporting
1.  Every few seconds, the Python scripts running on the Raspberry Pi read raw values from the **GPIO pins** (pressure pad state) and **I2C interface** (temperature and heart rate).
2.  The Pi packs these values into a JSON payload and sends an HTTP POST request to the backend API (`/v1/bed/state-update`).
3.  The backend saves the raw data, runs sleep analytics logic (detecting restlessness or bed entry/exit), and updates the cached bed state.
4.  The Flutter mobile app, polling `/v1/bed/state`, receives the updated state and updates the dashboard widgets (e.g., showing a "Sleep Restfulness" indicator or a "Bed Occupied" badge) in real-time.

---

## 4. Codebase Directory Map

When you open the project, keep this file mapping in mind:
*   [ai/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/ai/) — Contains the core logic for conversation, memory, sleep analysis, and LLM routers.
*   [api/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/api/) — Contains the FastAPI route endpoints (split into auth, devices, sleep, admin, and chat).
*   [database/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/database/) — Database tables (SQLAlchemy models) and connection handlers.
*   [hardware/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/hardware/) — Raspberry Pi drivers for LED strips (`pi_led.py`), temperature (`pi_temperature.py`), and heart rate (`pi_heart_rate.py`).
*   [islamic_mode/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/islamic_mode/) — Prayer calculations, Ramadan mode logic, and prayer automation engines.
*   [mobile_app/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/mobile_app/) — The Flutter codebase containing screens and state managers.
*   [tests/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/tests/) — Unit and integration tests (using pytest).

---

## 5. Where New Interns Can Contribute

Here are excellent, high-impact tasks designed specifically for new interns:

### 1. Refactor API Endpoints (Backend focus)
*   **The Task:** Currently, some of our APIs are grouped in a large [web_server.py](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/web_server.py) monolith.
*   **How you help:** Help move routes (such as user settings or custom configurations) into separate routers under the [api/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/api/) folder to keep the codebase modular.

### 2. Sensor Noise Filtering (Hardware & IoT focus)
*   **The Task:** Raw data from physical sensors (especially the heart rate monitor and pressure pads) can be noisy or report false spikes.
*   **How you help:** Write signal processing utilities (like moving average filters or threshold algorithms) to clean up sensor readings in [hardware/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/hardware/) before they are sent to the backend.

### 3. Build Dashboard Widgets (Mobile focus)
*   **The Task:** The Flutter app needs to render the newly added real-time parameters from the bed.
*   **How you help:** Design and implement elegant widgets in [mobile_app/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/mobile_app/) to show room humidity, active AI personality icons, and circadian LED status.

### 4. Write Unit & Integration Tests (Quality Assurance focus)
*   **The Task:** We want to raise our total test coverage to 80%+.
*   **How you help:** Write test cases in [tests/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/tests/) for individual modules like `prayer_times.py`, `sleep_score.py`, or API router validation checks. It's a great way to learn how the codebase works!

**Honest answer: Not yet.** Your architecture is well-designed in *concept*, but there are 5 concrete blockers that will break at specific user thresholds. Here's the reality:

---

### 🚦 Where It Breaks (in order)

| Bottleneck | Breaks At | Why |
|---|---|---|
| **JSON file stores** | ~100 concurrent users | [subscription_store.py](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/Storage/subscription_store.py) (82K!) persists ALL billing data in a single JSON file with file locks. No ACID, no backup, serialized writes. |
| **In-memory rate limiter** | ~4 Gunicorn workers | [rate_limiter.py](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/api/middleware/rate_limiter.py) stores token buckets in process memory — each worker has independent counters, so limits multiply by worker count |
| **Sync DB in async handlers** | ~500 concurrent requests | [web_server.py](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/web_server.py) uses sync `DatabaseConnection.get_session()` inside async FastAPI handlers — blocks the event loop on every DB call |
| **In-memory chat history** | ~200 users per worker | `_CHAT_ENGINES` dict capped at 200 entries, history lost on restart, different per worker |
| **Thread-based profile lock** | Multiple workers | `_PROFILE_RW_LOCK` in web_server.py serializes all profile writes within one process — useless across workers |

---

### ✅ What's Already Scalable

The good news — your *foundations* are solid:

- **Database layer** — PostgreSQL + async pool + SQLAlchemy 2.0 repository pattern. This scales well.
- **Docker Compose** — 7 services with health checks, resource limits, and proper dependency ordering. Ready for Kubernetes migration.
- **AI engines** — Circuit breaker, fallback chains, multi-provider (Deepgram → Claude → LiteLLM). Graceful degradation works.
- **Auth** — JWT + token revocation in DB. Stateless auth scales horizontally.

---

### 🔧 The Fix Is Closer Than You Think

The ironic part: **you already built the PostgreSQL models for everything** — you just aren't using them for the critical paths yet.

| What Exists | What's Still Used Instead |
|---|---|
| `SubscriptionRecord` model in [models.py:347](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/database/models.py#L347) | JSON file in `subscription_store.py` |
| `AsyncDatabaseConnection` in [connection.py](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/database/connection.py) | Sync `DatabaseConnection` in web_server.py |
| `api/routers/` (20 clean routers) | Still lazy-importing from the 10K-line `web_server.py` |
| Redis already in docker-compose | Rate limiter uses in-memory dict |

---

### 📊 Bottom Line

| Scale | Will It Work? | What Breaks |
|---|---|---|
| **1-50 users** (beta) | ✅ Yes | Nothing — works fine |
| **100-500 users** | ⚠️ Fragile | JSON file locks contend, profile writes slow down |
| **1,000+ users** | ❌ No | Event loop blocking, rate limits useless, chat history lost between restarts |
| **10,000+ users** | ❌ No | Need async DB everywhere, Redis-backed state, subscription migration |

**To make it scale to 10K+, you need ~5 changes** (all medium effort since the infrastructure already exists):
1. Migrate `subscription_store.py` → PostgreSQL
2. Move rate limiter state → Redis  
3. Switch sync → async DB sessions in API routes
4. Store chat history in Redis
5. Run only `app_factory.py` (kill the duplicate web_server.py FastAPI instance)

Your project has good bones — it's an architecture problem, not a rewrite.

Your **#1 cost problem** is voice AI. Here's the breakdown and what to do about it:

---

### 💸 Where Your Money Goes

At 10K users, your projected ~$29.5K/month splits like this:

```
Deepgram TTS (text-to-speech)  ████████████████████████████  $16,875  (57%)
Deepgram STT (speech-to-text)  ██████████████████            $10,800  (37%)
OpenAI GPT-4o-mini             ██                            $1,560   (5%)
Everything else                ▏                             $320     (1%)
```

**Voice is 94% of your bill.** Everything else is a rounding error.

---

### 🔧 5 Changes, Ranked by Impact

#### 1. Client-Side TTS for Mobile App — saves ~$13K/mo at 10K users
Your Flutter app doesn't need Deepgram TTS. Both iOS and Android have free built-in TTS engines.

```dart
// Flutter — free, runs on device, zero latency
import 'package:flutter_tts/flutter_tts.dart';
FlutterTts tts = FlutterTts();
await tts.speak(response.text); // FREE
```

Keep Deepgram TTS **only** for the physical bed speaker (Raspberry Pi). That alone eliminates ~80% of TTS calls since most users interact via the app.

#### 2. Local Whisper for Simple Commands — saves ~$7K/mo at 10K users
You already have `faster-whisper` in your [requirements.txt](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/requirements.txt) and `stt_mode` in [settings.py](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/config/settings.py). Use a **tiered approach**:

| Command Type | STT Engine | Cost |
|---|---|---|
| "Turn off lights", "Play music", "Set alarm" | Local Whisper (tiny model) | **$0** |
| Conversational / emotional / complex | Deepgram Nova-2 | $0.0043/min |

The [OfflineIntentPack](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/ai/offline_intent_pack.py) already handles local intent matching — pair it with local STT for a fully offline fast-path.

#### 3. Cache Common AI Responses in Redis — saves ~$500/mo at 10K users
Your [CacheManager](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/Storage/cache_manager.py) exists but **isn't used for AI responses**. Many queries repeat daily:

```python
# In conversation_engine.py — add before every LLM call
cache_key = f"ai:{user_id}:{hash(normalized_query)}"
cached = await redis.get(cache_key)
if cached:
    return cached  # Skip $0.002 API call

# After getting response:
await redis.setex(cache_key, 300, response)  # 5-min TTL
```

Cacheable queries: "What time is it?", "How did I sleep?", "What's the weather?", prayer times, sleep scores. Roughly 30-50% of all queries.

#### 4. Shrink System Prompts — saves ~$300/mo at 10K users
In [conversation_engine.py:289-342](file:///c:/Users/PC%23%23%23%23%23/Desktop/smart%20bed%20by%20me/ai/conversation_engine.py#L289-L342), every single turn sends **8-9 system messages** (~800 tokens of overhead). Merge them into one:

| Now | After |
|---|---|
| 8 separate system messages (persona, temporal, engagement, method, arc, mood, cognitive, context) | 1 combined system prompt with sections |
| ~800 tokens fixed overhead per call | ~400 tokens |
| No prompt caching on OpenAI (different message structure each time) | Stable prefix enables caching |

You're already doing this correctly for Claude (prompt caching at line 519), but **not for OpenAI calls**.

#### 5. Per-User Daily Limits — prevents cost spikes

No limits exist today. A single power user could make 500 AI calls/day. Add tier-based caps:

| Tier | Daily AI Calls | Daily Voice Minutes |
|---|---|---|
| Free | 15 | 5 |
| Standard ($4.99/mo) | 75 | 30 |
| Pro ($9.99/mo) | Unlimited | 120 |

This doesn't save money on average — it **caps your worst case** so one user can't run up a $200/day bill.

---

### 📊 Total Impact

| Optimization | Monthly Savings (10K users) | Effort |
|---|---|---|
| Client-side TTS for mobile | **~$13,500** | Medium |
| Local Whisper for simple commands | **~$7,500** | Medium |
| Redis response caching | **~$500** | Small |
| Shrink system prompts | **~$300** | Small |
| Per-user limits | **Bounds worst case** | Small |
| **TOTAL** | **~$21,800** (74% reduction) | |

That takes your 10K-user bill from **~$29.5K/month → ~$7.7K/month**.

---

### 🎯 If You Only Do One Thing

**Do #1 — client-side TTS for mobile.** It's the single biggest win, it improves latency (no network round-trip), and it works offline. The bed's Pi speaker still gets Deepgram's premium voice quality where it matters.