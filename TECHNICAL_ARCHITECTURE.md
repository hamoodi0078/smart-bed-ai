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
