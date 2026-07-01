# DANAH SMART BED AI — DEPLOYMENT READINESS AUDIT & MVP ROADMAP

**Prepared:** 2026-06-30  
**Target:** 15 August 2026 — Kuwait Furniture Shop MVP Deployment  
**Status:** NOT READY — Critical blockers must be fixed before any hardware work or public deployment

---

## PART 1: COMPLETE DUPLICATE & CONFLICT AUDIT

### 1.1 Duplicate / Parallel Implementations Found

| Duplicate | File A | File B | Impact |
|-----------|--------|--------|--------|
| **LED Controller** | `led_controller.py` (root) — `apply_led_hardware_config()`, `apply_music_led_preferences()` | `led/led_control.py` — `LEDController` class | `app_entry.py` imports from BOTH. If signatures drift, one silently uses stubs. |
| **STT Manager** | `stt_manager.py` (root, loose) | `ai/stt_manager.py` (complete, typed) | Root version is older; any file importing root gets a weaker class. |
| **Command Handler** | `main.py` lines 745-812: `_execute_resolved_action()` | `voice_handler.py` imported `handle_local_commands()` | Local definition in main.py shadows the import entirely. |
| **Automation Engine** | Root `automation_engine.py` — global `automation_registry`, `planned_reminders`, `sleep_mode_active` | `automations/registry.py` + `automations/defaults.py` | Two separate automation systems sharing NO state. |
| **Master Controller** | `master_controller.py` — `DanaCore`, `SpotifyClient`, `SpotifyControls` | `app_entry.py` — `SpotifyManager`, `PersonalityRuntimeOrchestrator` | Two completely different implementations. Neither references the other. |
| **Profile Persistence** | `main.py` `save_profile()` → `Storage.user_profile` | `web_server.py` `_save_profile()` → `atomic_write_json()` directly | Three write paths with different locking. Race conditions if server + voice loop write simultaneously. |
| **Flutter Token Storage** | `mobile_app/lib/services/api_service.dart` — key: `auth_token` | `mobile_app/lib/src/core/session_store.dart` — key: `smart_bed.mobile_auth_session` | Two keys. `ApiService.getToken()` returns null after `SessionStore.write()`. |
| **WebSocket Routes** | `web_server.py` defines `ws_chat` and `ws_voice` | `api/routers/chat.py` re-exports them | Circular import: app_factory → chat_router → web_server → main → ... |
| **FastAPI App Instance** | `web_server.py` line 269: `app = FastAPI(...)` | `api/app_factory.py` line 346: `app = create_app()` | README says `uvicorn web_server:app`; CI/Docker uses `api.app_factory:app`. `web_server.py:app` is NEVER served but `api/routers/chat.py` imports FROM it. Half-migration. |

### 1.2 God Files — Structural Debt

| File | Size | Routes/Functions | Risk |
|------|------|-----------------|------|
| `web_server.py` | ~409 KB | 134+ routes in one file | Every import creates circular deps. Changes risk breaking unrelated features. |
| `voice_handler.py` | ~173 KB | 812 lines: intent, actions, therapist, wake logic, TTS, guide | Changes to intent detection might break therapist followups. |
| `database/repositories.py` | ~95 KB | Full ActiveRecord-style CRUD | Mixes domain logic with data access. |
| `app_entry.py` | ~88 KB | Main voice loop, all imports, all local handlers | Entry point also contains business logic — impossible to test in isolation. |

### 1.3 Import Circular Dependency Chain

```
api/app_factory.py
  → api/routers/chat.py
    → web_server.py
      → main.py
        → voice_handler.py
          → ai/* modules
            → automation_engine.py (root)
              → Storage/*
                → database/*
```

This means importing ANY router that touches `web_server.py` triggers the full `main.py` import tree including ALL hardware libraries. Any Pi-sensor import error crashes the entire API server.

---

## PART 2: TOP 10 RISKS (RANKED BY BLAST RADIUS)

### RISK-01 🔴 CRITICAL — Privacy Leak: Real Data in Public Repo
**Files:** `data/manues.db`, `runtime_data/idempotency_store.json`  
**Blast radius:** Legal liability, user trust destroyed, cannot demo with real data visible.  
**Fix:** `git rm --cached`, `git filter-repo --invert-paths`, rotate ALL secrets (Firebase, Deepgram, Spotify, OAuth, JWT), add to `.gitignore`: `data/*.db`, `runtime_data/**`, `*.sqlite`.

