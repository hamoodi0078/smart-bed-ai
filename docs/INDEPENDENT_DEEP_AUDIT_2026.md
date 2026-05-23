# Smart Bed AI (Danah) — Independent Deep Audit & Brutal Honest Review

> **Audit Date:** May 22, 2026  
> **Auditor:** Independent code review (no prior audit bias)  
> **Scope:** Python backend, Flutter mobile app, Raspberry Pi hardware, DevOps  
> **Method:** Direct source code inspection — no documentation reliance

---

## Executive Honest Summary

**This project is NOT ready for production deployment.** It has a committed `.env` file containing live API keys, wide-open admin endpoints with zero authentication, a mobile app configured for the wrong backend port, and hardcoded fake metrics in the admin dashboard. The codebase shows genuine engineering effort — 54 AI modules, a real voice pipeline, proper database schema, and Docker orchestration — but the security posture is catastrophic and the architectural migration is half-finished. If deployed as-is, anyone on the internet can access your admin panel, delete users, view billing data, and reset the voice circuit breaker. You are approximately **4–6 weeks of focused work** away from a safe v1.0, not the "75% complete" your fixing plan claims.

---

## Connectivity Map: Is Everything Connected?

```
Mobile App (Flutter)        Backend (FastAPI)           Database / Infra
        |                            |                             |
        |  HTTP / Bearer Token       |                             |
        |---------------------------->|                             |
        |  PORT MISMATCH (8001 vs    |                             |
        |  8000) — BROKEN by default |                             |
        |                            |  SQLAlchemy + Alembic       |
        |                            |---------------------------->|
        |                            |  PostgreSQL / SQLite        |
        |                            |  (connected, schema good)   |
        |                            |                             |
        |                            |  Deepgram / OpenAI / Redis  |
        |                            |  (connected, KEYS EXPOSED)  |
        |                            |                             |
        |  NO offline handling       |  voice_handler.py           |
        |  NO connectivity awareness |  app_entry.py               |
        |                            |  (connected, 50+ imports) |
        |                            |                             |
Raspberry Pi Hardware          GPIO / MQTT
        |                            |
        |  pi_sensors.py             |
        |  (connected with fallback) |
```

**Verdict on connectivity:** The backend internal modules are mostly connected. The mobile-to-backend link is **broken by default** due to a port mismatch. The hardware bridge is properly designed with fallbacks. The biggest disconnect is **security**: the auth middleware exists but is wired to NOTHING.

---

## Category Scores

| Layer | Score | Why |
|-------|-------|-----|
| **Security** | **15/100** | Live API keys in repo. Admin router completely unprotected. JWT middleware exists but unused. |
| **Architecture** | **45/100** | `web_server.py` still 10,307 lines. Dual server confusion. Some routers migrated, most delegate back to monolith. |
| **Code Quality** | **60/100** | Type hints present, structured logging good, error hierarchy exists. But duplicated utils, mid-file imports, massive files. |
| **AI / Voice** | **65/100** | Real STT fallback chain, circuit breaker functional, TTS persona switching works. No prompt injection tests. |
| **Database** | **75/100** | Proper SQLAlchemy models, 28 tables, Alembic migrations, pgvector support. Alarm model finally migrated. |
| **Mobile App** | **50/100** | Good exception types, secure token storage. No offline mode. Wrong port. Uses web auth endpoints. |
| **Hardware / IoT** | **70/100** | NoopSensorMonitor fallback is correct. GPIO abstraction present. No mock for dev on Windows. |
| **DevOps / Deploy** | **55/100** | Docker Compose is solid. Dockerfile reasonable. But `.env` committed breaks any deployment. CI unknown. |
| **Testing** | **50/100** | 90 test files exist, but they test the legacy `web_server.py`. Zero tests for migrated router security. |
| **Documentation** | — | Skipped per your request. |

**Overall: 48/100 — Not production ready.**

---

## Critical Issues (Deploy = Data Breach)

### C-01 — `.env` Committed with Live Production Secrets
- **Files:** `.env` (committed despite `.gitignore` rule)
- **What:** The repository contains a `.env` file with real, active API keys:
  - `DEEPGRAM_API_KEY=c499573040486e01ba4a400bc346a70115808e4e`
  - `OPENAI_API_KEY=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`
  - `SPOTIFY_CLIENT_SECRET=13bd91ea2df645379bafe3326b6d0fde`
  - `MOBILE_SOCIAL_GOOGLE_CLIENT_ID=296114385571-s0e9p8rhillmr298b4lca63a762ee2ue.apps.googleusercontent.com`
  - `MOBILE_SOCIAL_FACEBOOK_APP_ID=895970409914868`
