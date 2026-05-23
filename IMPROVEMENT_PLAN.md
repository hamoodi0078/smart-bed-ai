# Danah Smart Bed — Master Improvement Plan
**Audit date: 2026-05-08 · Scope: all layers**

---

## HOW TO READ THIS DOCUMENT

Each item has:
- **Priority** — P0 (blocker), P1 (ship-critical), P2 (quality), P3 (growth)
- **Effort** — S (< 2 h), M (half day – 1 day), L (2–4 days), XL (1+ week)
- **Layer** — Backend / Flutter / Infra / Security / DB / Admin

Items are grouped into sprints. Do each sprint in order; later sprints depend on earlier ones.

---

## SPRINT 0 — IMMEDIATE BLOCKERS (do today)
*These break CI, crash startup, or make the app wrong right now.*

---

### B-01 · Uncomment `localizationsDelegates` in app.dart
**Priority:** P0 · **Effort:** S · **Layer:** Flutter

**Problem:** `flutter_localizations` is in `pubspec.yaml` but the import and `localizationsDelegates` are commented out in `mobile_app/lib/src/app.dart` (lines 3–5, 243–247). Arabic RTL layout, `Directionality`, and `intl` date formatting all silently fail.

**Fix:**
1. Run `flutter pub get` once to register the SDK package.
2. In `src/app.dart`, remove the comment block around the import and the `localizationsDelegates` list.
3. Add `AppLocalizations.delegate` from `lib/l10n/` once `flutter gen-l10n` is run.

---

### B-02 · Fix dual `config` import collision
**Priority:** P0 · **Effort:** M · **Layer:** Backend

**Problem:** `config.py` (flat module) and `config/settings.py` (pydantic-settings) both exist. `web_server.py` uses `from config import settings` (old). `api/app_factory.py` uses `from config.settings import settings` (new). They likely return different objects → env vars read twice, potential conflict.

**Fix:**
1. Audit every file that does `from config import …` — grep result: ~40 files.
2. Decide one canonical source: keep `config/settings.py` as the truth.
3. In `config/__init__.py`, re-export every name that `config.py` currently exposes so existing imports don't break.
4. Delete `config.py` once all references resolve.
5. Add a CI lint rule: `grep -r "from config import" . --include="*.py"` should match only the re-export shim, not multiple different files.

---

### B-03 · Add `Alarm` SQLAlchemy model + Alembic migration
**Priority:** P0 · **Effort:** M · **Layer:** DB

**Problem:** `database/models.py` has 18 models but no `Alarm` table. Alarms are stored in SQLite `data/manues.db` via raw SQL in web_server.py. This means alarm data is siloed from the main PostgreSQL database, can't be joined with user data, and has no schema enforcement.

**Fix — new model:**
```python
class Alarm(Base):
    __tablename__ = "alarms"
    __table_args__ = (Index("idx_alarms_user_enabled", "user_id", "enabled"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), ForeignKey("users.id"), nullable=False, index=True)
    time: Mapped[str] = mapped_column(String(5), nullable=False)          # "HH:MM"
    days: Mapped[list] = mapped_column(JSON, nullable=False, default=list) # [1..7]
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    wake_style: Mapped[str] = mapped_column(String(30), nullable=False, default="led_sunrise")
    smart_wake_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    smart_wake_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
```
Then: `alembic revision --autogenerate -m "add_alarms_table"` → `alembic upgrade head`.

---

### B-04 · Fix `Bed.is_stale` deprecated `datetime.utcnow()`
**Priority:** P0 · **Effort:** S · **Layer:** DB

**Problem:** `database/models.py` line 52 uses `datetime.utcnow()` which is deprecated in Python 3.12+ and returns a naive datetime, causing incorrect comparison with the timezone-aware `last_seen` column.

**Fix:**
```python
# Before
delta = (datetime.utcnow() - self.last_seen.replace(tzinfo=None)).total_seconds()

# After
from datetime import timezone
delta = (datetime.now(timezone.utc) - self.last_seen).total_seconds()
```

---

### B-05 · Fix `NightlySummaryFeedbackProgress.last_summary_generated_at_utc` type
**Priority:** P0 · **Effort:** S · **Layer:** DB

**Problem:** `database/models.py` line 181 — `last_summary_generated_at_utc` is typed as `String(40)` when it should be `DateTime(timezone=True)`. Inconsistent with every other timestamp in the schema, makes date-range queries impossible.

**Fix:** Change column type to `DateTime(timezone=True)`, add Alembic migration.

---

## SPRINT 1 — BACKEND API MIGRATION (week 1)
*Break the 391 KB monolith into proper routers.*

---

### A-01 · Migrate `auth` routes out of web_server.py
**Priority:** P1 · **Effort:** L · **Layer:** Backend

**Target file:** `api/routers/auth.py`

