# Smart Bed AI Runtime

Production-ready backend runtime for the Smart Bed voice assistant, with realtime voice flow, adaptive personality, long-term memory, and web/mobile bridge APIs.

## Developer Quick Start (App Development Phase)

### 1) Prerequisites
- Python 3.11+
- Windows PowerShell
- `.env` configured (at minimum `DEEPGRAM_API_KEY`)

### 2) Install dependencies
```powershell
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3) Configure environment
Copy and edit:
- `.env.example` -> `.env`

Important keys:
- `DEEPGRAM_API_KEY` (required for STT, TTS, and Voice Agent conversation)
- `DEEPGRAM_VOICE_AGENT_MODEL` (LLM/agent model id)
- `DEEPGRAM_VOICE_AGENT_URL` (Voice Agent endpoint)
- `WAKE_WORD_MODE` (`keyboard` for desktop testing, voice mode on device)
- `APP_BASE_URL` / `APP_BACKEND_BASE_URL` if web/mobile clients are external

### 4) Start backend
Preferred script flow:
```powershell
.\scripts\start_backend.ps1
```
Alternative:
```powershell
python main.py
```

### 5) Start web runtime API
```powershell
python -m uvicorn web_server:app --host 127.0.0.1 --port 8001 --reload
```

### 6) Validate core health
- `GET /healthz` -> should return `{"ok": true, "service": "web_runtime"}`
- Run test gate:
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Flutter Mobile Shell

The primary customer surface is now the Flutter app in [`mobile_app/`](/c:/Users/PC#####/Desktop/smart%20bed%20by%20me/mobile_app).

### Mobile quick start
```powershell
cd mobile_app
flutter pub get
flutter analyze
flutter test
flutter run --dart-define=SMART_BED_API_BASE_URL=http://10.0.2.2:8001
```

Notes:
- Android emulator defaults to `http://10.0.2.2:8001`
- iOS simulator defaults to `http://127.0.0.1:8001`
- Use `--dart-define=SMART_BED_API_BASE_URL=https://your-host` for staging or physical-device testing

## New Unified State Bridge API

### `GET /v1/bed/state`
Unified state snapshot for website/mobile clients to render the AI and device runtime in near realtime.

**Auth:** user or admin session cookie required.

**Response shape:**
```json
{
  "ok": true,
  "generated_at": "2026-02-24T18:40:00+00:00",
  "emotion_state": "neutral",
  "active_personality": "guide",
  "last_memory_context": "Last memory turn: user='...'; ...",
  "biometric_summary": {
    "recovery_mode": false,
    "challenge_level": 1,
    "night_wake_count": 0,
    "bedtime_samples": 12,
    "wake_samples": 12,
    "partner_mode_enabled": false,
    "last_bedtime_drift_alert_date": ""
  },
  "device_health_status": {
    "deepgram_configured": true,
    "spotify_connected_users": 1,
    "led": {
      "user_strip_pin": 18,
      "state_strip_pin": 13,
      "user_strip_led_count": 120,
      "state_strip_led_count": 60
    },
    "last_scene_key": "balanced_default",
    "last_preload_phase": "sleep",
    "sensor_pressure_active": false,
    "sensor_motion_active": false
  }
}
```

## App Integration Notes

- Poll `/v1/bed/state` every 2-5 seconds for live dashboard state.
- Use `emotion_state + active_personality + last_memory_context` for conversational UI continuity.
- Use `device_health_status` to surface setup diagnostics and LED/device telemetry.
- Use `biometric_summary` for sleep widgets and adaptive coaching cards.

## Final System Check Scope

`tests/final_system_check.py` simulates:
1. User speech (STT)
2. LLM streaming response
3. Parallel TTS pipeline playback
4. Memory persistence

This is the baseline release check before onboarding new pilot customers.
