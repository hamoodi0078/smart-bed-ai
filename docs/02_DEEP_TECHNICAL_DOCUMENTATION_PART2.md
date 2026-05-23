# Smart Bed AI — Deep Technical Documentation (Part 2)

> Continued from Part 1. Covers Islamic Mode, Database, API, Auth, Automations,
> Notifications, Billing, Integrations, Mobile App, Errors, Monitoring, Deployment, Testing.

---

## 8. Islamic Mode — Every Feature (`islamic_mode/`, 14 files)

**prayer_times.py (17KB):** Calculates 5 daily prayers + sunrise/sunset. Method 8 (Kuwait). Caches offline. Auto-adjusts for DST. GPS or manual location.

**prayer_automation.py (14.6KB):** Fajr gentle-light wake (LED brightness increases 20 min before). Adhan push notification per prayer. Auto-quiet during prayer window. Returns to previous state after.

**ramadan_mode.py (15.2KB):** Suhoor wake alarm. Iftar countdown timer. Reduced AI during fasting hours. Hijri date aware. Taraweeh reminder.

**tahajjud_manager.py (11.9KB):** Calculates last third of night. Soft alarm + light. Tracks consistency. Encouragement messages.

**hadith_daily.py (18.1KB):** One Hadith per day. Arabic text with proper reshaping (RTL). Multiple collections. Voice + push delivery.

**islamic_calendar.py (7.5KB):** Gregorian ↔ Hijri offline conversion. Knows Islamic holidays. Adjusts behavior for special periods.

**sunnah_tips.py (4.6KB):** Daily Sunnah tips about sleep and health. Example: "Sleeping on your right side is Sunnah."

**islamic_api.py (16.7KB):** REST API: `GET /v1/islamic/prayer-times`, `GET /v1/islamic/hadith/today`, `POST /v1/islamic/ramadan/toggle`.

**dana_islamic_voice.py (2.1KB):** Adds "Assalamu Alaikum", Arabic phrases, respectful tone during prayer contexts.

**geolocation.py (4.2KB):** Auto-detect location for prayers. IP-based fallback. Manual override.

---

## 9. Database — All 28 Tables

**Engine:** PostgreSQL 16 + pgvector. SQLAlchemy 2.0 (sync + async). Alembic migrations.
**Pools:** Sync (psycopg2): 10 connections, 20 overflow. Async (asyncpg): 2 min, 10 max.

### User & Auth Tables

**`users`** — id (UUID), email (unique), password_hash (bcrypt), role (user/admin/superadmin), subscription_status, timezone, locale, is_active, last_login, created_at.

**`refresh_tokens`** — id, user_id (FK), token (unique), expires_at, revoked (boolean), created_at. Old tokens are revoked on refresh.

**`mobile_auth_sessions`** — id, user_id (FK), access_token, refresh_token, client_name (iOS/Android), created_at. Tracks active app sessions.

**`user_social_identities`** — id, user_id (FK), provider (google/apple/facebook), provider_user_id, email, created_at. Links social login accounts.

**`user_phone_auth`** — id, phone_number, user_id (FK). Maps phone to user for OTP login.

**`otp_requests`** — request_id, phone_number, otp_digest (hashed OTP), attempts (max 3), expires_at, verified (boolean). One-time passwords.

### Device Tables

**`beds`** — id, device_id (unique), primary_user_id (FK), partner_user_id (FK, nullable), firmware_version, is_online, last_seen, created_at.

### Sleep & Health Tables

**`sleep_sessions`** — id, user_id (FK), date (unique per user), bedtime, wake_time, total_sleep_minutes, restlessness_score (0-100), sleep_score, scenes_used (JSON), notes, created_at.

**`alarms`** — id, user_id (FK), label, time (HH:MM), days_of_week (JSON array like ["mon","tue"]), wake_style (gentle/balanced/energetic), smart_window_minutes (0-30), enabled, created_at.

**`user_routines`** — id, user_id (FK), bedtime, wake_time, weekend_bedtime, weekend_wake_time, wind_down_minutes.

### AI & Memory Tables

**`user_memory_entries`** — id, user_id (FK), user_text (what user said), assistant_text (what Danah replied), emotion (detected emotion), personality (guide/coach/therapist), created_at. This is the long-term memory.

