DANAH SMART BED — PRODUCTION-READINESS AUDIT
Every claim below was verified by direct file inspection in this session. No documentation was consulted.

1. PROJECT COMPLETION STATUS
Backend wired end-to-end: ~70% of the mobile-facing surface; ~40% of the total declared surface.

The production app (api/app_factory.py:380) registers ~25 routers. The mobile-critical flows (auth, dashboard, timeline, chat, subscriptions, Spotify, OTP, pairing, scenes) genuinely reach a database or store and return real data. But three foundational features are broken by the half-finished migration off web_server.py, and two "hardware" features are simulations:

Feature	Status	Evidence
Mobile auth (register/login/refresh/OTP/social)	WORKING	services/auth_service.py, database/repositories.py:756-991
Alarms	BROKEN (contract mismatch)	see §7 P0-1
Admin panel API	BROKEN (auth mismatch)	see §7 P0-2
Profile save → prayer times/dashboard	BROKEN (split-brain storage)	see §7 P0-3
LED / device commands	FAKE — wall-clock simulation, no hardware dispatch	see §2 flow 6
Live sensors	STUB — hardcoded "not connected" (web_server.py:8208-8217)	
Billing (PayPal checkout/capture/webhook)	WORKING (single-worker only)	web_server.py:6683-6938
Chat (Dana AI)	WORKING	web_server.py:10076-10092
Flutter app: ~60% of screens are on live endpoints; ~40% are decorative.
Verified by grepping every screen for API/provider usage:

Live: home (12 call sites), dashboard (9), timeline (8), settings, profile, scenes, islamic, subscription, spotify, auth, pairing, alarms (wired but against a broken contract).
Decorative (zero backend calls, both UI trees): health dashboard, achievements, journal (local Hive only), winddown, sounds, partner mode. They render canned/local data and will look implemented in a demo until someone expects persistence or cross-device state.
Looks implemented but isn't:

Alarms — fully broken end-to-end in production wiring (§7 P0-1).
Admin panel — every protected endpoint 401s (§7 P0-2).
App localization — lib/l10n/ (668-line generated AppLocalizations, en+ar ARB files) is referenced by nothing outside itself; app.dart:234-238 omits the app delegate. The Arabic locale toggle only translates Material built-ins.
master_api.py / master_controller.py — an entire alternative FastAPI app; nothing imports or runs them (verified via git grep).
Sensors — hardcoded stub.
Device commands — status is simulated by elapsed time (§2 flow 6).
2. BACKEND WIRING AUDIT — 10 FLOW TRACES
Production entrypoint is gunicorn api.app_factory:app (Dockerfile:51, nixpacks.toml:8). All traces below are through that app.

