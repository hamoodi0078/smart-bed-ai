# Plan 8: Billing & Admin State → Postgres (Campaign Phase 2, part 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (or subagent-driven-development). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the money-and-access state survive container restarts and stop depending on one process's JSON file. Today `runtime_data/subscription_db.json` is the sole authority for checkout sessions, PayPal webhook idempotency/replay receipts, payment events, subscription tiers, and admin sessions — on Railway's ephemeral filesystem, a redeploy erases billing history and entitlements. This plan makes Postgres the durable authority for exactly those five state families, keeping every public `SubscriptionStore` method signature and return shape unchanged.

**Architecture (decided after reading the store end-to-end):**
- **Dual-write, DB-first-read.** Each ported method writes the DB row *and* the legacy JSON section (the JSON stays as mirror + no-DATABASE_URL fallback, and feeds legacy views like `build_user_timeline`). Reads try the DB first and fall back to JSON. No behavior change when `DATABASE_URL` is unset.
- **Live-dict mutation sites become explicit updates.** The store returns live references into `self.db` that callers mutate before `store.save()`. All external checkout mutations live in `subscriptions/billing.py` (8 sites: lines 121, 138-139, 186-195, 219-223, 409-416, 460-470) — they switch to a new `store.update_checkout_session(session_id, **fields)`. Subscription in-place mutations are internal to the store (`apply_billing_webhook` paused/cancelled branches at ~1120-1145 in the current file, `upsert_subscription`, `set_subscription_grace`, `update_subscription_provider_state`) and get a write-through hook.
- **Subscriptions: hydrate-at-boot + synchronous write-through.** `get_subscription` stays an in-memory read (it runs on entitlement checks; no per-request Neon round-trip). Durability comes from: (a) `__init__` hydrates `self.db["subscriptions"]` from `SubscriptionRecord` rows that the JSON lacks; (b) `save()`'s existing `_sync_subscriptions_to_db` mirror becomes non-leaking (shared connection, not a new engine per save — today it constructs `DatabaseConnection(database_url=...)` on EVERY save).
- **Admin sessions → DB row** with the existing Redis cache layer retained in front.
- **Explicitly OUT of scope** (still JSON, acceptable: legacy web or admin-fleet features): users/user_sessions (legacy web cookie flow — mobile auth is already DB-first via MobileAuthRepository), devices/fleet, usage counters, app/firmware releases, incidents, admin_users, admin_audit_logs, bed_profiles. Also out: profile-JSON races beyond the two GET write-on-read sites (rest goes to Plan 9 with the web_server decomposition).

**Tech stack facts (verified 2026-07-19):** alembic head is `ed907a3c517e`; contract tests use per-test sqlite via `DATABASE_URL` + `reset_web_server_db_singletons` + a fresh `SubscriptionStore(db_path=tmp)` patched onto `web_server.store`; tables come from `create_tables()` short-circuit in tests, alembic in prod; `get_shared_connection()` / `reset_shared_connection()` at database/connection.py:488/504. The 12-test net is `tests/test_mobile_subscription_billing.py` — it must stay green untouched through every task.

## Global Constraints

- Python via `venv/Scripts/python.exe`; Windows baseline = 8 environmental failures (2 long_term_memory, 2 EncryptedText flakes, 4 diarization); CI is arbiter.
- Every public `SubscriptionStore` method keeps its exact signature and return shape. `tests/test_mobile_subscription_billing.py` is the contract net and MUST NOT be edited.
- All DB access inside the store goes through `database.connection.get_shared_connection()` — never construct `DatabaseConnection(...)` directly.
- DB unavailable / `DATABASE_URL` unset ⇒ every method behaves exactly as today (JSON only). Wrap DB reads in try/except that logs at debug and falls back; DB writes in try/except that logs at warning (dual-write must not take down billing).
- Commit per task, never red. Co-author trailer as usual.

---

### Task 1: Models + migration + repositories (RED tests first)

**Files:** `database/models.py` (+4 models), `alembic/versions/a9b8c7d6e5f4_add_billing_admin_state_tables.py` (down_revision `ed907a3c517e`), `database/repositories.py` (+`BillingStateRepository`, `AdminSessionRepository`), new `tests/test_billing_db_persistence.py`.

