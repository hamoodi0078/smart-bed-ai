# Design: Smart Bed — 55% → 90%+ Production Readiness

- **Date:** 2026-07-08
- **Status:** Approved by Danah (2026-07-08), pending spec review
- **Source of truth for findings:** `audit.md` (repo root, 2026-07-08 audit)
- **Timeline:** No fixed date — priority order, as fast as possible. Danah and Claude are the only two working on this project, through deployment.

## 1. Problem statement

The 2026-07-08 audit scored the project ~55% production-ready. The systemic root cause: the router
migration from `web_server.py` (10,995 lines) to `api/app_factory.py` was declared done but never
re-verified end-to-end. Production serves the new dialect; the Flutter app, admin panel, and 29 test
files still speak the old one. All three P0s live on that seam. Secondary causes: per-process JSON
stores that corrupt under multi-worker gunicorn, and simulated hardware paths presented as real.

**Goal:** close every audit finding (P0/P1/P2, duplicates, dead code, decorative screens,
localization), wire the six decorative Flutter screens to real backends, build the bed-side hardware
bridge (simulated-testable), and deploy to Railway + Neon. Target: ≥90% on a re-audit against the
original `audit.md` checklist.

## 2. Hard constraints (from Danah)

1. **`web_server.py` deletion gate:** do NOT delete `web_server.py` until (a) zero imports of it
   remain anywhere, (b) all migrated services are live in production wiring, and (c) the contract
   suite is green.
2. **Deployment ordering:** deployment work starts only after the core contract, state, and auth
   fixes (Phases 0–3) are stable.