### RISK-02 🔴 CRITICAL — Dual Entrypoint Confusion
**Files:** `web_server.py:269`, `api/app_factory.py:346`, `README.md`, `.github/workflows/ci.yml`, `Dockerfile`  
**Blast radius:** Nobody knows which server runs. `web_server.py:app` has real logic but is never mounted. `api.app_factory:app` mounts routers that import FROM `web_server.py`.  
**Fix:** Make `api.app_factory:app` the ONLY entrypoint. Extract all handler functions out of `web_server.py` into `api/routers/` and `api/handlers/`. Then `web_server.py` only contains Pydantic models.

### RISK-03 🔴 CRITICAL — OTP HMAC Fallback Uses the Rejected Password
**File:** `web_server.py` line 1281  
```python
secret = settings.secret_key or "change-me-in-production"
```
The Settings validator REJECTS `"change-me-in-production"` as unsafe SECRET_KEY. But this exact string becomes the OTP HMAC secret when `MOBILE_OTP_SECRET` is unset.  
**Fix:** Remove the fallback. If `MOBILE_OTP_SECRET` is not set AND `SECRET_KEY` is not set, raise `RuntimeError` at startup.

### RISK-04 🔴 CRITICAL — Database Silent SQLite Fallback in Production
**File:** `database/connection.py` lines 35, 48-58  
**Blast radius:** Missing `DATABASE_URL` in production silently uses SQLite, but Docker Compose expects Postgres and models use PG-specific types. Runtime failure.  
**Fix:** When `DATABASE_URL` is empty AND `DANAH_ENV=production`, raise `RuntimeError`. Only allow SQLite fallback in `development`/`test`.

### RISK-05 🟠 HIGH — 178+ `except: pass` Blocks Swallowing Real Errors
**Scope:** `web_server.py`, `voice_handler.py`, `mobile_app/lib/services/api_service.dart`, `ai/stt_manager.py`  
**Blast radius:** STT fails silently → "I didn't catch that." DB writes fail → alarms lost. Auth refresh fails → user logged out with no explanation.  
**Fix:** Replace every `except: pass` with `logger.warning("context: {}", exc)`. Only pass on truly ignorable exceptions.

### RISK-06 🟠 HIGH — Two Parallel Spotify Implementations
**Files:** `master_controller.py` (root `spotify/` package) vs `app_entry.py` (`ai/spotify_manager`)  
**Blast radius:** Both control the same Spotify device. Volume fades from one are invisible to the other.  
**Fix:** Use `ai/spotify_manager.SpotifyManager` as canonical. Deprecate root `spotify/` package. Rewire `master_controller.py` to use `ai/spotify_manager`.

### RISK-07 🟠 HIGH — Flutter Dual API Client + Token Key Mismatch
**Files:** `mobile_app/lib/services/api_service.dart` (key: `auth_token`) vs `mobile_app/lib/src/core/session_store.dart` (key: `smart_bed.mobile_auth_session`)  
**Blast radius:** `ApiService.getToken()` returns null after `AuthController._hydrateSession()` wrote via `SessionStore`. Screens using `ApiService` get 401s.  
**Fix:** Migrate ALL API calls to `SmartBedApi` from `api_client.dart`. Delete `ApiService` static methods or make them delegate to `SmartBedApi`.

### RISK-08 🟠 HIGH — Router → Web Server Circular Imports
**File:** `api/routers/chat.py` lines 23, 31, 37  
```python
from web_server import ChatRequest, ai_chat as _ws
```
**Blast radius:** Loading the chat router imports ALL of `web_server.py` → `main.py` → `ai/*` → hardware stubs. Any missing Pi library crashes the API.  
**Fix:** Move handler functions from `web_server.py` into `api/handlers/chat_handlers.py`. No router should import from `web_server.py`.

### RISK-09 🟡 MODERATE — `web_server.py` God File Blocks Incremental Development
**File:** `web_server.py` (409 KB, 134+ routes)  
**Blast radius:** Every change risks breaking unrelated features. Code review is impossible. Merge conflicts guaranteed.  
**Fix (Phase 2, post-deploy):** The `api/routers/` migration is already 70% done. Finish extracting the remaining handlers.

