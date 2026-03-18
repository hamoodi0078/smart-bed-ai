# Dana Abuhalifa Smart Bed - Deployment Checklist

## Compile Validation (All Passed)

| Module | Files | Status |
|--------|-------|--------|
| Core (main, config, web_server, sanity_checks) | 4 | OK |
| ai/ (26 modules) | 26 | OK |
| Storage/ (4 modules) | 4 | OK |
| led/ (1 module) | 1 | OK |
| mobile_app/ (18 files) | 18 | Scaffold ready (npm install needed) |

---

## System Architecture Summary

### Bed Runtime (`main.py`)
- Wake word / keyboard input loop
- STT (local Whisper or OpenAI API)
- GPT conversation engine with personality routing
- TTS with playback controller
- LED dual-strip (user + state) WS2812 control
- Audio output manager (bed speaker + Bluetooth fallback)
- Cloud backend client with token refresh and entitlement-gated AI proxy
- Offline intent pack fallback when cloud is unavailable
- Sleep coaching: wind-down, night wake recovery, consistency, adaptive wake, stress decompression, sleep debt planner, environment intelligence, weekly insights
- Daily life support: sleep debt calculator, overthinking dump, nightmare recovery, mood-based music
- Goal system: compass, strategy engine, decomposition, missed-goal analysis
- Crisis fast protocol
- Routine scheduling with recurring days
- First-boot onboarding with sleep-specific questions
- Help-bot quick commands

### Backend Server (`web_server.py`)
- FastAPI on port 8000
- Auth: register/login with JWT tokens
- Subscription: Free / Standard / Pro tiers with PayPal checkout
- Device: provision, claim, transfer, token issuance/refresh
- Entitlements: tier-based feature flags including Spotify access
- AI proxy: /v1/ai/chat, /v1/ai/tts, /v1/ai/stt with quota enforcement
- Billing: checkout session + webhook lifecycle
- Upgrade: app + firmware version checks, OTA metadata, rollout/report
- Mobile API: dashboard, plan, usage, devices, Spotify status/control
- Admin v1.1: login, role guard, incidents, fleet devices, user timeline, audit log
- Spotify OAuth: connect, callback, token refresh, playback commands

### Storage (`Storage/`)
- `subscription_store.py` - Users, subscriptions, devices, tokens, usage, billing, admin, upgrades
- `user_profile.py` - Local JSON profile load/save
- `schedule_manager.py` - Routine scheduling with repeat days
- `cache_manager.py` - Response caching

### AI Modules (`ai/`)
- `bed_backend_client.py` - Cloud device auth, token refresh, entitlement fetch, AI chat proxy
- `conversation_engine.py` - GPT chat with personality and context
- `stt_manager.py` - Speech-to-text (local + API, auto language)
- `tts_manager.py` - Text-to-speech via OpenAI
- `spotify_manager.py` - Spotify playback API
- `audio_output_manager.py` - Bluetooth/bed speaker selection
- `audio_playback_controller.py` - pygame audio playback
- `local_music_manager.py` - Local music directory scanner + player
- `sleep_intelligence.py` - 8 sleep coaching features
- `sleep_routine_manager.py` - Sleep/wake routine management
- `daily_life_support.py` - Sleep debt, overthinking, nightmare, mood music
- `crisis_protocol.py` - Fast crisis detection and response
- `emotion_router.py` - Emotion state detection and response hints
- `environment_orchestrator.py` - Environment context orchestration
- `goal_compass.py` - Monthly goal compass
- `goal_strategy_engine.py` - Goal decomposition + missed analysis
- `personality_runtime.py` - Adaptive personality orchestrator
- `safety_guardrails.py` - Content safety evaluation
- `intent_classifier.py` - Intent classification
- `offline_intent_pack.py` - Offline command handling
- `realtime_info.py` - Real-time context (time, weather, etc.)
- `routine_engine.py` - Routine parsing and execution
- `online_calendar.py` - Calendar integration
- `session_goal_manager.py` - Session goal tracking
- `wake_word_manager.py` - Wake word detection
- `device_health.py` - Device health checks

### Mobile App (`mobile_app/`)
- Flutter (Dart, Material 3, Riverpod, GoRouter)
- Primary screens: Launch, Auth, Dashboard, Dana chat, Islamic, Timeline, Scenes, Report, Settings
- API client and state controllers in `lib/src/core` + `lib/src/state`
- Production command flows validated via `flutter analyze` + `flutter test`

---

## Pre-Deployment Checklist

Backend-only Raspberry Pi transfer reference:
- `docs/raspberry-pi-backend-only-transfer.md`

### 1. Environment Setup (Raspberry Pi)
- [ ] Flash Raspberry Pi OS (64-bit recommended)
- [ ] Install Python 3.11+
- [ ] Install system packages: `sudo apt install portaudio19-dev libatlas-base-dev`
- [ ] Clone project to `/home/pi/smart-bed/`
- [ ] Prefer `git clone/pull` for updates (avoid ad-hoc ZIP copy for production)
- [ ] Create `.env` from `.env.example` and fill in real values
- [ ] `pip install -r requirements.txt`
- [ ] Install pygame: `pip install pygame`
- [ ] Test microphone: `arecord -d 3 test.wav && aplay test.wav`
- [ ] Test speaker output
- [ ] Wire WS2812 strips to GPIO pins (default: 18 user, 13 state)