3. Solo project: small, green commits to `main`. Every commit passes tests + `flutter analyze`.
4. No feature cuts — decorative screens get wired, not deleted (Danah: "wire them with each and
   everything, I want this project flawless").

## 3. Non-goals

- Real-hardware verification (LED strips, sensors, microphone/speaker) — happens on the Pi in
  Kuwait. Everything bed-side here is verified against the simulated LED backend.
- Voice/wake-word pipeline work (separate track, already committed in `3dcecf2`).
- New product features beyond wiring what the UI already promises.

## 4. Target architecture

### 4.1 Backend

- **One FastAPI app:** `api/app_factory.py`. `web_server.py` ends at zero lines of responsibility
  (then deleted, per constraint 1).
- **Services layer:** implementations move out of `web_server.py` into `services/` modules
  (pattern: `services/auth_service.py`). Routers call services directly — no lazy
  `from web_server import …` inside request handlers.
- **One of each:** one Sentry init (app_factory lifespan); one service registry
  (`api/service_registry.py`, `core/service_registry.py` merged in); one retry framework
  (`core/retry.py` wins, `utils/retry.py` deleted); one task queue (arq; celery deleted); one
  admin route registration (dedupe `auth.py`/`admin.py` overlap).
- **Dead code deleted:** `master_api.py`, `master_controller.py`, `fix_db_schema.py`,
  `sanity_checks.py`, `pack_code.py`, `manual_email_test.py`, `test_whatsapp.py`,
  `print_sendgrid_env.py` (prints SendGrid key — delete first), `main.py` shim.

### 4.2 State model — Postgres is the single source of truth

All mutable state moves to DB tables via Alembic migrations:

| State | Today | Target |
|---|---|---|
| Web/admin cookie sessions | `SubscriptionStore` JSON, per-process | `web_sessions` table |
| Checkout sessions | same JSON | `checkout_sessions` table |
| PayPal idempotency keys | same JSON | `billing_idempotency` table |
| Profile prefs | split-brain: DB `user_profile_prefs` + JSON `web_profile_prefs` | `ProfileRepository` only; readers read through it |
| Alarms | two systems (DB + JSON) | `AlarmRepository` only; JSON alarm handlers deleted |
| Undo tokens | per-process `UndoManager` | Redis (TTL) with DB fallback |
| Rate limiting | Redis, per-process fallback | unchanged; fallback behavior documented |

- **One-time migration script** imports existing JSON store data (profiles, sessions,
  subscriptions) into the DB; runs idempotently; JSON files retired afterward.
- **One `DatabaseConnection` singleton** at module level, injected into repositories. No
  engine-per-request anywhere (alarms router, OTP, `/readyz`).
- After this lands: `GUNICORN_WORKERS` back to 4 in compose/nixpacks.

### 4.3 Contract & auth fixes

- **Alarms (P0-1):** backend adopts the app's contract: `alarm_id`, `days` 1–7, list-shaped POST
  response. Fixed in `api/routers/alarms.py` first (~30 lines), folded into `AlarmService` in
  Phase 3. Alarm *triggering* for mobile-created alarms: served by the bed-side poller (§4.5)
  reading `AlarmRepository` — one alarm store, one trigger path.
- **Admin (P0-2):** panel stays cookie-based. Admin router gets a cookie-session guard backed by
  the `web_sessions` table. JWTs additionally gain a `role` claim so `require_role` works for
  API clients.
- **Profile (P0-3):** prayer times, Islamic overview, dashboard, and chat resolve profile via
  `ProfileRepository` first (JSON fallback during transition, removed in Phase 3). The app's
  GPS location (auth_controller) drives prayer times; Kuwait City remains only as a final default.
- **Revoked tokens (P1-6):** `get_current_user` validates against the DB revocation flag
  (`MobileAuthRepository.validate_access_token`), matching the legacy `_mobile_user` behavior.
- **Event-loop blockers (P1-7):** every async wrapper that calls sync monolith code becomes plain
  `def` (FastAPI threadpool) or awaits `asyncio.to_thread`: `/v1/command`, undo ×2, push-token,
  first-3-nights, admin login (bcrypt), all three scene POSTs.
- **P2 batch:** dashboard/timeline GETs stop writing on read; chat SSE streams for real
  (chunk-by-chunk emit); wrapper-pattern `ValidationError` → 422 and `ValueError` messages no
  longer echoed to clients; prayer times / Islamic overview become free-tier; entrypoint aborts on
  Alembic failure (remove `|| true`-style continue in `scripts/docker-entrypoint.sh`);
  `create_tables()` paper-over removed — Alembic is the only schema authority;
  `validate_production_secrets` blocks boot in production; `main.save_profile` and Flutter
  `ApiService.saveToken` exception swallows surface errors instead of losing data silently.

### 4.4 Flutter completion

- **One UI tree:** canonical `lib/src/ui/`. Live screens from `lib/screens/` move in; dead mirrors
  deleted. Router in `src/app.dart` references one tree.
- **One API client:** `SmartBedApi` (Dio). Remaining `lib/services/api_service.dart` callers
  ported, then the legacy client deleted. One JournalStore, one notification service, one
  error/banner widget set.
- **Decorative screens wired** (using existing `/v1/automation/*` surface where it fits, new
  endpoints where it doesn't): achievements, health dashboard, journal → dreams endpoints,
  winddown, sounds, partner mode. Local Hive stays as offline cache, not primary store.
- **Localization wired:** `AppLocalizations` delegate registered in `app.dart`; en + ar coverage
  for all live screens; Arabic verified RTL. (Kuwait market.)
- **Alarms screens** verified against the fixed contract via integration test.

### 4.5 Hardware bridge (honest, simulated-testable)

- **Bed-side `DeviceControlPoller`** in the bed runtime (`app_entry.py`): polls the backend for
  pending device controls/commands using the device pairing token, dispatches to the LED backend
  (`led/` — simulated backend locally, `pi5-spi` in Kuwait), and acks completion/failure.
- **Honest command state machine:** `queued → running → completed/failed` driven by poller acks,
  with a timeout marking un-acked commands `failed`. Wall-clock fake progression removed.
- **Explicit simulation mode:** `DEVICE_SIMULATION=1` keeps demo-without-hardware working — but
  labeled, opt-in behavior, not silent fakery.
- **Sensors:** endpoint reports honest device-offline status until the Pi pushes real readings;
  the push contract (schema + auth) is defined and implemented backend-side now.
- **Alarm ringing:** poller also pulls due alarms from `AlarmRepository` (closes "mobile alarm
  never rings anywhere").

### 4.6 Testing & CI

- **Keystone contract suite (written FIRST, before any fix — it must fail on today's P0s):**
  boots `api.app_factory.app` in a TestClient and walks register → login → alarm
  create/list/toggle/delete → profile save → islamic overview → dashboard → device command →
  scene → admin login + overview. Guards every later phase.
- 29 legacy test files migrate off `TestClient(web_server.app)` as their implementations move
  (Phase 3), not before.
- CI smoke (`scripts/mobile_smoke.py`) broadens to the same walk. ruff/bandit/gitleaks/flutter
  gates unchanged.
- Every phase ends: `pytest` green, `flutter analyze` clean, `flutter test` green, committed.

### 4.7 Deployment — Railway + Neon (Phase 7, gated on Phases 0–3)

- **Railway services:** `api` (gunicorn `api.app_factory:app`, workers=4) and `worker` (arq).
  No voice container in the cloud — that runs on the Pi in Kuwait.
- **Neon Postgres** (`DATABASE_URL`), Redis via the Railway Redis plugin (same platform, one
  bill) for rate limiting, brute-force guard, undo, arq.
- **Healthcheck:** Railway probes `/readyz` (real DB/Redis checks), not `/healthz`.
- **Release step:** `alembic upgrade head` runs pre-deploy and fails the deploy on error.
- **Env checklist** (fail-fast in prod): `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `SENTRY_DSN`,
  PayPal, Spotify, SendGrid, `WHATSAPP_*` (WhatsApp notifications require the worker + these
  vars — completing the audit's "partially working" finding).
- **Access needed from Danah at this phase:** authorize the Neon connector (claude.ai →
  connector settings), and Railway CLI login on this machine (or Danah runs handed commands).
- Previous Railway attempts failed (July 3 notes: CI/dependency conflicts around
  requirements-dev; heavy-ML split into `requirements-ml.txt` already exists). Diagnose against
  current state at phase start rather than assuming.

## 5. Phases (dependency order)

| Phase | Contents | Exit criteria |
|---|---|---|
| **0. Keystone test** | Contract suite against `app_factory` covering the full mobile+admin walk | Suite exists, fails exactly on the known P0s |
| **1. P0s + cheap P1s** | Alarms contract; admin guard; profile read-through; `GUNICORN_WORKERS=1` stopgap; `DatabaseConnection` singleton; revoked-token check; async wrapper fixes | Contract suite green; existing tests green |
| **2. State unification** | Sessions/checkout/idempotency/profile→DB; single alarm store; undo→Redis; JSON import script; GET side effects removed; workers→4 | Multi-worker test proves session survives across workers; suite green |
| **3. Seam removal** | Services extraction from `web_server.py`; single app/Sentry/registry/retry/queue; dead code deleted; 29 test files migrated; **`web_server.py` deleted only per constraint 1** | Zero `web_server` imports; suite green; P2 batch complete |
| **4. Flutter completion** | Tree+client consolidation; six screens wired; localization | `flutter analyze` clean; screens hit live endpoints; ar/en verified |
| **5. Hardware bridge** | Poller, honest state machine, sensor contract, alarm ringing | Simulated end-to-end: app tap → poller → LED backend → ack → app sees `completed` |
| **6. CI + re-audit** | Broadened smoke; re-score against `audit.md` | Re-audit ≥90%; CI green |
| **7. Deployment** | Railway + Neon + Redis; env; migrations-as-release-step; prod smoke | Production URL passing the contract walk; Sentry receiving events |

Phases 4 and 5 can interleave after 3. Phase 7 strictly after 0–3 (constraint 2); a staging
deploy may happen early in Phase 7 to de-risk Railway issues before the final cutover.

## 6. Risks & mitigations

- **Biggest risk — Phase 3 regressions:** mitigated by the keystone suite (Phase 0), migrating
  tests alongside implementations, and small green commits.
- **JSON→DB migration data loss:** import script is idempotent, run against copies first; JSON
  files archived (not deleted) until post-deploy verification.
- **Windows dev vs Linux prod:** CI (Linux) is the arbiter; anything OS-sensitive (file locks,
  paths) verified in CI before merge.
- **Neon/Redis latency for rate limiting + sessions:** session lookups add one indexed query per
  request; acceptable. Measure in staging; add a short-TTL in-process cache only if proven needed.
- **Decorative-screen scope creep:** each screen wired to the *existing* automation surface
  first; new endpoints only where a screen's core promise has no backing route.

## 7. Success criteria

1. Every `audit.md` finding closed (traceability table in the implementation plan maps each
   finding → phase → commit).
2. Contract suite + full test suite + Flutter suite green in CI.
3. Session/billing correctness proven under `workers=4`.
4. App tap → simulated LED round-trip demonstrated.
5. Deployed on Railway: `/readyz` green, contract walk passes against production.
6. Re-audit against `audit.md` scores ≥90%.