- [x] **Step 1: Write the RED durability tests** — `tests/test_billing_db_persistence.py`, fixture modeled on `AppFactoryContractCase`'s env pattern but store-only (no HTTP): tmp dir; `patch.dict(os.environ, {"DATABASE_URL": "sqlite:///<tmp>/test.sqlite3"})`; `reset_shared_connection()`; `get_shared_connection().create_tables()`; helper `fresh_store(name)` returning `SubscriptionStore(db_path=tmp/f"{name}.json")`. Tests (each: write via `store_a = fresh_store("a")`, read via `store_b = fresh_store("b")` — different JSON paths, same DB):
  1. `test_checkout_session_survives_process_restart` — create via A; B's `get_checkout_session(session_id)` + `get_checkout_session_by_provider_order_id` find it after A calls `update_checkout_session(session_id, status="approved", provider_order_id="ORD-1")`.
  2. `test_payment_events_survive_process_restart` — A `apply_billing_webhook("payment.succeeded", user_id=…, tier="standard")`; B `list_payment_events(user_id)` returns the event AND B `get_subscription(user_id)["tier"] == "standard"` (hydration).
  3. `test_webhook_receipts_survive_process_restart` — A `remember_billing_webhook_receipt(...)` + `remember_billing_webhook_replay(...)`; B `get_billing_webhook_receipt(key)` / `get_billing_webhook_replay(key)` return them; B `prune_billing_webhook_memory(max_age_seconds=60)` with future rows removes nothing; with `_now_iso` patched old, removes them in DB too (A's fresh read confirms).
  4. `test_admin_session_survives_process_restart` — A `upsert_admin_user` + `issue_admin_token`; B `validate_admin_token(token)` returns the role payload (B also needs the admin user — admin_users stay JSON, so seed the admin user in B's JSON too via `upsert_admin_user` before validating; the SESSION is what must come from DB).
  5. `test_no_database_url_falls_back_to_json` — env without DATABASE_URL (patch it out + `reset_shared_connection()`): every flow above works single-store exactly as today.
  Run: expect all RED except test 5 (which documents the fallback and should already pass).
- [x] **Step 2: Models** — append to `database/models.py` (types per house style: `String` with lengths, `Text` for URLs/summary, `JSON` for raw/details, `DateTime(timezone=True)` for created/processed, `Index` on the lookup keys):
  - `CheckoutSessionRecord`: `id` PK autoinc; `session_id` String(64) unique index; `user_id` String(64) index; `tier/interval/payment_provider/status` String(20/20/40/30); `price_kwd` Float; `approve_url/return_url/cancel_url` Text; `provider_order_id/provider_subscription_id/provider_plan_id/provider_capture_id` String(255) (index the first two); `provider_environment/provider_currency/provider_status` String(60); `created_at/captured_at/cancelled_at` String(40) (ISO strings — match dict shape, no tz juggling).
  - `PaymentEventRecord2` is NOT needed — reuse name `PaymentEventRecord`: `id` PK; `event_id` String(64) unique index; `user_id` String(64) index; `event_type` String(80); `tier/interval` String(20); `payment_provider` String(40); `summary` Text; `status` String(60); `amount_value/currency` String(40/10); `provider_reference/provider_subscription_id/provider_plan_id` String(255); `raw` JSON; `created_at` String(40) index.
  - `BillingWebhookReceipt`: `id` PK; `kind` String(12) (`"idempotency"`/`"replay"`); `receipt_key` String(255); unique index on (`kind`,`receipt_key`); `payload` JSON (the full row dict); `processed_at` String(40) index.
  - `AdminSessionRecord`: `id` PK; `token` String(80) unique index; `user_id` String(64) index; `role` String(20); `expires_at` String(40); `revoked` Boolean default False.
- [x] **Step 3: Migration** — new revision file, `revision = "a9b8c7d6e5f4"`, `down_revision = "ed907a3c517e"`, `op.create_table` × 4 mirroring Step 2 exactly (copy an existing revision's imports/style), downgrade drops them.
- [x] **Step 4: Repositories** — `BillingStateRepository(db=None)` using `self._db = db or get_shared_connection()`:
  `create_checkout(row: dict)`, `get_checkout(session_id)`, `get_checkout_by_order_id(...)`, `get_checkout_by_subscription_id(...)`, `update_checkout(session_id, **fields) -> dict|None` (returns full dict), `add_payment_event(row: dict)`, `list_payment_events(user_id="", limit=100) -> list[dict]` (newest first; empty user_id = all users, for the admin listing), `get_receipt(kind, key) -> dict|None`, `remember_receipt(kind, key, payload: dict)` (upsert), `prune_receipts(kind, cutoff_iso) -> int`, `delete_user_billing(user_id) -> dict` (counts per table), `load_subscriptions() -> list[dict]` (SubscriptionRecord rows → store dict shape via `_subscription_defaults` keys). `AdminSessionRepository`: `create(token, user_id, role, expires_at)`, `get(token) -> dict|None`, `delete(token) -> bool`, `delete_for_user(user_id) -> int`. Row↔dict mapping helpers keep the exact dict key names the JSON store uses today.
- [x] **Step 5:** `venv/Scripts/python.exe -m pytest tests/test_billing_db_persistence.py -v` — still RED (store not wired), but now failing on missing store behavior, not missing tables. `venv/Scripts/python.exe -m alembic upgrade head --sql | tail -5` renders without error (offline check). Commit: `feat(db): billing/admin state tables + repositories (Plan 8 Task 1)`.

### Task 2: Checkout, payment events, receipts — DB-first in the store; BillingService explicit updates

**Files:** `Storage/subscription_store.py`, `subscriptions/billing.py`.

- [x] **Step 1:** Store helpers: `_billing_repo()` → `BillingStateRepository()` if `os.getenv("DATABASE_URL")` else None, cached per-instance, `except Exception -> None` (debug log). Same pattern `_admin_session_repo()`.
- [x] **Step 2:** Port methods (dual-write, DB-first read, JSON fallback; DB rows are dict-copies — never live references):
  - `create_checkout_session`: after building `checkout`, `repo.create_checkout(checkout)` (warn on failure), JSON append + save as today.
  - `get_checkout_session` / `_by_provider_order_id` / `_by_provider_subscription_id`: try repo getter; on hit return it; else JSON scan (unchanged). **Note:** these now return copies when served from DB — which is exactly why Step 4 rewrites the mutating callers first in the same commit.
  - NEW `update_checkout_session(self, session_id: str, **fields) -> Optional[dict]`: update DB row via repo; update matching JSON row in place; `self.save()`; return merged dict (JSON row if present else DB dict).
  - `apply_billing_webhook`: event dict → `repo.add_payment_event(event)` + JSON append (unchanged logic after that).
  - `list_payment_events`: DB-first (`repo.list_payment_events(user_id, limit)` → normalize exactly like today's projection); fallback JSON path unchanged. `list_payment_events_admin`: DB-first with the same post-filters it applies today (read its body first; keep filter semantics identical by applying them over the DB dicts).
  - receipts: `remember_billing_webhook_receipt/_replay` → `repo.remember_receipt(kind, key, row)` + JSON + save; `get_billing_webhook_receipt/_replay` → DB-first, JSON fallback; `prune_billing_webhook_memory` → also `repo.prune_receipts(kind, cutoff_iso)` and add DB-removed counts into the returned dict's existing keys.
  - `delete_user_data`: after JSON deletions, `repo.delete_user_billing(user_id)` + `admin_repo.delete_for_user(user_id)` (warn-only), fold DB counts into the same `deleted` keys.
- [x] **Step 3:** `subscriptions/billing.py` — replace all 8 in-place `checkout[...]=...; self.store.save()` sites with `self.store.update_checkout_session(checkout["session_id"], status=..., provider_order_id=..., ...)` carrying exactly the fields each site sets today (read each site; some set provider_capture_id/captured_at/cancelled_at too). Reassign `checkout = self.store.update_checkout_session(...) or checkout` where the local is used afterwards.
- [x] **Step 4:** GREEN: `tests/test_billing_db_persistence.py` tests 1, 3, 5 pass; `tests/test_mobile_subscription_billing.py` all 12 pass; `tests/test_app_factory_contract.py` 13 pass. Commit: `feat(billing): checkout/events/receipts DB-first with JSON fallback (Plan 8 Task 2)`.

### Task 3: Subscriptions — hydrate at boot, write-through without engine leak

**Files:** `Storage/subscription_store.py`.

- [x] **Step 1:** `_sync_subscriptions_to_db`: drop `DatabaseConnection(database_url=env_url)`; use `get_shared_connection()`; keep best-effort semantics. (This kills an engine construction on EVERY `save()` — a live resource leak today.)
- [x] **Step 2:** `__init__`: after `self.db = self._load()`, call `self._hydrate_subscriptions_from_db()`: `repo.load_subscriptions()`; for each DB row whose `user_id` is missing from `self.db["subscriptions"]`, append it (defaults-merged); if anything was added, `atomic_write_json` directly (NOT `self.save()`, to avoid a sync-back loop during init). Wrap whole thing in the warn-only guard.
- [x] **Step 3:** GREEN: durability test 2 passes (tier survives restart via hydration). Full billing net still green. Commit: `feat(billing): subscriptions hydrate from DB at boot; shared-connection sync (Plan 8 Task 3)`.

### Task 4: Admin sessions — DB-backed behind the Redis cache

**Files:** `Storage/subscription_store.py`.

- [x] **Step 1:** `issue_admin_token`: also `admin_repo.create(token, user_id, role, expires_at)` (warn-only). `validate_admin_token`: current chain (Redis → JSON) then DB fallback — on DB hit, backfill the JSON row so subsequent validates are cheap. Revocation: `delete_user_data` already deletes JSON admin sessions — add `admin_repo.delete_for_user`; find any admin-logout route calling session deletion (`grep -n "admin_sessions" web_server.py api/routers/*.py`) and mirror a `admin_repo.delete(token)` there if one exists.
- [x] **Step 2:** GREEN: durability test 4; admin flows in contract suites unaffected. Commit: `feat(admin): admin sessions DB-backed (Plan 8 Task 4)`.

### Task 5: Dashboard/timeline GET write-on-read under the profile lock

**Files:** `web_server.py`, `tests/test_device_sync_contract.py` (or the contract file — wherever `DeviceBridgeContractCase` fixture fits best).

- [x] **Step 1:** RED test (lock-probe pattern from Plan 7): patched `_save_profile` probe asserting `_PROFILE_RW_LOCK` held during `GET /v1/mobile/dashboard` when it decides to persist (drive persistence deterministically — inspect the dashboard handler's `profile_dirty` conditions first and pick the cheapest trigger; if no deterministic trigger exists, assert instead that a plain GET performs NO `_save_profile` call after moving the persist under the lock — match the test to what the handler actually does, and say which in the commit).
- [x] **Step 2:** Wrap the dashboard GET's read→mutate→save cycle and the timeline GET's equivalent in `with _profile_rw():` (find via `grep -n "_save_profile" web_server.py` inside the dashboard/timeline handlers; wrap the minimal block that spans the profile read used for the save through the save itself).
- [x] **Step 3:** GREEN: new test + `tests/test_app_factory_contract.py` + bridge suite. Commit: `fix(web): dashboard/timeline write-on-read cycles hold the profile RW lock (Plan 8 Task 5)`.

### Task 6: Verification sweep + push

- [x] `venv/Scripts/python.exe -m pytest tests/test_billing_db_persistence.py tests/test_mobile_subscription_billing.py tests/test_device_sync_contract.py tests/test_app_factory_contract.py -q` — all green.
- [x] Full suite `-q` — no NEW failures beyond the 8-failure baseline.
- [x] `ruff check` on every touched file — clean.
- [x] Boot smoke (TestClient `/healthz` 200) + `alembic heads` shows single head `a9b8c7d6e5f4`.
- [x] Tick plan checkboxes, update memory, commit `docs: Plan 8 executed`, push, note CI check.

## Follow-ups (unchanged from Plan 7's table)
Plan 9: web_server decomposition (+ remaining profile-JSON sections → DB, service-registry merge, pseudo-SSE, main.py shim). Plan 10: Flutter dedup. Phase 5 leftover: bed→cloud sensor telemetry. Workers>1 stays gated on the profile-JSON work in Plan 9 — this plan removes the billing/admin blockers only.