**`user_daily_events`** — id, user_id (FK), date, title, summary, stress_level (1-10), source (manual/calendar/fitbit), created_at.

### Scene & Event Tables

**`scene_records`** — id, user_id (FK), name, config (JSON: colors, brightness, animation), is_premium (boolean), category, usage_count, created_at.

**`events`** — id, user_id (FK), bed_id (FK), event_type (string), metadata (JSON), trace_id (for debugging), created_at, index on user_id+timestamp.

### Mobile App Tables

**`mobile_command_records`** — id, user_id, command_id, action, status (pending/completed/failed), created_at.

**`mobile_command_feedback`** — id, user_id, command_id, vote (thumbs up/down), note (text).

**`first_three_nights_progress`** — user_id, signup_completed_at, first_scene_at, first_automation_at, first_winddown_at. Onboarding milestones.

**`nightly_summary_feedback_progress`** — user_id, helpful_count, not_helpful_count. Tracks if nightly summaries are useful.

### Subscription Table

**`subscription_records`** — id, user_id (FK), tier (free/standard/pro), status (active/cancelled/expired), payment_provider (paypal), price_kwd, start_date, end_date, auto_renew.

### Notification Table

**`user_push_tokens`** — id, user_id (FK), expo_token or fcm_token, platform (ios/android/web), created_at.

### Preference Table

**`user_profile_prefs`** — id, user_id (FK), display_name, timezone, theme_mode (light/dark/system), locale, push_enabled, email_enabled, settings_json (extra preferences), location_lat, location_lon.

### Version Tables

**`app_versions`** — id, platform (ios/android), version_string, changelog, is_required (forced update), rollout_percent (gradual rollout), released_at.

**`firmware_versions`** — id, version_string, download_url, is_required, target_device_ids (JSON), released_at.

### Feature Flag Tables

**`feature_flags`** — id, flag_key (unique), enabled_globally (boolean), enabled_for_plans (JSON: ["pro", "standard"]), rollout_percent (0-100), description.

**`user_feature_overrides`** — id, user_id (FK), flag_key, override_value (boolean). Enable beta features for specific users.

### Beta Tables

**`beta_metrics_snapshots`** — id, user_id, activation_progress (JSON), command_count, error_count, created_at.

**`beta_cohort_members`** — id, cohort_key ("kuwait_beta"), user_id, country_code, status (active/graduated/dropped).

### Music Table

**`spotify_tokens`** — id, user_key, access_token, refresh_token, spotify_user_id, expires_at.

### Repository Layer

**`database/repositories.py` (92.9KB)** — Contains async CRUD functions for ALL 28 tables. Uses SQLAlchemy async sessions. Every database operation goes through this layer.

---

## 10. API — All 17 Routers

| Router | File | Size | Endpoints |
|---|---|---|---|
| Auth | `auth.py` | 19.6KB | register, login, refresh, logout, OTP request/verify, social auth |
| Admin | `admin.py` | 10.1KB | User mgmt, beta cohort enroll/report, diagnostics |
| Alarms | `alarms.py` | 5.8KB | CRUD alarms with smart wake window |
| Devices | `devices.py` | 5.7KB | Bed state, LED control, sensor readings |
| Profile | `profile.py` | 5.3KB | User profile, preferences, routines |
| Subscriptions | `subscriptions.py` | 4.3KB | Status, subscribe, cancel |
| Sleep | `sleep.py` | 3.9KB | Sessions list, stats, record session |
| Islamic | `islamic.py` | 3KB | Prayer times, daily Hadith, Ramadan toggle |
| Integrations | `integrations.py` | 2.7KB | Fitbit/Garmin/Calendar connections |
| Health | `health.py` | 2.5KB | `/healthz` liveness, `/healthz/detailed` full check |
| Spotify | `spotify.py` | 1.9KB | OAuth flow, playback control |
| Scenes | `scenes.py` | 1.8KB | List, activate scenes |
| Chat | `chat.py` | 1.5KB | AI chat (SSE streaming + WebSocket) |
| Metrics | `metrics.py` | 1.5KB | Prometheus `/metrics` |
| Reports | `reports.py` | 1.2KB | Weekly report generation |
| Automations | `automations.py` | 1.1KB | Automation rules |
| Automation Routes | `automation_routes.py` | 27.8KB | Detailed automation management |