### RISK-10 🟡 MODERATE — Three Race Conditions
1. **Profile race:** `app_entry.py` (voice loop) and `web_server.py` (HTTP threads) write profile via different code paths with different locks. Last-write-wins with lost data.
2. **TTS file race:** `ai/tts_manager.py` `_stream_speech_to_files` blocks on `done.wait(timeout=self.timeout_seconds)` for 20+ seconds, starving the voice loop of barge-in capability.
3. **Sensor race:** `app_entry.py` reads `profile["runtime_flags"]` dict while sensor monitor callback writes to the same dict via `_apply_sensor_snapshot`. No lock on the dict itself.

---

## PART 3: TOP 5 STRENGTHS (PRESERVE THESE)

### STRENGTH-01 ✅ Security Foundation
Bcrypt + JWT refresh-rotation + blacklist, no eval/exec/pickle, CORS regex validation, Sentry PII scrubbing. `auth/middleware.py` + `api/dependencies.py` are well-structured with proper `Depends()` injection.

### STRENGTH-02 ✅ Test Coverage & CI
80+ test files covering API endpoints, automation registry, idempotency, voice circuit breaker, DB models, scene store, sleep analytics. CI runs ruff, bandit, mypy, gitleaks, pytest. Alembic migrations. Docker Compose with all services.

### STRENGTH-03 ✅ Typed Database Models
`database/models.py` uses SQLAlchemy 2.0 `Mapped` types with proper indexes, FKs, unique constraints. Sync + async dual connection with SQLite fallback for dev.

### STRENGTH-04 ✅ AI Prompt Architecture
5-layer system prompt (persona → engagement → method → session arc → mood → cognitive load → temporal grounding) with token-budget pruning. Three engine backends (Deepgram, Anthropic, LiteLLM) with unified interface.

### STRENGTH-05 ✅ Mobile App Architecture
Riverpod state management, `flutter_secure_storage` with encrypted shared prefs, `go_router` navigation, typed `ApiException` hierarchy, proper session bootstrap with token refresh. `IslamicScreen` is well-structured with error/loading/data states.

---

## PART 4: REALISTIC ACHIEVABILITY

**46 days remaining (30 Jun → 15 Aug). At 3-4 hrs/day = 138-184 productive hours.**

**Realistic MVP for Kuwait kitchen table demo:**
- User registers/logs in via app → backend JWT
- App sets an alarm (basic time + days)
- Raspberry Pi triggers LED wake scene when alarm fires
- "Dana" responds to simple text commands via app chat
- Prayer times display in app (Islamic Mode)
- Basic wind-down: dim lights + play ambient sound

**NOT achievable by 15 Aug:**
- Full voice wake-word pipeline on Pi hardware (microphone/speaker setup varies per room)
- Sleep tracking via pressure sensors (calibration needed per bed)
- Spotify integration (requires Premium + device pairing, unreliable on Pi)
- Partner mode (requires two users + pressure sensing)
- Advanced AI personalities (requires stable API keys + tokens)

**Bottom line:** Focus on auth → alarms → scenes → prayer display → basic chat. Hardware = one LED action only.

---

## PART 5: WEEK-BY-WEEK ROADMAP

### WEEK 0: IMMEDIATE — Privacy & Entrypoint (30 Jun – 6 Jul)
**Objective: Close the security incident and pick one server entrypoint.**

**CRITICAL:**
- **Remove leaked data from git history**
  - `git rm --cached data/manues.db runtime_data/idempotency_store.json`
  - `git filter-repo --path data/manues.db --invert-paths` (or BFG Repo-Cleaner)
  - Verify with `git log --all -- data/` → returns nothing
  - Rotate ALL secrets: JWT SECRET_KEY, Deepgram key, Spotify tokens, Firebase, OAuth
  - Add to `.gitignore`: `data/*.db`, `data/*.sqlite`, `runtime_data/**`, `*.sqlite`, `*.db`
- **Fix OTP HMAC fallback** (`web_server.py:1281`)
  - Remove the `"change-me-in-production"` fallback entirely
  - If `MOBILE_OTP_SECRET` not set AND `SECRET_KEY` not set → `raise RuntimeError` at startup
- **Fix DB URL production guard** (`database/connection.py:48-58`)
  - When `DATABASE_URL` is empty AND `DANAH_ENV=production` → `raise RuntimeError`
  - Only allow SQLite fallback in `development`/`test` environment