- **Impact:** Anyone with read access to this repo (or its history) can use your Deepgram credits, burn your OpenAI quota, and impersonate your Spotify/Google/Facebook apps.
- **Fix:** `git rm --cached .env`, rotate ALL keys immediately, add `git-secrets` or `trufflehog` to CI.

### C-02 — Admin Router Is Completely Unprotected
- **File:** `api/routers/admin.py` (all 256 lines)
- **What:** Not a single route in the migrated admin router uses `Depends(get_current_user)` or `Depends(require_role("admin"))`. Every endpoint (`/v1/admin/users`, `/v1/admin/diagnostics`, `/v1/admin/actions`, `/v1/admin/voice/circuit-breaker/reset`) is **world-accessible**.
- **Impact:** Any HTTP client can list all users, view runtime diagnostics, execute admin actions, and reset the voice circuit breaker without authentication.
- **Fix:** Add `dependencies=[Depends(require_role("admin"))]` to the `APIRouter` constructor on line 43.

### C-03 — No Migrated Router Uses the New JWT Middleware
- **Files:** `api/routers/*.py` (all 17 router files)
- **What:** `auth/middleware.py` contains a fully implemented `get_current_user` and `require_role`. A grep across all `api/routers/` for these functions returns **zero imports**. The auth code exists but is wired to nothing.
- **Impact:** The "new" auth system is a phantom. All migrated routers fall back to legacy `_mobile_user(request)` from `web_server.py` (if they check auth at all).
- **Fix:** Import and apply `get_current_user` to every router that handles user data.

### C-04 — Mobile App Default Port Mismatches Backend
- **File:** `mobile_app/lib/src/config/app_config.dart`
- **What:** The Flutter app defaults to port `8001` (`http://127.0.0.1:8001`), but the backend FastAPI server runs on port `8000`. The `docker-compose.yml` exposes `8000:8000`. There is no service on 8001.
- **Impact:** The mobile app cannot connect to the backend out of the box. A new developer will spend hours debugging why "nothing works."
- **Fix:** Change `8001` to `8000` in `app_config.dart`.

---

## High Priority Issues

### H-01 — Hardcoded Fake Metrics in Admin Dashboard
- **File:** `web_server.py:8683-8684`
- **What:** `admin_overview` returns literally hardcoded integers:
  ```python
  "registered_users": 1248,
  "active_beds": 876,
  ```
- **Impact:** The admin panel shows fake data. This is either placeholder code that was never replaced, or intentional deception.
- **Fix:** Query the actual `User` and `Bed` tables.

### H-02 — `web_server.py` Is Still a 10,307-Line Monolith
- **File:** `web_server.py` (full_length: 10307)
- **What:** Despite claims in `IMPLEMENTATION_PLAN.md` and `FIXING_PLAN.md` that this is being decomposed, the legacy file still contains the vast majority of routes, inline business logic, direct database calls, and global mutable state (`_DB_CONNECTION`, `_CHAT_ENGINES`, `_PROFILE_RW_LOCK`).
- **Impact:** Impossible to unit test, review, or maintain. A single typo can break hundreds of routes.
- **Fix:** This file needs to be deleted, not maintained. All routes must be extracted.

### H-03 — Dual Server Architecture Creates Routing Conflicts
- **File:** `api/app_factory.py:239-240`
- **What:** `app_factory.py` mounts `web_server.py` as a catch-all sub-app:
  ```python
  from web_server import app as _legacy_app
  application.mount("/", _legacy_app)
  ```
- **Impact:** Both servers register routes on `/`. The "migrated" routers take priority, but anything unmatched falls through to the legacy app. This means the admin routes in `app_factory.py` (unprotected) shadow the legacy admin routes (protected by `_require_admin`). The result: **protection is stripped during migration.**
- **Fix:** Remove the legacy mount. Finish the migration first.

### H-04 — Mobile App Has Zero Offline Handling
- **Files:** `mobile_app/lib/services/api_service.dart`, `mobile_app/lib/`
- **What:** A grep for `offline`, `connectivity`, `noInternet`, or `retry` across the entire Flutter codebase returned **zero results**.
- **Impact:** If the user's phone loses signal, the app will crash or hang on every API call. No cached data, no queue-and-retry.
- **Fix:** Add `connectivity_plus`, implement a request queue, and cache critical data (user profile, alarms, scenes).