### Legacy Server (`web_server.py` — 397KB / 10,307 lines)
This is a large monolith file containing many routes that haven't been migrated to dedicated routers yet. It handles scenes, automations, profiles, sleep, undo, and more via the original FastAPI app. The action plan calls for migrating these into the router system above.

---

## 11. Authentication — Full Flow

### How Registration Works
1. `POST /v1/auth/register` with email + password
2. Password validated (min 8 chars, numbers + special chars)
3. Password hashed: bcrypt with 12 salt rounds
4. User created with role `user`
5. JWT access token (HS256) generated — expires 15-60 min
6. Refresh token generated — expires 7-30 days
7. Both returned to client

### How Login Works
1. `POST /v1/auth/login` with email + password
2. Email looked up (case-insensitive)
3. bcrypt.checkpw() verifies password
4. `last_login` updated
5. New tokens generated and returned

### How Token Refresh Works
1. Client sends refresh token to `POST /v1/auth/refresh`
2. Token looked up in `refresh_tokens` table
3. Must be: valid, not revoked, not expired
4. Old refresh token is **revoked** (one-time use — prevents replay attacks)
5. New access + refresh tokens generated
6. Returned to client

### Role-Based Access Control (RBAC)
Three roles with increasing permissions:

| Role | Can Do |
|---|---|
| `user` | Use all user features, manage own profile |
| `admin` | Everything user can + manage other users, view beta cohorts |
| `superadmin` | Everything admin can + system config, feature flags, dangerous operations |

### Phone OTP Authentication
1. `POST /v1/auth/otp/request` with phone number
2. 6-digit OTP generated and hashed (SHA-256)
3. Sent to phone via SMS
4. User submits OTP to `POST /v1/auth/otp/verify`
5. Hash compared, attempts tracked (max 3)
6. On success → user logged in with JWT tokens

### Social Authentication
1. Client gets OAuth token from Google/Apple/Facebook
2. Sends to `POST /v1/auth/social`
3. Backend verifies token with the provider
4. Extracts verified email
5. Creates or links user account
6. Returns JWT tokens

### Security Layers
- **bcrypt 12 rounds** — takes ~250ms to hash (prevents brute force)
- **Token rotation** — refresh tokens are single-use
- **Token blacklisting** — revoked tokens stored in DB
- **Rate limiting** — 5 login attempts/min, 3 register/hour, 3 OTP/10min
- **CORS** — only allowed origins can call the API
- **HTTPS-only** in production — CORS rejects non-HTTPS origins
- **Input validation** — all request bodies validated via Pydantic
- **Secret audit** — startup checks for weak/default secrets

---

## 12. Error Handling (`core/errors.py` — 146 lines)

### Error Code System

Every API error has a code, message, HTTP status, and trace ID:

| Error Code | HTTP Status | When It Happens |
|---|---|---|
| `DEVICE_OFFLINE` | 503 | Bed device is unreachable |
| `UNAUTHORIZED` | 401 | Invalid or missing JWT token |
| `FORBIDDEN` | 403 | User doesn't have required role |
| `RATE_LIMITED` | 429 | Too many requests |
| `VALIDATION_ERROR` | 422 | Bad request data |
| `NOT_FOUND` | 404 | Resource doesn't exist |
| `INVALID_SCENE_CONFIG` | 422 | Scene has invalid settings |
| `TRIAL_ALREADY_USED` | 409 | User already used free trial |
| `SUBSCRIPTION_REQUIRED` | 402 | Premium feature, no subscription |
| `DEVICE_BUSY` | 409 | Device is processing another command |
| `TIMEOUT` | 504 | Operation timed out |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### Exception Hierarchy

```
BedError (base)
├── DeviceOfflineError
├── AuthorizationError
├── SubscriptionRequiredError
├── VoiceProcessingError
└── ConfigurationError
```

Every error response includes a `trace_id` header for debugging.

---

## 13. Automation Engine

### Core Components

**`automation_engine.py` (9KB)** — Main scheduler using APScheduler + croniter. Runs automations at configured times.

**`automations/registry.py` (13.3KB)** — Stores automation rules. Evaluates conditions. Manages enable/disable.

**`automations/idempotency.py` (4.5KB)** — Prevents duplicate firing. If an automation already ran today, it won't run again.

**`automations/defaults.py` (16.3KB)** — All built-in automations:

| Automation | Trigger | Action |
|---|---|---|
| Bedtime Reminder | bedtime - 30min | Push notification + light shift |
| Smart Wake | Optimal wake time | Gradual light + gentle audio |
| Bedtime Drift Alert | >30min bedtime variance | Warning notification |
| Wind-Down Start | bedtime - 45min | Dim lights, reduce stimulation |
| Morning Brief | After wake detected | Weather + schedule + sleep score |
| Evening Brief | Evening window | Day summary + tomorrow prep |
| Quiet Hours | 22:00-07:00 | Mute notifications, dim LED |

**`automations/islamic_automations.py` (7.5KB)** — Prayer-based automations:

| Automation | Action |
|---|---|
| Fajr Wake | Gentle light 20 min before Fajr |
| Prayer Reminder | Push notification per prayer |
| Tahajjud | Soft wake in last third of night |
| Suhoor (Ramadan) | Pre-dawn meal alarm |
| Iftar Countdown | Timer to Maghrib |

**`automations/bathroom_automation.py` (7.6KB)** — Pressure sensor detects bed exit → dim pathway lights on → detects return → lights off.

**`ai/automation_learning_engine.py` (13KB)** — Learns from behavior. Adjusts timing. Suggests new automations. Disables ignored ones.

**`ai/proactive_automation_engine.py` (7.5KB)** — Anticipates needs before user asks. "You usually dim lights at 10 PM. Should I?"

---

## 14. Notification System

### Channels

| Channel | Module | Provider |
|---|---|---|
| Push (Android/iOS) | `fcm_sender.py` (13.8KB) | Google Firebase Cloud Messaging |
| Push (Expo) | `expo_sender.py` (6.9KB) | Expo Push Service |
| Email | `ses_sender.py` (6.3KB) + `email_service.py` (7.7KB) | AWS SES |
| WhatsApp | `whatsapp_notifier.py` (2.3KB) | WhatsApp Business API |

### Features

**notification_scheduler.py (5.6KB)** — Cron-based scheduling. "Send prayer reminder at each prayer time."

**notification_types.py (2.3KB)** — Typed categories: sleep_reminder, prayer_time, alarm, system_alert, achievement.

**summaries.py (6.1KB)** — Digest notifications. Instead of 5 separate notifications, sends one summary.

**reengagement_campaigns.py (11.7KB)** — If user stops using the app:
- Day 3: "We miss you! Your sleep tracking is paused."
- Day 7: "Your sleep streak was 14 nights. Come back to continue."
- Day 14: "Try our new wind-down feature."

---

## 15. Subscription & Billing (`subscriptions/`)

### Tiers

| Tier | What You Get |
|---|---|
| **Free** | Basic sleep tracking, 1 alarm, 3 default scenes, AI chat (limited) |
| **Standard** | Full analytics, unlimited alarms, all scenes, Spotify, weekly reports |
| **Pro** | Everything + Islamic features, partner mode, advanced AI, dream journal, priority support |

### Modules

**billing.py (29.5KB)** — Core billing logic. Creates/updates/cancels subscriptions. Handles plan changes.

**paypal_provider.py (10.8KB)** — PayPal subscription integration:
- Sandbox and production modes
- Creates subscription via PayPal API
- Webhook verification (validates PayPal signature)
- Handles: BILLING.SUBSCRIPTION.ACTIVATED, CANCELLED, SUSPENDED, PAYMENT.FAILED
- Plan IDs configured per environment

**gate.py (3.2KB)** — Feature gating. Before any premium feature, checks: `is_feature_allowed(user, feature)`. Returns True/False.

**trial_automation.py (9.7KB)** — Free trial management:
- 7-day trial for new users
- Sends reminder at day 5: "Your trial ends in 2 days"
- Converts to paid or downgrades to free

---

## 16. Third-Party Integrations (`integrations/`)