### 2. API Keys & Secrets
- [ ] OpenAI API key set in `OPENAI_API_KEY`
- [ ] Spotify app created at developer.spotify.com
- [ ] `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` set
- [ ] `SPOTIFY_REDIRECT_URI` matches Spotify app settings
- [ ] `BED_DEVICE_ID` assigned (unique per manufactured unit)
- [ ] `BED_FIRMWARE_VERSION` set to current release

### 3. Backend Server
- [ ] Deploy `web_server.py` on cloud host (e.g. VPS, Railway, Render)
- [ ] Set `APP_BACKEND_BASE_URL` on bed to point to production server
- [ ] Enable HTTPS (TLS termination via reverse proxy or platform)
- [ ] Set up persistent storage for `data/subscription_db.json` (or migrate to PostgreSQL)
- [ ] Configure CORS if mobile app accesses from different origin
- [ ] Set strong `JWT_SECRET` environment variable
- [ ] Test: `curl https://your-server/docs` (FastAPI Swagger UI)

### 4. Subscription & Billing
- [ ] Create PayPal developer account and app
- [ ] Configure PayPal webhook URL to `/v1/billing/webhook`
- [ ] Test checkout flow end-to-end (create session -> approve -> webhook)
- [ ] Verify 7-day grace period automation
- [ ] Verify tier entitlement mapping (Free/Standard/Pro)

### 5. Mobile App
- [ ] `cd mobile_app`
- [ ] `flutter pub get`
- [ ] Set API base URL via `--dart-define=SMART_BED_API_BASE_URL=https://your-host`
- [ ] `flutter analyze`
- [ ] `flutter test`
- [ ] Test all screens: Launch, Auth, Dashboard, Dana, Islamic, Timeline, Scenes, Report, Settings
- [ ] Build for Android: `flutter build apk --release` (or `flutter build appbundle`)
- [ ] Build for iOS: `flutter build ipa`
- [ ] Create Play Store / App Store listings
- [ ] Upload APK/IPA and submit for review

### 6. Bed Runtime
- [ ] Test first-boot onboarding flow
- [ ] Test voice loop: wake word -> STT -> GPT -> TTS -> playback
- [ ] Test offline fallback (disconnect internet, verify local responses)
- [ ] Test LED strips: user animations + state colors
- [ ] Test Bluetooth speaker pairing and fallback to bed speaker
- [ ] Test Spotify playback commands
- [ ] Test sleep coaching features (wind-down, adaptive wake, etc.)
- [ ] Test cloud entitlement gating (free vs. pro features)
- [ ] Set up systemd service for auto-start on boot

### 7. Admin Panel
- [ ] Create initial admin user via backend
- [ ] Test admin login and role-based access
- [ ] Verify incidents, fleet devices, user timeline, audit log endpoints
- [ ] Build admin frontend (future task - endpoints are ready)

### 8. OTA Updates
- [ ] Publish first firmware release via `/v1/admin/firmware/releases` endpoint
- [ ] Publish first app release via `/v1/admin/app/releases` endpoint
- [ ] Test update check from bed (`/v1/device/update-check`)
- [ ] Test update report from bed (`/v1/device/update-report`)

### 9. Security Hardening
- [ ] Rotate all dev/test tokens and secrets
- [ ] Enable rate limiting on auth endpoints
- [ ] Validate all user inputs on backend (already done via Pydantic)
- [ ] Audit admin role permissions
- [ ] Set up log rotation for production logs
- [ ] Consider database migration from JSON to PostgreSQL for scale

### 10. Monitoring & Operations
- [ ] Set up health check endpoint monitoring
- [ ] Configure error alerting (email/Slack)
- [ ] Set up daily backup of subscription_db.json
- [ ] Document incident response process
- [ ] Create user support FAQ from help-bot commands

---

## Systemd Service File (Bed Runtime)

```ini
[Unit]
Description=Smart Bed Runtime
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/smart-bed
EnvironmentFile=/home/pi/smart-bed/.env
ExecStart=/usr/bin/python3 main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save as `/etc/systemd/system/smart-bed.service`, then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable smart-bed
sudo systemctl start smart-bed
```

## Systemd Service File (Backend Server)

```ini
[Unit]
Description=Smart Bed Backend API
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/smart-bed
EnvironmentFile=/home/pi/smart-bed/.env
ExecStart=/usr/bin/python3 -m uvicorn web_server:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## File Inventory (35 Python + 18 App files = 53 total)

**Core**: main.py, config.py, web_server.py, sanity_checks.py
**AI**: 26 modules in ai/
**Storage**: 4 modules in Storage/
**LED**: 1 module in led/
**Mobile**: 18 files in mobile_app/
**Config**: .env.example, requirements.txt, user_profile.json

---

*Generated for Dana Abuhalifa Smart Bed v1.0 production rollout.*