### H-05 — Mobile App Uses Web Auth Endpoints Instead of Mobile Ones
- **File:** `mobile_app/lib/services/api_service.dart:92-99`
- **What:** The Flutter app calls `/v1/auth/register` and `/v1/auth/login` (cookie-based web routes) instead of `/v1/mobile/auth/register` and `/v1/mobile/auth/login` (Bearer-token mobile routes). The mobile routes exist and are better suited for Flutter.
- **Impact:** The mobile app gets session cookies instead of JWT Bearer tokens, creating auth inconsistency between web and mobile.
- **Fix:** Switch to `/v1/mobile/auth/*` endpoints.

### H-06 — Massive Import-Time Side Effects in `app_entry.py`
- **File:** `app_entry.py` (lines 1–163)
- **What:** The main voice runtime entry point imports **50+ AI modules at the top of the file** before `main()` is even called. Every module is instantiated eagerly in `main()` with no lazy loading.
- **Impact:** Cold start is slow. If any single module fails to import (e.g., `gpiozero` missing on a dev machine), the entire voice runtime crashes.
- **Fix:** Move imports inside `main()` or factory functions where possible.

---

## Medium Priority Issues

### M-01 — `alarms.py` Router Still Delegates Auth to `web_server`
- **File:** `api/routers/alarms.py:59-67`
- **What:** `_get_user_id` calls `_mobile_user(request)` from `web_server` instead of using the new `get_current_user` dependency.
- **Impact:** The alarm router is "migrated" but still tightly coupled to the monolith for auth.

### M-02 — `voice_handler.py` Duplicates Utility Functions from `main.py`
- **Files:** `voice_handler.py`, `main.py`, `app_entry.py`, `scene_manager.py`
- **What:** Functions like `normalize_for_intent()`, `has_any()`, `wants_detailed_answer()`, `clamp_non_detail_response()` exist in multiple files.
- **Impact:** Bug fixes in one copy don't propagate. Divergence over time.

### M-03 — `config/settings.py` Default Secret Key Is Weak
- **File:** `config/settings.py:64-89`
- **What:** Default `secret_key` is `"change-me-in-production"`. The validator warns in dev but only errors in production. If someone deploys without setting `SECRET_KEY`, JWT tokens are trivially forgeable.
- **Impact:** Forgotten env var = complete auth bypass.

### M-04 — Docker Build Copies `.env` into Image
- **File:** `Dockerfile:16`
- **What:** `COPY . .` copies the entire repo, including `.env`, into the Docker image.
- **Impact:** Even if you fix the Git history, the Docker image layers still contain the secrets.

### M-05 — No Rate Limiting on Admin Routes
- **Files:** `api/routers/admin.py`, `web_server.py`
- **What:** While `app_factory.py` installs `RateLimitMiddleware`, admin routes that do heavy aggregation (`/v1/admin/observability`, `/v1/admin/users`) have no per-endpoint rate limits.
- **Impact:** An attacker can DDoS the admin panel or scrape the entire user database.

### M-06 — `SpeakerDiarization` and `VadFilter` Imports Are Fragile
- **File:** `ai/stt_manager.py:58-77`
- **What:** Multiple nested `try/except` blocks with fallback imports (`ai.speaker_diarization` → `speaker_diarization`). This is brittle and hard to debug.
- **Impact:** Import errors are silently swallowed. You won't know diarization is missing until it fails at runtime.

### M-07 — Tests Cover Legacy Code, Not Migrated Routers
- **Files:** `tests/test_web_auth_flows.py`, `tests/test_scene_endpoints.py`
- **What:** Tests import `web_server` directly and patch its globals. They do not test the migrated `api/routers/` files.
- **Impact:** The migrated admin router being completely unprotected is not caught by any test.

---

## Low Priority Issues

### L-01 — `Bed.is_stale` Uses Naive `replace(tzinfo=timezone.utc)`
- **File:** `database/models.py:70`
- **What:** `self.last_seen.replace(tzinfo=timezone.utc)` forcibly replaces the timezone without converting. If `last_seen` was stored in a different timezone, the comparison is wrong.
- **Fix:** Use `ensure_utc()` or `astimezone(timezone.utc)`.