| Integration | Module | Size | What It Does |
|---|---|---|---|
| Fitbit | `fitbit_client.py` | 16.4KB | Pulls sleep stages, heart rate, SpO2, steps via OAuth |
| Garmin | `garmin_client.py` | 13.8KB | Pulls sleep, HRV, body battery, steps via OAuth |
| Google Calendar | `google_calendar_client.py` | 6.2KB | Fetches events for schedule-aware automations |
| Calendar Sync | `calendar_sync.py` | 12KB | Unified calendar from multiple sources |
| Fitness API | `fitness_tracker_api.py` | 15.8KB | Unified fitness data REST API |
| Smart Home | `smart_home.py` | 30.8KB | Controls third-party devices (lights, plugs, etc.) |
| MQTT | `mqtt_client.py` | 11.7KB | IoT messaging protocol for device communication |
| Zigbee | `zigbee_coordinator.py` | 12.1KB | Zigbee device coordination (Phillips Hue, etc.) |
| Geofence | `geofence_manager.py` | 8.9KB | Location-based automations (near home → prepare bed) |

---

## 17. Mobile App — Screen by Screen

### Entry Point (`main.dart`, 57 lines)
- Initializes Flutter, local notifications, journal storage
- Sentry crash reporting (required in production via `--dart-define SENTRY_DSN`)
- Riverpod state management with initial theme + onboarding state
- Root widget: `SmartBedApp`

### Main Screens (19 refactored screens in `src/ui/screens/`)

| Screen | Size | What The User Sees |
|---|---|---|
| **dashboard_screen** | 21.4KB | Home: sleep score, quick actions, sensor readings, today's summary |
| **auth_screen** | 20.1KB | Login form, register form, social login buttons, phone OTP |
| **settings_screen** | 52.2KB | Everything: bed config, notifications, Islamic settings, automation rules, profile, subscription |
| **bed_controls_screen** | 14.8KB | LED color picker, brightness slider, scene buttons, manual commands |
| **alarm_screen** | 13.2KB | Alarm list, create/edit alarm, wake style picker, smart window toggle |
| **connect_bed_screen** | 12.8KB | Device discovery, QR code scan, pairing flow |
| **islamic_screen** | 12.7KB | Prayer times list, next prayer countdown, Hadith card, Ramadan toggle |
| **dana_chat_screen** | 12.1KB | Chat bubble UI, send message, see AI response, personality indicator |
| **report_screen** | 11.9KB | Weekly report view, charts, trend graphs, PDF download |
| **spotify_screen** | 11.3KB | Spotify login, now playing, playlist browser, sleep playlist |
| **bed_viewer_screen** | 11KB | 3D visualization of the bed with sensor indicators |
| **timeline_screen** | 10.8KB | Activity feed: events, automations, commands in chronological order |
| **scenes_screen** | 10.7KB | Scene cards, preview colors, activate, create custom |
| **subscription_screen** | 9.2KB | Plan comparison table, pricing, subscribe button |
| **onboarding_screen** | 7.9KB | First-time flow: welcome, features overview, permissions, setup |
| **profile_screen** | 7.2KB | Name, email, timezone, avatar, sleep goals |
| **launch_screen** | 5.7KB | Splash screen with logo while app loads |
| **about_screen** | 4.7KB | App info, version, credits, licenses |
| **home_shell** | 3KB | Bottom navigation bar with tabs |

### Additional Screens (21 folders in `screens/`)

| Folder | What It Contains |
|---|---|
| `achievements/` | Gamification badges and streak display |
| `alarm/` | Alarm management (2 files) |
| `auth/` | Authentication flow |
| `dana/` | AI chat, voice, and conversation UI (3 files) |
| `health/` | Health dashboard with vitals |
| `home/` | Home screen variant |
| `islamic/` | Prayer times and Quran (2 files) |
| `journal/` | Dream and sleep journal |
| `led/` | Direct LED color wheel and brightness |
| `partner/` | Partner mode settings |
| `qr/` | QR code scanner for device pairing |
| `report/` | Report viewer |
| `scenes/` | Scene browser |
| `settings/` | Settings detail pages |
| `sleep_tips/` | AI-generated sleep improvement tips |
| `sounds/` | Ambient sound player (rain, ocean, etc.) |
| `spotify/` | Spotify integration |
| `subscription/` | Subscription management |
| `winddown/` | Wind-down session UI (2 files) |

### Theme (`theme.dart`, 9.8KB)
- Dark and light mode support
- Custom color scheme per personality (purple/orange/cyan)
- Font: uses system font with custom sizes

### State Management
- **Riverpod** — reactive state across the app
- `ThemeController` — dark/light/system with persistence
- `OnboardingController` — tracks first-time flow
- API Service — centralized HTTP client

---

## 18. Command System (`commands/`)

Handles specific voice and app commands:

| Module | Size | What It Handles |
|---|---|---|
| `lights.py` | 9.9KB | "Turn lights blue", "dim to 50%", "set color red" — parses color/brightness and calls LED controller |
| `reminders.py` | 6.5KB | "Remind me at 7 AM to take medicine" — extracts time and text, creates scheduled reminder |
| `reflection.py` | 5.5KB | "Let's reflect on today" — starts end-of-day reflection conversation |
| `sleep.py` | 1.3KB | "Start sleep tracking", "record my bedtime" — triggers sleep session |
| `undo_manager.py` | 2.8KB | "Undo that" — reverts last action (LED change, alarm set, etc.) |
| `registry.py` | 1.9KB | Command registration and matching — maps text patterns to handlers |

---

## 19. Monitoring & Logging

### Prometheus Metrics
| Metric | Type | What It Tracks |
|---|---|---|
| `http_request_total` | Counter | Total requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency |
| `http_error_total` | Counter | Errors by endpoint |

### Grafana Dashboards
Pre-configured dashboards: API performance (P50/P95/P99 latency), error rates, DB pool usage, resource consumption.

### Alert Rules
| Alert | Condition |
|---|---|
| High error rate | >5% errors for 5 minutes |
| High latency | P95 >2s for 5 minutes |
| Service down | No response for >2 minutes |
| High memory | >1GB for 10 minutes |
| Auth failures | >5/second for 10 minutes |

### Sentry (error tracking)
- FastAPI + SQLAlchemy auto-instrumentation
- 10% trace sampling in production, 100% in development
- Environment tagged

### OpenTelemetry (`core/tracing.py`, 4.2KB)
- Distributed tracing with spans
- FastAPI auto-instrumentation
- Trace IDs in all responses

### Logging (`core/structured_logging.py`, 3.6KB)
- JSON format via loguru
- Correlation IDs per request
- All log levels: DEBUG → INFO → WARNING → ERROR

### Health Checks
- `GET /healthz` — simple "alive" check
- `GET /healthz/detailed` — checks: database connected? Redis connected? Deepgram API key set? Sensors responding? Disk space?

---

## 20. Deployment

### Docker Compose (7 services)

| Service | Image | Port | Purpose |
|---|---|---|---|
| `api` | Custom (Dockerfile) | 8000 | FastAPI backend |
| `voice` | Custom (Dockerfile) | — | Voice assistant runtime |
| `worker` | Custom (Dockerfile) | — | arq background jobs |
| `migrations` | Custom (Dockerfile) | — | Alembic migrations (runs once) |
| `db` | postgres:16-alpine | 5432 | PostgreSQL database |
| `redis` | redis:7-alpine | 6379 | Cache + pub/sub + queue |
| `prometheus` | prom/prometheus | 9090 | Metrics collection |
| `grafana` | grafana/grafana | 3000 | Dashboards |

**Resource limits:** api (2 CPU, 2GB RAM), voice (1.5 CPU, 1GB), worker (1 CPU, 512MB), db (1 CPU, 1GB), redis (0.5 CPU, 256MB).

### Dockerfile
- Base: `python:3.11-slim`
- System deps: `libpq-dev`, `portaudio19-dev` (for audio)
- Installs `requirements.txt` (108 packages)
- Entrypoint: `gunicorn api.app_factory:app -w 4 -k uvicorn.workers.UvicornWorker`

### Raspberry Pi Deployment
- Runs voice runtime + API on the Pi directly
- GPIO access for sensors and LEDs
- Local network access for mobile app
- Can work offline (local STT, cached prayer times)
- Special env vars: `WAKE_WORD_MODE=voice`, `LED_HARDWARE_ENABLED=true`, `SENSOR_PRESSURE_PIN=17`

### Backup System (`core/backup_manager.py`, 352 lines)
- AES-256 encrypted backups
- Schedule: daily at 3 AM
- Retention: 30 daily, 12 weekly, 6 monthly
- SHA-256 integrity verification
- Optional cloud sync hooks (S3)

---

## 21. Testing — 90 Test Files

### Framework
- **pytest** + **pytest-asyncio** for async tests
- **hypothesis** for property-based testing (generates random inputs)
- **freezegun** for time mocking
- **Coverage target:** 70%+

### Test Categories