- **Pick ONE entrypoint: `api.app_factory:app`**
  - Update `README.md`: `uvicorn web_server:app` → `uvicorn api.app_factory:app`
  - Confirm `.github/workflows/ci.yml` uses `api.app_factory:app` (already does)
  - Confirm `docker-compose.yml` uses `api.app_factory:app` (already does)
  - Comment out `app = FastAPI(...)` in `web_server.py:269` with note: "Handler library only — do not run as entrypoint"
- **Break circular import: `api/routers/chat.py`**
  - Extract handler functions (`ai_chat`, `v1_command`, `ws_chat`, `ws_voice`) from `web_server.py` into `api/handlers/chat_handlers.py`
  - Update `api/routers/chat.py` to import from `api.handlers.chat_handlers` instead of `web_server`

**HIGH:**
- Replace 10 most dangerous `except: pass` blocks with logging (auth flows, profile writes, DB commits)
- Add `SLEEP_HISTORY_PATH` to `config/settings.py` with model_validator resolver

**Test this week:**
- `git log --all -- data/manues.db` returns nothing
- App starts with `uvicorn api.app_factory:app` without importing `web_server.py` directly
- OTP HMAC raises RuntimeError when no secret configured in production mode
- DB connection raises RuntimeError on empty DATABASE_URL in production mode

---

### WEEK 1: Backend Stabilization (7 Jul – 13 Jul)
**Objective: All mobile app calls work end-to-end.**

**CRITICAL:**
- **Migrate remaining handler functions out of `web_server.py`**
  - `ai_chat()` → `api/handlers/chat_handlers.py`
  - `v1_command()` → `api/handlers/command_handlers.py`
  - `ws_chat()` / `ws_voice()` → `api/handlers/websocket_handlers.py`
  - `/v1/bed/state`, `/v2/bed/state` → `api/routers/devices.py`
  - `/v1/scenes/compose` → `api/routers/scenes.py`
  - After: `web_server.py` only contains Pydantic models (`ChatRequest`, `CommandRequest`, `BedStateV2State`, etc.)
- **Unify profile write paths**
  - ALL profile writes → `Storage.user_profile.save_profile()` with `_profile_rw()` lock
  - Remove `_save_profile()` / `_save_profile_unlocked()` from `web_server.py`
  - `main.py`, `app_entry.py`, `automation_engine.py` all import the SAME `save_profile` with the SAME lock
- **Unify LED controller**
  - Keep `led/led_control.py` as canonical `LEDController`
  - Move `apply_led_hardware_config()` and `apply_music_led_preferences()` INTO `led/led_control.py`
  - Delete root `led_controller.py`
- **Unify automation engine**
  - Use `automations.registry.AutomationRegistry` as canonical
  - Root `automation_engine.py` → thin wrapper calling into `automations/` package

**HIGH:**
- **Migrate Flutter API calls to single client**
  - All screens → `SmartBedApi` from `api_client.dart`
  - Remove `ApiService` static methods (or make them delegate to `SmartBedApi`)
  - Unify token: only `SessionStore` (key: `smart_bed.mobile_auth_session`)

**Test this week:**
- Full auth: register → login → protected route → refresh → logout
- Alarm CRUD via mobile app
- Scene activation: preview + apply
- Verify ONE profile write path (no race between voice loop and web server)
- Full pytest suite; target 80% pass rate

---

### WEEK 2: Hardware MVP (14 Jul – 20 Jul)
**Objective: One hardware feature that works reliably.**

**CRITICAL:**
- **Confirm single Spotify implementation**
  - Canonical: `ai/spotify_manager.SpotifyManager`
  - Remove root `spotify/spotify_client.py` and `spotify/spotify_controls.py` from `master_controller.py` imports
  - Rewire `master_controller.py` to use `ai/spotify_manager` if any hardware trigger still needs it
- **Wire ONE Pi-triggerable hardware action**
  - Path: app → `/v1/mobile/device-commands` (action: `"optimize_room"`) → `commands/lights.py` → `LEDController` → GPIO
  - Test: set alarm → trigger → LED strips react with warm breathing scene
  - Keep ONE scene: sleep-optimized = warm color, brightness 0.2, breathing animation
- **Document Pi setup for Kuwait deployment**
  - `docs/HARDWARE_SETUP.md`: GPIO pinout (18=user, 13=state), power supply, WiFi, SSH from shop network
  - Include: pre-demo checklist (LED connected? Power on? Same WiFi?)
  - Include: recovery procedure (reboot, restart voice service)

