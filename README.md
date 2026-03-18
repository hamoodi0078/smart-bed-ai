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

## Raspberry Pi 5 Runtime

The backend can run on Raspberry Pi OS 64-bit while the Flutter app stays on your phone.

Quick path:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
python main.py
python -m uvicorn web_server:app --host 0.0.0.0 --port 8001
```

Pi-specific notes:
- Set `WAKE_WORD_MODE=voice`
- Set `APP_BASE_URL` and `APP_BACKEND_BASE_URL` to `http://<pi-ip>:8001`
- Enable real LED output with `LED_HARDWARE_ENABLED=1`
- Configure GPIO sensor pins with `SENSOR_PRESSURE_PIN` / `SENSOR_MOTION_PIN`
- Point the phone app at the Pi with `--dart-define=SMART_BED_API_BASE_URL=http://<pi-ip>:8001`

Full setup steps are in [`docs/raspberry-pi-setup.md`](/c:/Users/PC#####/Desktop/smart%20bed%20by%20me/docs/raspberry-pi-setup.md).

### 7) Run mobile smoke flow (manual E2E helper)
With backend running on `127.0.0.1:8001`, execute:
```powershell
.\.venv311\Scripts\python.exe .\scripts\mobile_smoke.py --base-url http://127.0.0.1:8001
```
This validates: `signup/register -> dashboard -> quick action -> scene preview -> timeline update`.

### 8) Check Day 36-45 beta exit gate (admin API)
- Endpoint: `GET /v1/admin/mobile/beta-acceptance?max_testers=5&min_required=3`
- Auth: admin session required
- Returns: scoped tester rows + blockers + `exit_gate_pass` so you can decide if the cohort is ready to move past the first 45-day window.

### 9) Track Month 2 Kuwait cohort progress (admin API)
- Enroll/update tester: `POST /v1/admin/mobile/beta-cohort/enroll`
- Cohort report: `GET /v1/admin/mobile/beta-cohort?cohort_key=kuwait_beta&target_min=10&target_max=15`
- Returns active tester counts, target-gap status, and tester-level rollout metrics.

### 10) Run one Day-45 gate command (recommended)
From repo root:
```powershell
.\.venv311\Scripts\python.exe .\scripts\day45_gate.py --base-url http://127.0.0.1:8001
```
Useful options:
- `--skip-smoke` if backend is not running yet
- `--skip-flutter` for backend-only checks
- `--flutter-cmd "C:\src\flutter\flutter\bin\flutter.bat"` if `flutter` is not on PATH

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

### VS Code Run and Debug (Windows desktop)
- Open `mobile_app` as your workspace for the cleanest Flutter debug flow.
- Use launch profile `Flutter Windows (Smart Bed)` from `mobile_app/.vscode/launch.json`.
- If you keep the repo root open, use `Flutter Windows (Smart Bed / mobile_app)` from `.vscode/launch.json`.
- Start backend first from repo root:
```powershell
.\scripts\start_backend.ps1
```

Notes:
- Android emulator defaults to `http://10.0.2.2:8001`
- iOS simulator defaults to `http://127.0.0.1:8001`
- Use `--dart-define=SMART_BED_API_BASE_URL=https://your-host` for staging or physical-device testing
- Mobile settings now include automation controls: `bedtime_drift_automation_enabled`, `quiet_hours_override_limit_minutes`, and `weekly_insight_enabled`
- Mobile automation feedback loop is live: `POST /v1/mobile/device-commands/{command_id}/feedback` and dashboard field `automation_feedback_loop`

## CI Quality Gates

GitHub Actions now blocks merges unless both lanes pass:

- `backend`: Python 3.11 dependency install + `ruff check .` + `python -m unittest discover -s tests -p "test_*.py"`
- `mobile`: Flutter 3.41.4 + `flutter pub get` + `flutter analyze` + `flutter test`

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

## Raspberry Pi 5 (Backend-Only Transfer)

For runtime-only Pi deployment (without Flutter mobile source on Pi), use:
- `docs/raspberry-pi-backend-only-transfer.md`