| Category | What It Tests |
|---|---|
| AI | conversation engine, intent classifier, emotion router, personality |
| Voice | STT manager, TTS manager, VAD filter, wake word |
| Auth | registration, login, refresh, OTP, social auth |
| Database | models, repositories, migrations |
| Automation | registry, defaults, idempotency, Islamic automations |
| Sleep | analyzer, score, debt tracker, wake optimizer |
| API | each router's endpoints |
| Mobile | app commands, feedback, auth sessions |
| Hardware | sensor readings, LED commands |
| Subscriptions | billing, gate, trial |
| Integration | calendar, Spotify, fitness trackers |

### CI/CD (GitHub Actions)
Two quality gates:
- **Backend:** Python 3.11 → install deps → ruff lint → pytest
- **Mobile:** Flutter 3.41 → analyze → test
- Both must pass to merge a pull request

---

## 22. Storage Layer (`Storage/`)

| Module | What It Does |
|---|---|
| `io.py` | Atomic JSON file writes (write to temp file → rename). Locked reads (prevents corruption). |
| `cache_manager.py` | In-memory cache with TTL (time-to-live). Avoids re-reading files. |
| `schedule_manager.py` | Manages scheduled events stored in JSON. Time parsing and validation. |
| `user_profile.py` | Load/save/delete user profile JSON files. |
| `subscription_store.py` | JSON-file-based subscription storage (legacy, being migrated to DB). |

---

## 23. Additional Systems

### Gamification (`gamification/achievement_engine.py`, 13.7KB)
Tracks achievements across categories:

| Achievement | Category | How to Earn | Reward |
|---|---|---|---|
| First Week | Sleep | Track 7 nights | Custom scene builder |
| Monthly Champion | Sleep | Track 30 nights | Advanced analytics |
| Sleep Master | Sleep | Track 100 nights | Exclusive scene pack |
| Year of Excellence | Sleep | Track 365 nights | 50% lifetime discount |
| Quality Sleeper | Quality | 7 nights with score >80 | Sleep insights badge |
| Elite Sleeper | Quality | 30 nights with score >80 | Premium analytics |

### Guest Mode (`guest_mode/`, 5 files)

**auto_guest_detection.py (6KB):** Detects unusual pressure patterns (different body weight). If owner is away and someone enters bed during unusual hours (10AM-6PM), confirms after 15 minutes → activates guest mode.

**guest_manager.py (3.6KB):** Manages guest sessions. Basic features only. No personal data access.

**guest_privacy.py (2KB):** Hides owner's sleep history, conversation memory, and personal settings during guest mode.

**guest_settings.py (1.1KB):** Default guest preferences (neutral lighting, no Islamic features unless requested).

**guest_api.py (2.5KB):** REST endpoints for guest mode management.

### Partner Engine (`core/partner_engine.py`, 262 lines)
- Dual pressure sensor detection (left/right side of bed)
- Separate sleep tracking per partner
- Individual wake times and preferences
- Couple sleep goal tracking

### Presence Engine (`core/presence_engine.py`, 309 lines)
Unified context detection from sensor data:

| Context State | How Detected |
|---|---|
| `sleeping` | In bed + minimal movement for >15 min |
| `wind_down` | Wind-down routine active |
| `awake_in_bed` | In bed + significant movement |
| `reading` | In bed + light on + minimal movement |
| `relaxing` | In bed + music playing |
| `away` | Not in bed |
| `bathroom_trip` | Was sleeping → left bed → returned within 10 min |
| `guest_mode` | Guest detection triggered |
| `nap` | In bed during daytime (10AM-4PM) |

### Reports (`reports/`, 3 files)

**pdf_generator.py (12.7KB):** Generates weekly health reports as A4 PDFs using ReportLab. Includes sleep trends, heart rate charts, recommendations.

**html_report_renderer.py (10.2KB):** Generates HTML version of reports for email embedding.

**chart_generator.py (7.4KB):** Creates Plotly charts: sleep duration trends, bedtime consistency, heart rate over night, sleep score history.

### Health Monitoring (`core/health_monitor.py`, 15KB)
Comprehensive system health checks:
- Database connectivity
- Redis connectivity
- Deepgram API reachability
- Sensor status
- Disk space
- Memory usage
- CPU load
- Service uptime

---

*This completes the deep technical documentation of every component in the Smart Bed AI project.*