Mobile auth — WORKING. api/routers/auth.py:337-351 → AuthService.login → UserRepository/MobileAuthRepository (bcrypt via core/security, JWT+JTI, DB-backed refresh rotation at repositories.py:875-916). Redis brute-force guard degrades to no-op without Redis (services/auth_service.py:33-98).
Alarm creation — BROKEN. api/routers/alarms.py:93-113 writes the DB fine, but the request/response contract doesn't match the app (§7 P0-1).
Alarm trigger — NOT WIRED. Alarms stored via AlarmRepository are read by nothing that fires them. The only alarm execution path is ScheduleManager.pop_due_alarms() in the bed's voice runtime (app_entry.py:381-401) — a different store entirely. A mobile-created alarm never rings anywhere.
Prayer times — PARTIALLY WORKING. api/routers/islamic.py:47-60 calls AlAdhan correctly, but resolves location from the legacy JSON profile, not from the DB the app writes to (§7 P0-3), so it falls back to Kuwait City defaults (web_server.py:1182-1194). Also premium-gated: a free demo account gets 403 (web_server.py:5254-5269).
Chat — WORKING. api/routers/chat.py:22-30 → web_server.ai_chat → thread-offloaded _generate_actor_reply → httpx-based ConversationEngine, memory recorded per user. Note the SSE "stream" collects all chunks before emitting (web_server.py:10189) — it's not actually streaming.
LED control — UI-ONLY. App → POST /v1/mobile/device-controls → JSON write to web_device_controls (web_server.py:8414-8435). Nothing consumes it: no polling in app_entry.py, voice_handler.py, or ai/bed_backend_client.py (verified by grep). POST /v1/mobile/device-commands state machine is time-based: queued → running at 2 s → completed at 5 s (web_server.py:3165-3185) regardless of any hardware.
Profile save — BROKEN split-brain (§7 P0-3).
WhatsApp notification — PARTIALLY WORKING. whatsapp_client.py (Graph API) ← notifications/whatsapp_notifier.py ← scheduler/arq tasks. Requires WHATSAPP_* env plus the separate worker container; nothing in the API path sends WhatsApp.
Billing — WORKING on one worker. Checkout/capture/webhook wired through BillingService with idempotency — but idempotency and checkout sessions live in the per-process JSON store (§4), so with GUNICORN_WORKERS=4 (docker-compose.yml:30) capture can land on a worker that can't see the checkout session → intermittent 404 "Checkout session not found".
Admin panel — BROKEN (§7 P0-2).
Routes never called by the Flutter app: the entire /v1/automation/* surface (91 routes, api/automation_routes.py) except achievements and sleep/smart-insight; all /v1/dana/*, /v1/guest/*, /v1/qr/*, /v1/ring/*, /v1/monitoring/*; most of /v1/admin/* is called only by the web panel (which can't authenticate).
Flutter calls with no backend route: none — all 60 extracted paths matched (verified by full-path cross-diff).

Circular imports / lazy-import cost: every "migrated" router lazy-imports from web_server inside request handlers (from web_server import …). The first such request executes the entire 10,995-line module: builds a second FastAPI app (web_server.py:297), re-initializes Sentry a second time with different settings (web_server.py:182-199 vs app_factory.py:62-81), and constructs SubscriptionStore, SceneStore, UndoManager, SleepIntelligenceEngine at module scope (web_server.py:78-116). It does not load AI/audio hardware modules (those imports are httpx-light), so this is a latency/duplication problem, not an OOM problem.

3. CODE QUALITY
Exception swallowing: 0 truly bare except:; 679 except Exception blocks; 67 are except Exception: pass outside tests. Severity grouping:

Auth/data-loss relevant: BruteForceGuard.clear swallow (auth_service.py:97-98) — benign; main.save_profile swallows profile-save failure entirely (main.py:38-44) — silent data loss for the voice runtime; Flutter ApiService.saveToken/getToken catch-all (api_service.dart:55-73) — a failed token save silently logs the user out later.
Startup-resilience style (majority): the 34 try/except → logger.warning blocks of api/service_registry.py and app lifespans. Defensible pattern, but it means the app happily boots with any subsystem dead ("non-fatal" DB!).
Cosmetic: telemetry/_event guards.
Duplicate implementations (verified pairs):

Duplicate	Files
Two FastAPI apps (three counting dead master_api)	api/app_factory.py, web_server.py:297, master_api.py
Two alarm systems w/ different contracts	api/routers/alarms.py (DB) vs web_server.py:7963-8104 (JSON)
Two profile stores	ProfileRepository (DB) vs web_profile_prefs JSON (web_server.py:2261-2277)
Two session systems	MobileAuthSession (DB) vs SubscriptionStore sessions (Storage/subscription_store.py:207-218)
Two Sentry inits (backend), plus Flutter's	app_factory lifespan vs web_server module scope
Two complete Flutter UI trees, both routed	lib/screens/** and lib/src/ui/screens/** — 12+ mirrored screens (app.dart routes both)
Two Flutter API clients	lib/src/core/api_client.dart (Dio) vs lib/services/api_service.dart (http)
Two JournalStores, 2 notification services, 2 error/banner widget sets	lib/services/* vs lib/src/core/*, lib/widgets/* vs lib/src/ui/widgets/*
Two retry frameworks	core/retry.py vs utils/retry.py
Two task queues	tasks/celery_app.py vs tasks/arq_app.py (compose runs arq only)
Two service registries	api/service_registry.py + core/service_registry.py
Duplicate routes registered twice	POST /v1/admin/auth/login and GET /v1/admin/auth/me in both auth.py and admin.py (first registration wins)
Dead code: master_api.py+master_controller.py (never imported), main.py (test-utility shim), fix_db_schema.py, sanity_checks.py, pack_code.py, manual_email_test.py, test_whatsapp.py, print_sendgrid_env.py (all unreferenced), the entire Flutter l10n system, lib/screens/settings/settings_screen.dart's twin usage, celery app, and web_server's own middleware/lifespan (never runs under app_factory, yet maintained).

Maintainability of the 5 largest files (1–10):

web_server.py (10,995 ln, 386 defs, 137 routes): 2/10 — god-module: auth, billing, OTP, social login, scenes, timeline, admin, Spotify HTTP calls all in one namespace with module-level singletons.
voice_handler.py (4,549 ln): 3/10 — ~100 loose functions imported by name into app_entry (app_entry.py:188-253 imports 66 of them).
database/repositories.py (2,511 ln): 6/10 — coherent repository pattern, but 13 classes in one file and each defaults to constructing its own engine.
app_entry.py (2,095 ln): 4/10 — one main() wiring 40+ engines by hand.
Storage/subscription_store.py (2,032 ln): 3/10 — JSON file pretending to be a multi-table DB with sessions, billing, audit logs, incidents.
4. RELIABILITY & CONCURRENCY
Race conditions (all real under the compose config of 4 workers):

SubscriptionStore loads the JSON DB into memory once per process (subscription_store.py:137-140) and save() writes the whole dict back (:261-265). Across workers: cookie sessions issued on worker A are invisible to B (login randomly "doesn't stick"), and any later save from B erases A's sessions/checkouts/audit logs. This breaks web login, admin sessions, PayPal webhook idempotency, and checkout capture whenever workers > 1.
Profile JSON read-modify-write is guarded only by the in-process _PROFILE_RW_LOCK (web_server.py:84); Storage/io.py locks individual reads/writes but not the cycle. Concurrent settings/alarms/Spotify-token writes across workers lose updates. Worse, GET /v1/mobile/dashboard and GET /v1/mobile/timeline write the profile on read (web_server.py:6170-6171, 8500-8501).
UndoManager, _CHAT_ENGINES, in-memory rate-limit fallback are per-process → undo issued via worker A can't be undone on worker B; rate limits multiply by worker count when Redis is absent.
Event-loop blockers (async wrappers directly invoking sync monolith handlers on the loop): POST /v1/command (chat.py:42-50 → sync web_server.py:10972), both undo POSTs (actions.py:21-27, 48-54), POST /v1/mobile/push-token and first-3-nights/complete (mobile_features.py:41-53, 76-88), admin login (bcrypt, admin.py:60-66), and all three scene POSTs (scenes.py:37-61) — scene preview even sleeps/animates. Each of these freezes every concurrent request on that worker for its duration.

Engine-per-request leak: DatabaseConnection() builds a new SQLAlchemy engine + pool (10+20 conns) and a retried SELECT 1 probe on every instantiation (connection.py:41-102). It is constructed per-request in the alarms router (alarms.py:88,100,123,146,158), in OTP request/verify (web_server.py:7332-7334, 7390-7392), and per readiness probe (health.py:35,70). Under Postgres (default max_connections=100) this is connection-pool roulette; if the DB is down, each such request stalls ~3–7 s in retry and then proceeds with a dead engine (reraise=False at connection.py:91).

Single points of failure: the profile JSON file (every mobile request path touches it; a corrupt file is quarantined → all user state silently resets, Storage/io.py:227-233); the subscription JSON (auth+billing); and the lifespans' "non-fatal" catches, which let the API boot with no DB and fail on first real request while /healthz stays green (health.py:20-22 checks nothing — only /readyz checks DB/Redis, and compose/Dockerfile healthchecks use /healthz).

5. SECURITY
Secrets: .env was never committed (git history clean); .gitignore covers it; no token patterns in tracked files; CI runs gitleaks. print_sendgrid_env.py prints the SendGrid key to stdout — delete it. SECRET_KEY fails fast at import (config/settings.py:73-83) — good. Sentry events are scrubbed (web_server.py:156-169).

Auth flow:

Revoked access tokens keep working on migrated routes. get_current_user (auth/middleware.py:40-63) verifies signature/expiry only — it never checks the DB revoked flag that logout sets (repositories.py:941-991). Logout therefore doesn't invalidate the access token for up to 60 min on alarms, profile, settings, chat, devices, actions routes. The legacy guard _mobile_user (web_server.py:5193-5203) does check the DB — the two disagree.
Token storage keys agree between app and backend (Authorization: Bearer, access_token/refresh_token fields; secure storage via flutter_secure_storage, session_store.dart).
Refresh rotation is correct (old refresh revoked atomically).
OTP: HMAC-digested codes, TTL, attempt cap, constant-time compare (web_server.py:7377-7423) — good.
Input validation: consistent Pydantic on mobile routes; but the wrapper pattern Model(**await request.json()) in chat/actions/scenes/integrations raises raw ValidationError → 500 via the generic handler instead of 422, and ValueError messages are echoed to clients (error_handler.py:47-54) — mild info leak, no stack traces.

CORS / rate limiting / headers: production wildcard CORS is refused at startup (app_factory.py:172-184); Redis-backed sliding-window limiter with proxy-aware IP (api/middleware/rate_limiter.py); solid security headers; /docs disabled in production; /metrics IP-gated (metrics.py:21-45). This layer is genuinely good.

6. DEPLOYMENT & INFRASTRUCTURE
Entrypoint consistency: Dockerfile CMD, nixpacks, and CI smoke all run api.app_factory:app — consistent. The compose voice service runs python app_entry.py in a container with no microphone/speaker; STT/wake managers will run in degraded stub loops — it's wasted RAM at best.
Startup memory/healthcheck: app_factory imports are light; the heavy web_server import happens lazily on the first wrapped request (one-time multi-second stall + duplicate Sentry init). /healthz answers immediately but proves nothing (§4).
Env enforcement: SECRET_KEY fail-fast ✔; DATABASE_URL fail-fast in production for the sync engine (connection.py:47-60) ✔ — but the async pool, arq, Firebase, Redis all silently no-op on failure (lifespan warnings only). validate_production_secrets returns warnings, never blocks (settings.py:531-551).
Migrations: entrypoint runs alembic upgrade head but continues on failure (scripts/docker-entrypoint.sh:6); repositories then paper over it with create_tables() (Base.metadata.create_all at repositories.py:759) — schema drift between Alembic and ORM will go unnoticed. Alembic heads are merged (single head 084855be2828 — verified).
CI: ruff + bandit + pytest (sqlite) + a real HTTP smoke against app_factory + flutter analyze/test + gitleaks. Better than most. But the smoke (scripts/mobile_smoke.py) covers register→dashboard→device-command→scene only — it cannot catch the alarm/admin/profile breaks.
7. CRITICAL BUGS (RANKED)
P0-1 — Alarms are broken end-to-end in production.
The app serializes {alarm_id, time, days(1-7), enabled, label, sound, vibrate} (models.dart:1364-1374) and reads back alarm_id/days; it expects an alarms list in the POST response (api_client.dart:554-567). The production route accepts days_of_week(0-6) and returns a single alarm keyed id (alarms.py:31-54, 64-77, 93-113). Result in a live demo: created alarms lose all recurrence days, the list refresh after saving shows nothing, every alarm deserializes with an empty ID so toggle/delete call /v1/mobile/alarms//toggle → 404, and "editing" creates duplicates. The legacy JSON handler that matches the app (web_server.py:7980-8036) is unreachable — and 29 test files test that one (TestClient(web_server.app), e.g. tests/test_mobile_pairing_alarm_api.py:66); zero tests target app_factory. Fix: change alarms.py to accept/return the legacy field names (alarm_id, days 1-7, list response) or bulk-update the Flutter model — one side, consistently — and add one app_factory-based contract test.

P0-2 — Admin panel is 100% dead in production.
Protected admin router requires require_role("admin") on a Bearer JWT (admin.py:50-54), but (a) the panel authenticates with cookies (credentials:"include", no Authorization header — web/assets/app.js:28), and (b) no JWT ever contains a role claim (auth/jwt_handler.py:63-73). Every /v1/admin/* call except login/me returns 401/403 for everyone. Fix: replace the router dependency with a cookie-based guard that calls web_server._require_admin, or embed role in JWTs and make the panel send them.

P0-3 — Profile save is split-brain; prayer times and dashboard ignore what the app saves.
POST /v1/mobile/profile writes DB user_profile_prefs (profile.py:98-108); prayer times, Islamic overview, dashboard name/location all read the legacy JSON web_profile_prefs (web_server.py:2261-2277, 6125-6134). The app's auto-captured GPS location (auth_controller.dart:279-332) never affects prayer times → everyone gets Kuwait City. Fix: make _chat_profile_prefs_for_user read through ProfileRepository first.

P1-4 — Multi-worker deployment corrupts sessions/billing state. (§4 item 1). With compose's GUNICORN_WORKERS=4, web login breaks ~75% of requests and JSON-store writes clobber each other. Fix for demo: set workers=1 everywhere; real fix: move sessions/checkouts to the DB.

P1-5 — Engine-per-request on alarms/OTP/readyz (§4). Under Postgres this exhausts connections under modest load. Fix: module-level singleton DatabaseConnection, pass into repositories.

P1-6 — Revoked-token acceptance on migrated routes (§5). Fix: have get_current_user call MobileAuthRepository.validate_access_token.

P1-7 — Event-loop blocking async wrappers (§4): /v1/command, undo, push-token, scene preview/save freeze the worker. Fix: make wrappers def (threadpool) or await asyncio.to_thread(_ws, ...).

P2 — GETs with write side effects (dashboard/timeline); fake SSE streaming; duplicate Sentry init with conflicting configs; migration failures swallowed by entrypoint; premium gate on Islamic tab will 403 free demo accounts; localization dead; voice container pointless in cloud.

8. FINAL VERDICT
This project is ~55% production-ready for a limited demo (not full production).

The floor is genuinely good — auth core, rate limiting, security headers, secrets hygiene, OTP, billing service, CI — this is far above hobby level. What drags it down is one systemic failure: the router migration was declared done but never re-verified end-to-end. Tests, the Flutter app, and the admin panel all still speak the web_server.py dialect, while production serves the new one. Everything that broke, broke on that seam — and the CI smoke test is too narrow to see it.

Must fix before July 15 (all are ≤ 1 day each):

P0-1 alarms contract (backend-side fix is ~30 lines).
P0-2 admin router guard.
P0-3 profile read-through (or at minimum: prayer location).
Set GUNICORN_WORKERS=1 in compose/nixpacks until sessions move to the DB (one-line mitigations for P1-4).
Singleton DatabaseConnection (P1-5, ~10 lines).
Add one pytest that boots api.app_factory.app in a TestClient and walks register → alarm create/list/toggle → profile save → islamic overview → admin login+overview. This single test would have caught all three P0s.
Can wait: token-revocation check (P1-6, do it the week after), async wrapper cleanup, deleting master_api.py/dead scripts, collapsing the duplicate Flutter tree, localization, celery removal, SSE streaming, and everything in §3.

One hard truth to close on: as shipped, the "smart bed control" from the phone controls a JSON file, not a bed. For a demo that's survivable — the simulation even animates command status — but nothing in this repo currently connects a mobile tap to an LED. If the July demo includes "press button, light changes," the bed-side poller for /v1/mobile/device-controls still has to be written.