**HIGH:**
- Do NOT connect pressure sensors, motion sensors, or MAX30102
- Do NOT attempt voice wake-word on Pi hardware (too unreliable for MVP)
- Test full flow: app → API → alarm set → (simulate fire) → LED changes

**Test this week:**
- Desktop: `docker-compose up` → app connects → set alarm → trigger → LED changes
- Simulate "no Pi connected": app shows "hardware offline" but alarm still shows correct time
- Verify `master_controller.py` does NOT crash import even if `spotify/` or `dana/` have issues

---

### WEEK 3: Stability & Polish (21 Jul – 27 Jul)
**Objective: Everything that worked in tests still works when all systems connect.**

**CRITICAL:**
- **Fix top 20 `except: pass` blocks**
  - Priority: auth flows, profile writes, DB commits, alarm triggers, TTS writes
  - Pattern: `except Exception as exc: logger.warning("context: {}", exc)`
- **Replace all `print()` with `logger.info()`**
  - `automation_engine.py` line 235: `print(f"[REMINDER]...")` → `logger.info(...)`
- **Fix DateTime consistency**
  - All stored timestamps = UTC ISO strings
  - All comparisons = UTC datetimes
  - `web_server.py` uses `ensure_utc`/`from_iso`/`to_iso` from `time_utils.py` — correct
  - `app_entry.py` uses `datetime.now()` (naive) in some places — fix to `datetime.now(timezone.utc)`

**HIGH:**
- **Test on actual Android device** (not just emulator)
  - `flutter build apk --debug` → install → test register/login/set alarm/activate scene/Islamic screen
  - Test offline mode: no crash, shows cached data
  - Test poor network: timeouts handled gracefully
- **Verify `config/production.py` CORS** allows only known origins

**Test this week:**
- Full E2E flow (app → API → DB → LED) 10x in sequence
- Full pytest suite; fix all failures
- App behavior: no network → network restored
- Session persistence: app restart → still logged in

---

### WEEK 4: Freeze & Deployment Prep (28 Jul – 3 Aug)
**Objective: No new features. Bug fixes and deployment dry-runs only.**

**CRITICAL:**
- **Feature freeze.** No new routes, screens, or features.
- **Bug bash:** Run every user-facing flow 3x. Log every crash. Fix only P0/P1.
- **Deployment dry-run #1**
  - Build Docker: `docker-compose build`
  - `docker-compose up` on test machine (NOT dev box)
  - Verify: API responds, DB connects, Redis connects, Prometheus at `/metrics`
- **Prepare deployment docs**
  - One-page: "How to deploy" (Docker commands, env vars, port forwarding)
  - One-page: "How to demo" (3-min walkthrough for furniture shop)
  - One-page: "How to recover" (Pi offline, app crash, API slow)

**HIGH:**
- API p95 latency < 500ms for all routes
- Mobile app startup < 3 seconds to first screen
- Demo mode fallback: if Pi unavailable, app still functions; LED commands return "success" without hardware

---

### WEEK 5: Buffer & Final Polish (4 Aug – 10 Aug)
**Objective: Handle every failure mode gracefully.**

**CRITICAL:**
- **Error message audit**
  - Every API error returns user-friendly message
  - No raw Python tracebacks reach mobile app
  - No raw DB error strings reach mobile app
- **Offline mode test**
  - Launch app → turn off WiFi → verify behavior
  - Turn WiFi back on → verify data syncs
- **Session expiry test**
  - Let session expire → app handles 401 → auto-refresh → or prompts re-login
- **Prepare `.env` for deployment**
  - `SECRET_KEY`: 32+ chars, not default
  - `POSTGRES_PASSWORD`: set
  - `DEEPGRAM_API_KEY`: valid
  - All Firebase/Dana credentials: valid

**HIGH:**
- Backup procedure: `pg_dump` command, schedule
- Monitoring: Prometheus dashboards load, add one alert ("5xx for 5+ minutes")

---

### WEEK 6: DEPLOYMENT WEEK (11 Aug – 15 Aug)

**MON 11 Aug: Final freeze — NO CODE CHANGES after this point.**
- Copy deployment config to Pi
- Build Docker images
- Push to deployment target