Routes to migrate (line references are in the stub's docstring):
- `POST /v1/auth/register` — email/password signup
- `POST /v1/auth/login` — returns JWT access + refresh
- `POST /v1/auth/logout` — revoke session
- `POST /v1/auth/revoke-all-sessions`
- `POST /v1/auth/delete-data` — GDPR erasure
- `GET  /v1/auth/me`
- `POST /v1/mobile/auth/register`
- `POST /v1/mobile/auth/login`
- `POST /v1/mobile/auth/otp/request` — Twilio SMS OTP
- `POST /v1/mobile/auth/otp/verify`
- `POST /v1/mobile/auth/social` — Google / Facebook / Apple sign-in
- `POST /v1/mobile/auth/refresh`
- `POST /v1/mobile/auth/logout`
- `GET  /v1/mobile/auth/me`

**Pattern:** Copy the route handler body verbatim, replace `app.` decorators with `router.`, inject shared dependencies via FastAPI `Depends()` instead of module globals, then delete from web_server.py. Uncomment in `app_factory.py`.

---

### A-02 · Migrate `alarms` routes
**Priority:** P1 · **Effort:** M · **Layer:** Backend

**Target file:** `api/routers/alarms.py`

Routes (lines 7472–7601 in web_server.py):
- `GET    /v1/mobile/alarms`
- `POST   /v1/mobile/alarms` (create + update, differentiates by `alarm_id` presence)
- `POST   /v1/mobile/alarms/{alarm_id}/toggle`
- `DELETE /v1/mobile/alarms/{alarm_id}`

**Additional work:** Point these routes at the new `Alarm` SQLAlchemy model from B-03 (not `data/manues.db`).

---

### A-03 · Migrate `sleep` + `dashboard` routes
**Priority:** P1 · **Effort:** L · **Layer:** Backend

**Target file:** `api/routers/sleep.py`

Routes:
- `GET /v1/mobile/dashboard` — main mobile dashboard (sleep score, biometrics, weekly insight)
- `GET /v1/sleep/overview` — detailed sleep overview
- `GET /v1/mobile/routine` — bedtime routine state
- `POST /v1/mobile/routine` — update routine settings

---

### A-04 · Migrate `scenes` routes
**Priority:** P1 · **Effort:** M · **Layer:** Backend

Routes:
- `GET  /v1/mobile/scenes`
- `GET  /v1/scenes/templates`
- `POST /v1/scenes/compose`
- `POST /v1/mobile/scenes/preview`
- `POST /v1/mobile/scenes/save-tonight`

---

### A-05 · Migrate `profile` + `settings` routes
**Priority:** P1 · **Effort:** M · **Layer:** Backend

Routes:
- `GET  /v1/mobile/profile`
- `POST /v1/mobile/profile`
- `GET  /v1/mobile/settings`
- `POST /v1/mobile/settings`
- `GET  /v1/mobile/usage`

---

### A-06 · Migrate `devices` routes
**Priority:** P1 · **Effort:** L · **Layer:** Backend

Routes (bed pairing, device commands, firmware):
- `GET  /v1/mobile/device-controls`
- `GET  /v1/mobile/bed/pairing`
- `POST /v1/mobile/bed/pair`
- `POST /v1/mobile/bed/unpair`
- `POST /v1/mobile/device-controls`
- `POST /v1/mobile/device-commands`
- `GET  /v1/mobile/device-commands/{id}`
- `GET  /v1/mobile/devices`
- `GET  /v1/bed/state`
- `GET  /v1/device/status`
- `GET  /v1/device/firmware-check`

---

### A-07 · Migrate `subscriptions` + billing routes
**Priority:** P1 · **Effort:** L · **Layer:** Backend

Routes (PayPal + subscription management):
- `POST /v1/subscriptions/trial/start`
- `GET  /v1/subscriptions/status`
- `GET  /v1/mobile/subscription/status`
- `GET  /v1/mobile/plan`
- `GET  /v1/mobile/subscription/history`
- `POST /v1/mobile/subscription/checkout`
- `POST /v1/mobile/subscription/capture`
- `POST /v1/mobile/subscription/cancel`
- `POST /v1/mobile/subscription/pause`
- `GET  /billing/paypal/approve`
- `GET  /billing/paypal/cancel`
- `POST /v1/billing/paypal/webhook`

---

### A-08 · Migrate `chat` + WebSocket routes
**Priority:** P1 · **Effort:** L · **Layer:** Backend

Routes (REST + SSE + WebSocket):
- `POST  /v1/ai/chat`
- `GET   /v1/ai/chat/stream` — Server-Sent Events
- `WS    /ws/chat`
- `WS    /ws/voice`

Note: WebSocket routes use `@router.websocket()` — include with `prefix=""` in app_factory.

---

### A-09 · Migrate remaining routes + wire all routers in app_factory.py
**Priority:** P1 · **Effort:** M · **Layer:** Backend

After A-01 through A-08, uncomment all router registrations in `app_factory.py`. Then migrate:
- `api/routers/integrations.py` — Spotify OAuth, Fitbit, Garmin, Google Calendar callbacks
- `api/routers/reports.py` — weekly PDF report generation
- `api/routers/notifications.py` — register device token, send push

Finally: retire `web_server.py` as the entry point. `uvicorn api.app_factory:app` becomes the only deployment target.

---

## SPRINT 2 — ADMIN PANEL (week 2)
*Build the admin panel from zero — backend first, then frontend.*

---

### C-01 · Implement admin backend routes
**Priority:** P1 · **Effort:** XL · **Layer:** Backend

**Target file:** `api/routers/admin.py`

Implement all 30+ routes currently listed in the stub's docstring. Grouped by domain:

**Admin Auth (3 routes)**
- `POST /v1/admin/auth/login` — admin-only JWT (separate role from user JWT)
- `GET  /v1/admin/auth/me`
- `GET  /v1/admin/observability` + `GET /v1/admin/diagnostics` — basic health

**User Management (6 routes)**
- `GET  /v1/admin/users` — paginated user list with search
- `GET  /v1/admin/users/{id}/detail` — full user profile + subscription + sessions
- `PATCH /v1/admin/users/{id}` — update subscription tier, ban, etc.
- `GET  /v1/admin/users/{id}/features` — per-user feature flag overrides
- `POST /v1/admin/users/{id}/features` — set override
- `DELETE /v1/admin/users/{id}/features/{key}` — clear override

**Feature Flags (4 routes)**
- `GET  /v1/admin/feature-flags` — full flag list with rollout %
- `POST /v1/admin/feature-flags` — create flag
- `PATCH /v1/admin/feature-flags/{key}` — toggle / update rollout %

**App/Firmware Versions (5 routes)**
- `GET  /v1/admin/versions`
- `POST /v1/admin/versions/app` — publish new app version
- `POST /v1/admin/versions/firmware` — publish new firmware
- `PATCH /v1/admin/versions/{id}` — update rollout %, force-update flag

**Beta Cohort (3 routes)**
- `GET  /v1/admin/mobile/beta-acceptance`
- `GET  /v1/admin/mobile/beta-cohort`
- `POST /v1/admin/mobile/beta-cohort/enroll`

**Operational (6 routes)**
- `GET  /v1/admin/overview` — KPI cards (MAU, revenue, sessions)
- `GET  /v1/admin/incidents` — recent errors from Sentry
- `GET  /v1/admin/runtime` — CPU, memory, active connections
- `GET  /v1/admin/fleet` — all beds with online/offline status
- `GET  /v1/admin/audit` — action audit log
- `GET  /v1/admin/billing/timeline` — revenue by month

**Actions (2 routes)**
- `POST /v1/admin/actions` — bulk user actions
- `POST /v1/admin/voice/circuit-breaker/reset`

**Security requirement:** All `/v1/admin/*` routes must check `role == "admin"` in the JWT. Add a `require_admin` FastAPI dependency. Admin tokens must be short-lived (15 min) with no refresh. Admin login must enforce MFA (TOTP or email OTP).

---

### C-02 · Build admin frontend (React + Vite + TailwindCSS)
**Priority:** P1 · **Effort:** XL · **Layer:** Admin

**Location:** `admin_panel/` at project root.

**Tech stack:** React 18 + Vite + TailwindCSS + shadcn/ui + Recharts.

**Pages to build (priority order):**

1. **Login page** — email + password → calls `/v1/admin/auth/login` → stores JWT in memory (not localStorage, admin security)
2. **Dashboard** — KPI cards: total users, active subscriptions, MAU, beds online, revenue last 30 days. Uses `/v1/admin/overview`.
3. **Users table** — searchable/sortable paginated list. Click row → user detail drawer (subscription, sessions, feature overrides). Uses `/v1/admin/users`.
4. **Feature Flags** — toggle table with rollout percent slider. Inline edit. Uses `/v1/admin/feature-flags`.
5. **Beta Cohort** — table of enrolled users, enroll new user form. Uses beta-cohort routes.
6. **Fleet Health** — live table of beds with last-seen timestamp, firmware version, online indicator. Polls `/v1/admin/fleet` every 30s.
7. **App Versions** — publish new app/firmware version with rollout %, changelog textarea. Uses version routes.
8. **Billing Timeline** — bar chart of monthly revenue. Uses `/v1/admin/billing/timeline`.
9. **Audit Log** — chronological action log with user/IP/action columns.

**CI integration:** Add `admin_panel` build step to `ci.yml`:
```yaml
admin:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: admin_panel
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with: { node-version: '20' }
    - run: npm ci
    - run: npm run build
    - run: npm run lint
```

---

## SPRINT 3 — FLUTTER COMPLETION (week 3)
*Audit and complete every Flutter screen. Unify the two screen directories.*

---

### F-01 · Unify Flutter screen directories
**Priority:** P1 · **Effort:** L · **Layer:** Flutter

**Problem:** 26 screens in `mobile_app/lib/screens/` + 23 in `mobile_app/lib/src/ui/screens/` — some screens are duplicated, routes import from both, creating a split codebase.

**Decision:** Keep `src/ui/screens/` as the canonical location (Riverpod ConsumerWidget pattern). Migrate everything from `screens/` into it.

**Migration list (legacy → new):**
| Legacy (`screens/`) | Target (`src/ui/screens/`) | Action |
|---|---|---|
| `alarm/alarm_screen.dart` | `alarm_screen.dart` | Already complete in `screens/` — move |
| `alarm/smart_alarm_screen.dart` | `smart_alarm_screen.dart` | Move |
| `dana/dana_chat_screen.dart` | `dana_chat_screen.dart` | Move, merge with existing stub |
| `dana/dana_screen.dart` | `dana_screen.dart` | Create new |
| `dana/dana_selector_screen.dart` | `dana_selector_screen.dart` | Create new |
| `health/health_dashboard_screen.dart` | `health_dashboard_screen.dart` | Move + Riverpod |
| `home/home_screen.dart` | *(stays in `screens/`)* | Home is already complete in `screens/` |
| `islamic/islamic_screen.dart` | `islamic_screen.dart` | Merge/consolidate |
| `journal/sleep_journal_screen.dart` | `journal_screen.dart` | Move + API |
| `led/led_control_screen.dart` | `led_control_screen.dart` | Move |
| `partner/partner_mode_screen.dart` | `partner_screen.dart` | Move + implement |
| `qr/qr_scanner_screen.dart` | `qr_screen.dart` | Move |
| `report/sleep_report_screen.dart` | `report_screen.dart` | Merge with existing |
| `scenes/scenes_gallery_screen.dart` | `scenes_screen.dart` | Merge |
| `settings/settings_screen.dart` | `settings_screen.dart` | Merge |
| `sleep_tips/sleep_tips_screen.dart` | `sleep_tips_screen.dart` | Move |
| `sounds/sleep_sounds_screen.dart` | `sounds_screen.dart` | Move |
| `spotify/spotify_screen.dart` | `spotify_screen.dart` | Merge |
| `subscription/subscription_screen.dart` | `subscription_screen.dart` | Merge + implement |
| `winddown/winddown_journey_screen.dart` | `winddown_screen.dart` | Consolidate both winddown files |
| `achievements/achievements_screen.dart` | `achievements_screen.dart` | Move |

After migration: delete `screens/` directory, update all imports in `app.dart` and `main_shell.dart`.

---

### F-02 · Complete `SubscriptionScreen` — PayPal checkout flow
**Priority:** P1 · **Effort:** L · **Layer:** Flutter

**Problem:** Subscription screen exists but PayPal checkout is stub-level. Users can't subscribe.

**Required flow:**
1. Screen shows plan cards (Free / Standard KWD / Pro KWD) pulled from `/v1/mobile/plan`
2. Tap "Subscribe" → POST `/v1/mobile/subscription/checkout` → receive PayPal approval URL
3. Open URL in in-app WebView (`url_launcher` with `LaunchMode.inAppWebView`)
4. On return to app, POST `/v1/mobile/subscription/capture` with PayPal order ID
5. Show success/failure state, refresh subscription status
6. "Cancel subscription" button → POST `/v1/mobile/subscription/cancel`

---

### F-03 · Complete `HealthDashboardScreen` with real API + Riverpod
**Priority:** P1 · **Effort:** L · **Layer:** Flutter

**Problem:** Screen uses `fl_chart` but with hardcoded/mock data. No Riverpod, no NetworkBanner.

**Fix:**
1. Create `healthDataProvider = FutureProvider.autoDispose` that calls `ApiService.getHealthDashboard()`
2. Add `ShimmerLoader` for chart loading state
3. Add `NetworkBanner` at top
4. Wire `fl_chart` to real sleep scores, HRV trend, activity data
5. Pull-to-refresh with `ref.invalidate()`

---

### F-04 · Complete `PartnerModeScreen`
**Priority:** P2 · **Effort:** L · **Layer:** Flutter

**Problem:** Partner mode screen exists but partner sync has no API backing.

**Required features:**
- Show partner's current bed presence (from `Bed.partner_user_id`)
- Sync "Do Not Disturb" window with partner
- Partner LED zone control (each user controls their side independently)
- Share sleep stats with partner (consent-gated)

**Requires backend work:** Add partner-sync endpoints to `devices` router.

---

### F-05 · Complete `SleepJournalScreen` — sync to backend
**Priority:** P2 · **Effort:** M · **Layer:** Flutter

**Problem:** Journal entries are stored locally only (`SharedPreferences`). They're lost on reinstall.

**Fix:**
1. Add `POST /v1/mobile/journal` + `GET /v1/mobile/journal` endpoints (backend)
2. Add `JournalEntry` SQLAlchemy model
3. Flutter: create `journalProvider`, sync on load and save, offline-first with Hive cache

---

### F-06 · Complete `ConnectBedScreen` — full QR + pairing flow
**Priority:** P1 · **Effort:** M · **Layer:** Flutter

**Problem:** `connect_bed_screen.dart` exists but QR pairing may not be fully wired to `/v1/mobile/bed/pair`.

**Fix:**
1. Screen opens `QRScannerScreen` → parses claim token from QR
2. POST `/v1/mobile/bed/pair` with `{ claim_token, device_id }`
3. On success: save `bed_id` to secure storage, navigate to `/dashboard`
4. Handle `MOBILE_PAIRING_REQUIRE_CLAIM_TOKEN=1` env requirement

---

### F-07 · Complete `AchievementsScreen`
**Priority:** P2 · **Effort:** M · **Layer:** Flutter

**Problem:** `gamification/achievement_engine.py` has a complete engine but no API endpoint. Flutter screen likely has no real data.

**Fix:**
1. Add `GET /v1/mobile/achievements` endpoint → calls `AchievementEngine.get_user_achievements(user_id)`
2. Flutter: create `achievementsProvider`, show badge grid with locked/unlocked states
3. Trigger `lottie` animation on newly unlocked badges (use `Lottie.asset`)

---

### F-08 · Complete `SleepSoundsScreen` — real audio with `just_audio`
**Priority:** P2 · **Effort:** M · **Layer:** Flutter

**Problem:** Sleep sounds screen likely has buttons but no real `just_audio` integration.

**Fix:**
1. Use `just_audio` `AudioPlayer` to stream/play local assets or remote URLs
2. Implement fade-in/fade-out for smooth audio transitions
3. Timer to auto-stop after N minutes (user-configurable)
4. Background audio support (Android foreground service + iOS background mode)

---

### F-09 · Implement `BedControlsScreen` real-time LED control
**Priority:** P2 · **Effort:** M · **Layer:** Flutter

**Problem:** `bed_controls_screen.dart` exists but likely doesn't send real LED commands.

**Fix:**
1. Wire color picker → POST `/v1/mobile/device-controls` with `{ action: "set_color", color: ... }`
2. Brightness slider → POST with `{ action: "set_brightness", value: ... }`
3. Scene quick-actions → POST scene key
4. Show real-time device status from `GET /v1/device/status`

---

### F-10 · Fix `flutter_localizations` and wire `AppLocalizations` throughout app
**Priority:** P1 · **Effort:** M · **Layer:** Flutter

**Problem:** l10n infrastructure (ARB files, `l10n.yaml`, `locale_controller.dart`) is all done but the delegates are commented out and no screen uses `AppLocalizations.of(context)`.

**Steps:**
1. Uncomment delegates in `app.dart` (see B-01)
2. Run `flutter gen-l10n`
3. Add `AppLocalizations.of(context)!.greetingMorning` usage in `HomeScreen`, `IslamicScreen`, `DanaChatScreen`, `SettingsScreen`
4. Wire language toggle in Settings to `LocaleController`
5. Test RTL layout on Arabic locale (mainly `IslamicScreen` and prayer rows)

---

### F-11 · Add Flutter widget tests
**Priority:** P2 · **Effort:** L · **Layer:** Flutter

**Problem:** `flutter test` in CI passes vacuously — no test files exist.

**Minimum test suite to add (`mobile_app/test/`):**
1. `home_screen_test.dart` — mock provider, assert greeting + quick action cards render
2. `islamic_screen_test.dart` — mock prayer data, assert 5 prayer rows + toggle
3. `alarm_screen_test.dart` — empty list state, single alarm card with toggle
4. `network_banner_test.dart` — shows when offline, hides when online
5. `locale_controller_test.dart` — toggle AR, persists to SharedPreferences, reverts to EN

---

## SPRINT 4 — BACKEND FEATURES (week 4)
*Wire the back-end modules that are written but have no API endpoints.*

---

### D-01 · Expose `gamification/achievement_engine.py` via API
**Priority:** P2 · **Effort:** M · **Layer:** Backend

`AchievementEngine` is complete. Add to a new `api/routers/gamification.py`:
- `GET /v1/mobile/achievements` — list user achievements with locked/unlocked
- `POST /v1/mobile/achievements/claim/{id}` — claim reward

---

### D-02 · Wire `guest_mode/` via API
**Priority:** P2 · **Effort:** M · **Layer:** Backend

Four guest-mode files exist (`guest_manager.py`, `guest_privacy.py`, `guest_settings.py`, `auto_guest_detection.py`) but are not exposed. Add:
- `POST /v1/mobile/guest/start`
- `DELETE /v1/mobile/guest`
- `GET  /v1/mobile/guest/status`

---

### D-03 · Wire Fitbit/Garmin sync jobs
**Priority:** P2 · **Effort:** M · **Layer:** Backend

`integrations/fitbit_client.py` and `integrations/garmin_client.py` are written. Wire them:
1. Add OAuth callback route for Fitbit (`GET /v1/fitbit/callback`)
2. Schedule nightly sync via `APScheduler` (already a dependency) — pull HRV, sleep stages, steps
3. Store results in `SleepSession` enrichment fields
4. Expose `GET /v1/mobile/fitness-sync/status` for the Flutter health dashboard

---

### D-04 · Wire `health/hydration_tracker.py` + `stress_detector.py`
**Priority:** P3 · **Effort:** M · **Layer:** Backend

Both modules have logic but no routes. Add to `health` router:
- `GET  /v1/mobile/health/hydration`
- `POST /v1/mobile/health/hydration/log`
- `GET  /v1/mobile/health/stress`

---

### D-05 · Complete `realtime_voice_pipeline.py` WebSocket stabilization
**Priority:** P2 · **Effort:** L · **Layer:** Backend

`ai/realtime_voice_pipeline.py` exists but WebSocket voice route is still in web_server.py. After A-08 migration, audit:
1. VAD → STT → LLM → TTS pipeline latency (target < 1.5s round-trip)
2. Barge-in handling via `ai/barge_in_monitor.py`
3. Echo cancellation via `ai/acoustic_echo_guard.py`
4. Speaker diarization (new `ai/speaker_diarization.py`) — identify who's speaking in partner mode

---

### D-06 · Wire `dana/` personality modes properly
**Priority:** P2 · **Effort:** M · **Layer:** Backend

`dana/therapist.py`, `dana/coach.py`, `dana/guide.py` all exist. Audit `ai/conversation_engine.py` to ensure:
1. Personality routing correctly dispatches to each module
2. `dana/personality.py` evolution persists personality drift scores to DB
3. The mobile `/v1/ai/chat` endpoint accepts `personality` param and routes correctly

---

## SPRINT 5 — SECURITY HARDENING
*These apply across all layers.*

---

### S-01 · Admin JWT separation
**Priority:** P1 · **Effort:** M · **Layer:** Security

Admin tokens must be completely separate from user tokens:
- Different signing secret (`ADMIN_JWT_SECRET` in `.env.example`)
- Shorter TTL (15 min, no refresh)
- Contain `role: "admin"` claim
- All admin routes check this with a `require_admin` FastAPI Depends

---

### S-02 · OTP delivery hardening
**Priority:** P1 · **Effort:** S · **Layer:** Security

From `.env.example`: `MOBILE_OTP_DEBUG=0` + `MOBILE_OTP_SECRET` + `MOBILE_OTP_DELIVERY_MODE=auto`. Ensure:
1. `MOBILE_OTP_DEBUG=1` is **impossible** in production — add a startup assertion: `if settings.mobile_otp_debug and settings.env == "production": raise RuntimeError`
2. OTP codes must be rate-limited (5 attempts / 10 min per IP) — the `rate_limiter.py` middleware needs an OTP-specific tier
3. OTP expiry must be ≤ 10 minutes

---

### S-03 · PayPal webhook signature verification
**Priority:** P1 · **Effort:** M · **Layer:** Security

`POST /v1/billing/paypal/webhook` must verify the PayPal webhook signature using the `PAYPAL_WEBHOOK_ID` before processing. HMAC verification using PayPal's auth-algo headers. Without this, anyone can fake subscription payments.

---

### S-04 · CORS tightening for production
**Priority:** P1 · **Effort:** S · **Layer:** Security

`app_factory.py` currently uses `WEB_ALLOWED_ORIGINS` which defaults to `localhost`. Add to `.env.production.template`:
```
WEB_ALLOWED_ORIGINS=https://app.danah.io,https://admin.danah.io
```
And ensure `allow_credentials=True` is only set when origins are not `*`.

---

### S-05 · Secrets scanning in CI
**Priority:** P1 · **Effort:** S · **Layer:** Security

The `gitleaks` step already exists but only runs with a paid `GITLEAKS_LICENSE`. Add a fallback using `trufflehog` (free):
```yaml
- name: TruffleHog secret scan
  uses: trufflesecurity/trufflehog@main
  with:
    path: ./
    base: ${{ github.event.repository.default_branch }}
    head: HEAD
```

---

### S-06 · Rate limit chat endpoint per user
**Priority:** P1 · **Effort:** S · **Layer:** Security

`RATE_LIMIT_CHAT_PER_MINUTE=30` is in `.env.example` but must be enforced per **authenticated user ID**, not per IP. Many users behind NAT share the same IP. Fix `api/middleware/rate_limiter.py` to use `user_id` from JWT when available, fall back to IP for unauthenticated routes.

---

## SPRINT 6 — PERFORMANCE + OBSERVABILITY

---

### P-01 · Prometheus + Grafana dashboard
**Priority:** P2 · **Effort:** M · **Layer:** Infra

Metrics are being emitted (`danah_http_requests_total`, `danah_http_request_latency_seconds`, `danah_http_errors_total`). Add a `docker-compose.monitoring.yml`:
```yaml
services:
  prometheus:
    image: prom/prometheus
    volumes: [./prometheus.yml:/etc/prometheus/prometheus.yml]
  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
```
And a pre-built Grafana dashboard JSON: request rate, p50/p95/p99 latency, error rate, active WebSocket connections.

---

### P-02 · Database connection pool tuning
**Priority:** P2 · **Effort:** S · **Layer:** Backend

`database/connection.py` uses asyncpg. Expose pool settings via `.env`:
```
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
```
Add a `GET /v1/admin/runtime` response that includes pool stats (`pool.size()`, `pool.checkedout()`).

---

### P-03 · Hive offline caching in Flutter
**Priority:** P2 · **Effort:** M · **Layer:** Flutter

`hive_flutter` is in `pubspec.yaml` but unused. Use it for:
1. Cache last dashboard response (serve immediately on next open, refresh in background)
2. Cache prayer times (they change daily — cache the full day)
3. Cache alarm list (show immediately without spinner)

Pattern: FutureProvider reads from Hive first → emits cached data → fires API call → updates Hive → emits fresh data.

---

### P-04 · Background fetch for sleep data
**Priority:** P2 · **Effort:** M · **Layer:** Flutter

Add `workmanager` package to pubspec. Register a background task that runs every morning at 08:00 to fetch previous night's sleep data and pre-warm the dashboard cache. This way the HomeScreen never shows a loading spinner on first open.

---

### P-05 · `SELECT N+1` audit in repositories.py
**Priority:** P2 · **Effort:** M · **Layer:** Backend

`database/repositories.py` likely has SELECT N+1 patterns for loading users with sessions, commands with feedback, etc. Audit with `sqlalchemy-utils` query count assertions in tests. Fix by adding `selectinload` / `joinedload` where needed.

---

## SPRINT 7 — INTEGRATIONS COMPLETION

---

### I-01 · Spotify OAuth complete flow
**Priority:** P2 · **Effort:** M · **Layer:** Backend + Flutter

`.env.example` has `SPOTIFY_CLIENT_ID/SECRET/SCOPES/REDIRECT_URI`. The OAuth flow needs:
1. Backend: `GET /v1/mobile/spotify/authorize` → redirect to Spotify
2. Backend: `GET /v1/mobile/spotify/callback` → exchange code for token → store in DB
3. Flutter: `SpotifyScreen` shows current playing track, play/pause/skip controls
4. Token auto-refresh (Spotify access tokens expire in 1 hour)

---

### I-02 · Google Calendar sync
**Priority:** P3 · **Effort:** M · **Layer:** Backend

`integrations/google_calendar_client.py` exists. Wire:
1. `GET /v1/mobile/calendar/today` — today's events (for smart alarm context)
2. Dana uses calendar events in morning briefing ("You have a meeting at 9 AM")
3. Respect event stress level (back-to-back meetings → suggest earlier bedtime)

---

### I-03 · Zigbee/MQTT smart home integration
**Priority:** P3 · **Effort:** L · **Layer:** Backend

`integrations/zigbee_coordinator.py` and `integrations/mqtt_client.py` exist. These enable control of Zigbee lights/sensors without cloud APIs. Wire to:
1. LED scene engine (scene changes also propagate to Zigbee lights)
2. Bed presence sensor (Zigbee pressure mat → occupancy detection)

---

### I-04 · Weather adaptive scenes
**Priority:** P3 · **Effort:** S · **Layer:** Backend

`scenes/weather_adaptive.py` exists. Wire it to `pyowm` (already a dependency). Add:
- `GET /v1/mobile/scenes/weather-adaptive` — returns scene adjusted for local weather
- Rainy night → warmer LED tone, white noise sound
- Hot day → cooler LED, fan sound

---

## SPRINT 8 — DEVOPS + DEPLOYMENT

---

### O-01 · Multi-stage Docker build
**Priority:** P1 · **Effort:** M · **Layer:** Infra

Current `Dockerfile` is likely a single stage. Optimize:
```dockerfile
FROM python:3.11-slim AS builder
RUN pip install --user -r requirements.txt

FROM python:3.11-slim AS runtime
COPY --from=builder /root/.local /root/.local
COPY . .
CMD ["uvicorn", "api.app_factory:app", "--host", "0.0.0.0", "--port", "8000"]
```
This reduces image size from ~2 GB to ~400 MB.

---

### O-02 · `docker-compose.yml` production-ready services
**Priority:** P1 · **Effort:** M · **Layer:** Infra

Current `docker-compose.yml` needs health checks and volume mounts for all services:
```yaml
services:
  api:
    build: .
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
  postgres:
    image: pgvector/pgvector:pg16
    healthcheck: { test: pg_isready, interval: 5s, retries: 5 }
  redis:
    image: redis:7-alpine
    healthcheck: { test: redis-cli ping, interval: 5s }
  celery:
    build: .
    command: celery -A tasks.celery_app worker -l info
  beat:
    build: .
    command: celery -A tasks.celery_app beat -l info
```

---

### O-03 · GitHub Actions: add coverage gate
**Priority:** P2 · **Effort:** S · **Layer:** CI/CD

Add a minimum coverage threshold to the CI backend job:
```yaml
- name: Coverage gate
  run: python -m pytest tests/ --cov --cov-fail-under=70 -q
```
Current: coverage is reported but not enforced. With 75+ test files, 70% is achievable immediately.

---

### O-04 · CD pipeline (deploy on merge to main)
**Priority:** P2 · **Effort:** L · **Layer:** CI/CD

Add a `deploy` job to `ci.yml` that fires on `push` to `main` only:
```yaml
deploy:
  needs: [backend, smoke, mobile]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - name: Deploy to production
      run: ssh deploy@${{ secrets.PROD_HOST }} 'cd /srv/danah && git pull && docker compose up -d --build'
```
Requires `PROD_HOST` + `PROD_SSH_KEY` in GitHub secrets.

---

### O-05 · Raspberry Pi deployment script
**Priority:** P3 · **Effort:** M · **Layer:** Infra

`docs/raspberry-pi-setup.md` exists but `scripts/` has `restart_server.bat`, `start_backend.ps1`, `start_hidden.vbs`, `start_tunnel.ps1` — Windows-only scripts. The Pi runs Linux. Add:
- `scripts/pi_deploy.sh` — pulls, restarts systemd service
- `scripts/systemd/danah.service` — systemd unit file
- Pi-specific env validation (check `LED_HARDWARE_ENABLED`, GPIO pins)

---

## OPEN ITEMS FOUND DURING SCAN (not yet in any sprint)

These need investigation before they can be planned:

| # | File | Issue |
|---|---|---|
| X-01 | `master_api.py` + `master_controller.py` | Two more entry points exist outside `web_server.py` / `app_factory.py`. What do they do? Do they duplicate routes? |
| X-02 | `automation_engine.py` | Separate automation engine at root — does it conflict with `automations/` package? |
| X-03 | `led_controller.py` | Root-level LED controller separate from `led/led_control.py` — duplication? |
| X-04 | `data/manues.db` | SQLite database with unknown schema — what tables? Should this be migrated to PostgreSQL? |
| X-05 | `dana/dana_api.py` + `dana/dana_core.py` | `dana_api.py` — is this a duplicate of `/v1/ai/chat`? |
| X-06 | `app_entry.py` | Called by `main.py._run()`. Is this the real voice/hardware entry point or the web entry point? |
| X-07 | `mobile_app/lib/screens/main_shell.dart` | `MainShell` uses `IndexedStack` with `screens/` versions — after F-01, this needs updating to use `src/ui/screens/` |
| X-08 | `Storage/subscription_store.py` (modified in git) | Was recently modified — verify subscription tier checks still work with the DB model from B-03 |
| X-09 | `.env` committed to repo | Git status shows `.env` as tracked but modified. `.env` should be in `.gitignore`. Verify secrets haven't been committed. |
| X-10 | `mobile_app/lib/screens/islamic/islamic_mode_screen.dart` | There are TWO Islamic screens: `islamic_screen.dart` (prayer times, full Riverpod) AND `islamic_mode_screen.dart` (toggle on/off). Are both needed? |

---

## EFFORT SUMMARY TABLE

| Sprint | Items | Total Effort | Prerequisite |
|---|---|---|---|
| Sprint 0 — Blockers | B-01…B-05 | ~1 day | — |
| Sprint 1 — API Migration | A-01…A-09 | ~2 weeks | Sprint 0 |
| Sprint 2 — Admin Panel | C-01…C-02 | ~2 weeks | Sprint 1 |
| Sprint 3 — Flutter | F-01…F-11 | ~2 weeks | Sprint 0 |
| Sprint 4 — Backend Features | D-01…D-06 | ~1 week | Sprint 1 |
| Sprint 5 — Security | S-01…S-06 | ~3 days | Sprint 1 |
| Sprint 6 — Performance | P-01…P-05 | ~1 week | Sprint 1 |
| Sprint 7 — Integrations | I-01…I-04 | ~1 week | Sprint 1 |
| Sprint 8 — DevOps | O-01…O-05 | ~1 week | Sprint 1 |
| Open Items | X-01…X-10 | ~3 days investigation | Sprint 0 |

**Estimated total to reach production-ready 9/10:** ~10–12 weeks of focused work.
**Current state:** ~5/10 (strong AI core, weak API surface, no admin panel, Flutter partially complete).

---

## QUICK REFERENCE: FILES THAT NEED WORK

### Backend — modify these
- `api/app_factory.py` — uncomment routers as each is migrated
- `api/routers/admin.py` — implement all 30+ routes
- `api/routers/auth.py` — migrate from web_server.py
- `api/routers/alarms.py` — migrate + point at new Alarm model
- `api/routers/chat.py` — migrate REST + SSE + WS
- `api/routers/sleep.py` — migrate dashboard + overview
- `api/routers/scenes.py` — migrate scene routes
- `api/routers/profile.py` — migrate profile + settings
- `api/routers/devices.py` — migrate pairing + commands
- `api/routers/subscriptions.py` — migrate PayPal + billing
- `database/models.py` — add `Alarm` model, fix type issues
- `config/__init__.py` — shim old imports, delete `config.py`
- `api/middleware/rate_limiter.py` — per-user rate limiting

### Flutter — modify these
- `mobile_app/lib/src/app.dart` — uncomment localizationsDelegates
- `mobile_app/lib/src/ui/screens/subscription_screen.dart` — PayPal flow
- `mobile_app/lib/src/ui/screens/bed_controls_screen.dart` — real LED commands
- `mobile_app/lib/src/ui/screens/connect_bed_screen.dart` — QR pairing
- `mobile_app/lib/screens/health/health_dashboard_screen.dart` — Riverpod + real data
- `mobile_app/lib/screens/partner/partner_mode_screen.dart` — implement
- `mobile_app/lib/screens/journal/sleep_journal_screen.dart` — backend sync
- `mobile_app/lib/screens/main_shell.dart` — update after F-01 migration

### New files to create
- `database/migrations/` — Alarm + JournalEntry migration
- `api/routers/gamification.py` — achievements endpoint
- `api/routers/notifications.py` — wire notification_api.py
- `admin_panel/` — entire React admin frontend
- `mobile_app/test/` — Flutter widget tests
- `scripts/pi_deploy.sh` — Raspberry Pi deploy script
- `prometheus.yml` + `docker-compose.monitoring.yml` — observability stack