### L-02 — `web_server.py` CORS Origins Are Parsed at Import Time
- **File:** `web_server.py:127-129`
- **What:** `ALLOWED_ORIGINS` is computed when the module is imported, not per-request. This prevents dynamic config reloading.

### L-03 — `acoustic_echo_guard.py` Is Only 718 Bytes
- **File:** `ai/acoustic_echo_guard.py`
- **What:** Likely a minimal stub. Needs review for real echo cancellation logic.

### L-04 — `barge_in_monitor.py` Is Only 1,341 Bytes
- **File:** `ai/barge_in_monitor.py`
- **What:** Small file. Verify it actually detects barge-in or just logs.

---

## What the Previous Audit Missed or Softened

| Finding | Previous Audit | Reality |
|---------|---------------|---------|
| Admin router protection | Did not flag as critical | **Completely missing** — not a gap, a total absence |
| `.env` in repo | Not mentioned | **Live keys exposed** — catastrophic operational risk |
| Mobile app port | Not mentioned | **8001 vs 8000** — broken by default |
| JWT middleware usage | Implied auth was "implemented" | **Exists but unused** — phantom code |
| Hardcoded admin metrics | Not mentioned | **Fake numbers in production endpoint** |
| Mobile offline handling | Not mentioned | **Zero implementation** |
| Web vs mobile auth endpoints | Not mentioned | **App uses wrong endpoints** |
| `app_entry.py` imports | Mentioned as "less severe" | **50+ eager imports** — severe for Pi cold start |

---

## Deployment Readiness Verdict

### Can you deploy this today? **NO.**

**Why not:**
1. **Active secret exposure** — anyone can steal your API keys from Git history.
2. **Unprotected admin surface** — anyone can access `/v1/admin/users`, `/v1/admin/actions`, etc.
3. **Mobile app won't connect** — wrong port means no users can use the Flutter client.
4. **Fake metrics** — the admin dashboard lies to you.

### What is the real timeline to v1.0?

| Sprint | Focus | Duration |
|--------|-------|----------|
| 1 | Rotate all secrets, purge `.env` from Git history, audit GitHub for leaks | 1–2 days |
| 2 | Wire `auth.middleware` into ALL migrated routers, delete unprotected admin routes | 3–5 days |
| 3 | Fix mobile app port, switch to mobile auth endpoints, add offline handling | 1 week |
| 4 | Finish `web_server.py` decomposition, remove legacy mount | 2–3 weeks |
| 5 | Replace hardcoded metrics, add per-endpoint rate limits, load testing | 1 week |
| 6 | End-to-end testing, security review, penetration test | 1 week |

**Realistic total: 6–8 weeks for a safe production deployment.**

---

## What Is Genuinely Impressive

Despite the harsh review, there is real engineering here:
- **Database schema is well-designed** — 28 models, proper indexes, foreign keys, JSON columns where appropriate. The migration from JSON files to SQLAlchemy is largely complete.
- **Voice pipeline has real resilience** — STT fallback chain (Deepgram → faster-whisper → local), circuit breaker with state machine, noise reduction, loudness normalization.
- **Hardware abstraction is correct** — `NoopSensorMonitor` means the code won't crash on a developer's Windows laptop.
- **Auth service layer is solid** — bcrypt with 12 rounds, refresh token rotation, token revocation. It's just not wired to the routers.
- **Docker Compose is production-minded** — health checks, resource limits, dependency ordering, separate voice worker.

The foundation is good. The wiring is dangerously incomplete.

---

## Action Items — Do These in Order

1. **TODAY:** `git rm --cached .env` + rotate ALL API keys.
2. **TODAY:** Add `dependencies=[Depends(require_role("admin"))]` to `api/routers/admin.py` line 43.
3. **This week:** Audit every `api/routers/*.py` file and add `Depends(get_current_user)` where user data is accessed.
4. **This week:** Change `mobile_app/lib/src/config/app_config.dart` port from `8001` to `8000`.
5. **This week:** Replace hardcoded metrics in `web_server.py:8683-8684` with real DB queries.
6. **Next 2 weeks:** Finish extracting all routes from `web_server.py` and delete the legacy mount.
7. **Next 2 weeks:** Add offline handling to the Flutter app (`connectivity_plus`, request queue, local caching).
8. **Before deploy:** Run `trufflehog` or `git-secrets` scan on the entire repo history.

---

*End of audit. This document reflects the actual state of the codebase as of May 22, 2026. No sugar-coating, no assumptions, only what the code reveals.*