**TUE 12 Aug: Deploy to test environment**
- `docker-compose up -d` on test Pi
- Run all E2E tests against live system
- Fix ONLY if completely broken

**WED 13 Aug: Install at Kuwait furniture shop**
- Connect Pi to shop WiFi
- Start Docker Compose
- Pair display phone/tablet
- Run demo script

**THU 14 Aug: Full dress rehearsal**
- Do the demo 5 times
- Fix issues found (document but don't over-engineer)

**FRI 15 Aug: GO LIVE**
- Demo day. The bed is in the shop. Dana is live.

---

## PART 6: GUIDED LEARNING PLAN (TIED TO YOUR CODE)

| Topic | Why It Matters | Files to Study / Apply |
|-------|---------------|------------------------|
| **Structured logging & error handling** | 178 `except: pass` blocks make debugging impossible | `web_server.py`, `voice_handler.py`, `mobile_app/lib/services/api_service.dart` — replace every `catch (_){}` with `logger.warning()` |
| **Circular imports and module layering** | Router → web_server → main → voice_handler → ai/* crashes API when any leaf fails | Learn: Python import system, `if TYPE_CHECKING:`, lazy imports, module layering. Apply to: `api/routers/chat.py`, `api/app_factory.py`, `web_server.py` |
| **Thread safety and locking** | Profile writes race between HTTP threads and voice loop. TTS files race between synthesis and playback. | `web_server.py` `_PROFILE_RW_LOCK` (good), `ai/tts_manager.py` `_write_lock` (good). Apply locks to: `app_entry.py` `_apply_sensor_snapshot`, `automation_engine.py` `planned_reminders` |
| **Database migration hygiene** | `database/connection.py` has DIY `_ensure_schema_version()`. Should use Alembic. | `alembic/`, `database/models.py`, `database/connection.py`. Learn: `alembic revision --autogenerate`, upgrade/downgrade |
| **REST API design and layering** | `web_server.py` is 409 KB. `api/routers/` migration is half-done. | Study: `api/routers/auth.py` (clean), `api/routers/scenes.py` (clean). Apply to: extract every handler from `web_server.py` |
| **Flutter state ownership** | Two auth state systems: `AuthController` (Riverpod) vs `ApiService` (static keystore). If they disagree, inconsistent state. | `mobile_app/lib/src/state/auth_controller.dart`, `mobile_app/lib/services/api_service.dart`, `mobile_app/lib/src/core/session_store.dart` |
| **Git hygiene & branch protection** | `.gitignore` has entries but files are still tracked (`.vscode/`, `desktop.ini`) | `.gitignore`, `.gitignore.txt`. Learn: `git rm --cached`, tracked vs ignored files |
| **Configuration management** | `config/settings.py` is excellent but `web_server.py` has hardcoded paths bypassing it | `config/settings.py` (study validators), `config/production.py`. Apply: add every path constant to settings |
| **API contract stability** | Mobile app calls `/v1/bed/status`, `/v1/bed/lighting` — but canonical backend uses `/v1/mobile/alarms`, `/v1/scenes/compose` | `mobile_app/lib/services/api_service.dart` (old paths), `api/routers/` (new paths). Learn: API versioning, OpenAPI schema diff |
| **Process supervision for Pi** | Docker Compose works on server, but Pi needs auto-restart, log rotation, disk monitoring | `docker-compose.yml`, `Dockerfile`. Learn: systemd service files, Docker restart policies, logrotate |

---

## PART 7: CRITICAL PRE-DEPLOYMENT CHECKLIST

| # | Action | File(s) | Status |
|---|--------|---------|--------|
| 1 | Remove leaked data from git history | `data/manues.db`, `runtime_data/**` | ⬜ NOT STARTED |
| 2 | Rotate ALL secrets | `.env`, Firebase, Deepgram, Spotify, OAuth | ⬜ NOT STARTED |
| 3 | Fix OTP HMAC fallback | `web_server.py:1281` | ⬜ NOT STARTED |
| 4 | Fix DB URL production guard | `database/connection.py:48` | ⬜ NOT STARTED |
| 5 | Choose ONE entrypoint: `api.app_factory:app` | `README.md`, `web_server.py:269`, `ci.yml` | ⬜ NOT STARTED |
| 6 | Extract handlers from `web_server.py` → `api/routers/` | `web_server.py`, `api/routers/chat.py` | ⬜ NOT STARTED |
| 7 | Unify profile write paths | `web_server.py`, `app_entry.py`, `automation_engine.py` | ⬜ NOT STARTED |
| 8 | Delete root `led_controller.py`; consolidate into `led/led_control.py` | `led_controller.py` (root) | ⬜ NOT STARTED |
| 9 | Unify Flutter API client: use `SmartBedApi` everywhere | `mobile_app/lib/services/api_service.dart` | ⬜ NOT STARTED |
| 10 | Fix `master_controller.py` → use `ai/spotify_manager` | `master_controller.py` | ⬜ NOT STARTED |
| 11 | Add `SLEEP_HISTORY_PATH` to `config/settings.py` | `config/settings.py`, `web_server.py:77` | ⬜ NOT STARTED |
| 12 | Protect `api/routers/chat.py` from importing `web_server.py` | `api/routers/chat.py` | ⬜ NOT STARTED |
| 13 | Top 20 `except: pass` → `logger.warning()` | All files | ⬜ NOT STARTED |
| 14 | Test full auth flow on real Android device | Mobile app | ⬜ NOT STARTED |

---

## PART 8: "NOT MY JOB" — WHAT TO SKIP ENTIRELY FOR MVP

Do NOT spend time on these before 15 August:

| Item | Why Skip | When to Revisit |
|------|----------|-----------------|
| `dana/` package (core, personality, guide, coach, therapist) | Legacy architecture. Superseded by `ai/adaptive_personality_engine`, `ai/personality_runtime`. | Post-launch |
| `spotify/` package (root-level) | Superseded by `ai/spotify_manager`. Duplicate. | Post-launch |
| `guest_mode/` package (full implementation) | Not wired into current flow. `guest_manager.is_active()` only checked in `master_controller.py`. | Post-launch |
| `partner/` package | Requires pressure sensors + two users. | Phase 2 |
| `health/` package (stress, hydration, weekly report) | Nice-to-have. No mobile screen consumes it yet. | Phase 2 |
| `gamification/` package | Achievements logic exists but no UI consumes it. | Phase 2 |
| `integrations/` (calendar sync, geofence, fitness) | Garmin/Fitbit/Google require external accounts. Not demo-able without credentials. | Phase 2 |
| `ai/speaker_diarization.py` | Requires HF_TOKEN + pyannote model. Overkill for MVP. | Phase 2 |
| `ai/pgvector_memory_index.py` | Requires pgvector Postgres extension. | Phase 2 |
| `ai/activity_predictor.py` | ML-based activity prediction. Not wired in. | Phase 2 |
| `ai/automation_learning_engine.py` | Learns from automation feedback. No UI to rate automations yet. | Phase 2 |
| `ai/personality_evolution.py` | Long-term relationship tracking. Not wired in. | Phase 2 |
| Voice wake-word on Pi | Unreliable in noisy furniture shop. Use app-based activation. | Phase 2 |
| **Python 3.12 in Docker** | Codebase has C extensions compiled for Python 3.11 (`cpython-311` pyc). Docker uses `python:3.12-slim`. **This will break on Pi.** | **Immediately — change Dockerfile to `python:3.11-slim`** |

---

## PART 9: 3-MINUTE DEMO SCRIPT FOR KUWAIT FURNITURE SHOP

**Customer sees:** A phone controlling bed lights and alarms.  
**What runs under the hood:** Python API on Raspberry Pi + Flutter app + PostgreSQL + LED strips.

**Walkthrough:**

1. **"This is Danah, your smart bed assistant."** (Open app → profile visible)
2. **"You set your wake-up time here."** (Tap Alarms → "6:00 AM, every day, LED sunrise")
3. **"When that time comes, the bed lights up gently — no jarring alarm."** (Tap Scenes → preview "Calm Recovery" → lights dim and breathe)
4. **"The app also shows you prayer times for Kuwait."** (Tap Islamic → today's prayers, next prayer countdown, hadith)
5. **"And you can ask Dana anything about your sleep."** (Tap Chat → "How did I sleep?" → Dana responds with sleep summary)

**Demo fallback if Pi is offline:** App functions fully. LED commands show "success" without hardware. Customer sees the app experience.

---

*End of deployment readiness document. This is your source of truth. Update it as tasks are completed. Next step: start WEEK 0, task 1 — remove leaked data from git history.*
