# Plan 7: Critical Blockers & Duplication Cleanup (2026-07-18 Audit Refresh) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every critical/high finding from the 2026-07-18 audit refresh that is fixable in ≤1 day each: two new P0s introduced by the device bridge (unlocked profile read-modify-write on the bed's 2.5 s poll path; open device auth), three carried-over ops gaps (secrets never block, migrations swallowed, healthchecks prove nothing), and the cheap duplication deletions (celery, dead retry frameworks, repo litter).

**Architecture:** Fixes land in `api/device_bridge.py`, `config/settings.py`, `api/app_factory.py`, and deploy files. Test-first against the production app via the existing `DeviceBridgeContractCase` scaffolding (`tests/test_device_sync_contract.py`). Deletions are verified-then-deleted with grep gates. The big remaining refactors (state→DB, web_server decomposition, Flutter tree merge) are explicitly OUT of this plan — see "Follow-up plans" at the bottom.

**Tech Stack:** FastAPI + SQLAlchemy 2.x (sync) + pytest/unittest + fastapi.testclient. Windows dev box (`venv/Scripts/python.exe`); GitHub CI (Linux) is the arbiter.

## 2026-07-18 Audit Refresh — findings this plan responds to

**Fixed since the July 8 audit (verified in code, no action needed):** P0-1 alarms contract, P0-2 admin guard, P0-3 profile read-through, P1-5 engine-per-request (shared connection adopted incl. web_server OTP), P1-6 revoked tokens, P1-7 event-loop blockers (`asyncio.to_thread` everywhere), workers=1 stopgap, duplicate admin routes (0 duplicate route registrations across all 255 routes), dead scripts (master_api, print_sendgrid_env, etc. all deleted), l10n registered, decorative screens wired, device bridge + BedCommandPoller real, bed-side alarm ringing wired via `/v1/device/sync` desired_state.

**New criticals found (this plan fixes):**
- **NEW-P0-A** — `api/device_bridge.py` does profile read-modify-write **without** `web_server._profile_rw()` in all four functions (`device_auth`, `device_token_refresh`, `device_sync`, `device_command_result`), and `device_sync` writes the whole profile JSON every 2.5 s bed poll. Any concurrent mobile request that writes the profile (settings, pairing, Spotify tokens, scenes — and the dashboard/timeline GETs, which write on read) can be clobbered by a bed poll or vice versa. Single worker does not save you: handlers run concurrently in the threadpool. Continuous 2.5 s cadence makes lost updates a when, not an if. (Tasks 1)
- **NEW-P0-B** — `/v1/device/auth` requires no credential when `DEVICE_FACTORY_SECRET` is unset (it is unset: not in `config/settings.py`, not checked by `validate_production_secrets`). Anyone who knows/guesses a provisioned device_id can mint a device JWT, read that household's alarms/desired state, and report fake command results. (Task 2)
- **NEW-BLOCKER-0 (machine, not code)** — the dev box C: drive is **100 % full (0 bytes free)**. The 2026-07-18 test run produced 9 failures beyond the 8-failure Windows baseline (6× `test_mobile_subscription_billing`, 2× timeline DB, 1× vertical-slice) — all in disk-writing tests, all suspect until re-run with free disk. Reclaimable inside the project: `.venv` 2.7 GB + `.venv311` 529 MB (redundant — `venv/` is the one scripts use), `repomix-output.txt` 134 MB, `.tmp/` 126 MB pytest litter. **Prerequisite: free disk space before executing any task** (see Task 7 + manual step).

**Carried-over P1s still live (this plan fixes):** `validate_production_secrets` warns but never blocks (Task 3); `docker-entrypoint.sh` continues on failed Alembic migration; compose/Dockerfile healthchecks hit `/healthz`, which checks nothing (Task 4).

**Carried-over duplication still live:** celery app (compose runs arq only) — Task 5; `core/retry.py` + `utils/retry.py` (both apparently importer-less) — Task 6; two service registries (`api/` + `core/` — **deferred**, coupled to web_server decomposition); 11,035-line web_server + 115 lazy-import seams + dual FastAPI app + dual Sentry init + pseudo-SSE (**deferred** → Plan 9); SubscriptionStore JSON sessions/billing + profile write-on-read GETs (**deferred** → Plan 8); Flutter: two UI trees with four live duplicate screen pairs (AlarmScreen/SmartAlarmScreen, IslamicScreen/IslamicModeScreen, DanaScreen+DanaChatScreen/dana twins, ScenesScreen/ScenesGalleryScreen), two API clients, duplicated journal/notification services (**deferred** → Plan 10). ~800 `except Exception` swallow sites project-wide (top offenders: `ai/` 36 files) — swept opportunistically in Plans 8–9, not here.

## Global Constraints

- Run Python via the repo venv: `venv/Scripts/python.exe`. Tests: `venv/Scripts/python.exe -m pytest <path> -v`.
- Windows baseline: 8 pre-existing environmental failures (2× long_term_memory, 2× EncryptedText order-flake, 4× diarization). "Green" locally = no NEW failures beyond these. CI is the arbiter.
- Every task ends with the contract-test files green, then a commit. Never commit red.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Do NOT restructure `web_server.py` or `Storage/subscription_store.py` — that is Plans 8/9.
- Production flag convention (already in the codebase): `os.getenv("DANAH_ENV", "development").lower() == "production"` — use exactly this, do not invent a settings field.
- **Prerequisite before Task 1:** at least ~2 GB free on C:. If still full, do the manual disk step at the bottom of this plan first.

---

### Task 1: Bridge profile writes take the RW lock + stop the 2.5 s write churn (NEW-P0-A)

**Files:**
- Modify: `api/device_bridge.py` (all four public functions)
- Test: `tests/test_device_sync_contract.py` (append classes)

**Interfaces:**
- Consumes: `web_server._profile_rw()` (context manager holding `_PROFILE_RW_LOCK` for a full read-modify-write cycle, web_server.py:85-98), `web_server._parse_iso_timestamp`, existing `DeviceBridgeContractCase` helpers (`device_token`, `device_bearer`, `pair_bed`).
- Produces: `device_bridge.LAST_SEEN_PERSIST_SECONDS = 30` (module constant); `device_sync` persists the profile only when it dispatched commands or `last_seen` is stale by ≥ 30 s. All four functions hold `_profile_rw()` for their whole read→mutate→save cycle. No route/response changes.

- [x] **Step 1: Append the failing tests**

Append to `tests/test_device_sync_contract.py` (the file already imports `patch`, `Path`, `to_iso`, `utcnow`, `timedelta`; add `import concurrent.futures` at the top with the other imports):

```python
class DeviceSyncLockingTests(DeviceBridgeContractCase):
    """NEW-P0-A: the bridge's profile read-modify-write cycles must hold
    web_server._PROFILE_RW_LOCK — a bed polls every 2.5s and used to race
    every concurrent mobile profile write."""

    def test_sync_holds_profile_rw_lock_for_full_cycle(self):
        import web_server

        auth = self.register("bridge-lock@example.com")
        self.pair_bed(auth, "BED-LOCK-01")
        bundle = self.device_token("BED-LOCK-01")

        # Queue a command so the sync definitely persists (dispatch transition)
        resp = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "winddown"},
            headers=self.bearer(auth),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        real_save = web_server._save_profile
        probe_results: list[bool] = []

        def probing_save(payload):
            # Try to take the profile lock from ANOTHER thread mid-cycle.
            # If device_sync correctly wraps its cycle in _profile_rw(),
            # the lock is held and this acquire must fail.
            def try_acquire() -> bool:
                got = web_server._PROFILE_RW_LOCK.acquire(blocking=False)
                if got:
                    web_server._PROFILE_RW_LOCK.release()
                return got

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                probe_results.append(pool.submit(try_acquire).result())
            return real_save(payload)

        with patch.object(web_server, "_save_profile", side_effect=probing_save):
            resp = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(probe_results, "sync with a queued command must persist the profile")
        self.assertTrue(
            all(r is False for r in probe_results),
            "profile lock must be held across the whole read-modify-write cycle",
        )

    def test_sync_skips_redundant_profile_writes(self):
        import web_server

        auth = self.register("bridge-churn@example.com")
        self.pair_bed(auth, "BED-CHURN-01")
        bundle = self.device_token("BED-CHURN-01")
        headers = self.device_bearer(bundle)

        # First sync right after auth: last_seen is fresh, nothing queued.
        self.assertEqual(self.client.get("/v1/device/sync", headers=headers).status_code, 200)

        # Second sync seconds later: nothing changed -> must NOT rewrite the profile.
        with patch.object(web_server, "_save_profile") as save_spy:
            resp = self.client.get("/v1/device/sync", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        save_spy.assert_not_called()
```

- [x] **Step 2: Run to verify both FAIL for the right reasons**

Run: `venv/Scripts/python.exe -m pytest tests/test_device_sync_contract.py::DeviceSyncLockingTests -v`
Expected: `test_sync_holds_profile_rw_lock_for_full_cycle` FAILS on `all(r is False ...)` (lock not held today); `test_sync_skips_redundant_profile_writes` FAILS on `save_spy.assert_not_called()` (sync saves every poll today).

- [x] **Step 3: Fix `api/device_bridge.py`**

Add the constant near the top (after `LIVE_WINDOW_SECONDS = 15`):

```python
# device_sync persists last_seen at most this often; dispatch transitions
# always persist. Keeps the 2.5s bed poll from rewriting the profile JSON
# on every tick (audit 2026-07-18 NEW-P0-A).
LAST_SEEN_PERSIST_SECONDS = 30
```

Rewrite `device_auth` (only the body after the provisioning check changes — the profile cycle moves under the lock):

```python
def device_auth(payload: DeviceAuthRequest) -> dict[str, Any]:
    import web_server as ws

    device_id = _canonical_device_id(payload.device_id)
    if not device_id:
        raise HTTPException(status_code=422, detail="device_id is required")

    required_secret = os.getenv("DEVICE_FACTORY_SECRET", "").strip()
    if required_secret and not hmac.compare_digest(
        str(payload.factory_secret or ""), required_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid factory secret")

    from qr_code.pair_device import get_device_status

    status_payload = get_device_status(device_id)
    if not bool(status_payload.get("success", False)):
        raise HTTPException(status_code=404, detail="Device is not provisioned")

    with ws._profile_rw():
        profile = ws._safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        return _issue_device_bundle(ws, profile, device_id, payload.firmware_version)
```

(`_issue_device_bundle` calls `ws._save_profile` which re-acquires the same RLock — reentrant, safe.)

Rewrite `device_token_refresh` the same way — the whole read→verify→reissue cycle under the lock:

```python
def device_token_refresh(payload: DeviceTokenRefreshRequest) -> dict[str, Any]:
    import web_server as ws

    device_id = _canonical_device_id(payload.device_id)
    presented = str(payload.refresh_token or "").strip()
    if not device_id or not presented:
        raise HTTPException(status_code=422, detail="device_id and refresh_token are required")

    with ws._profile_rw():
        profile = ws._safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        sessions = ws._get_scoped_profile_section(profile, "device_sessions")
        row = sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
        stored_hash = str(row.get("refresh_token_hash", "") or "")
        if not stored_hash or not hmac.compare_digest(stored_hash, _hash_refresh_token(presented)):
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        return _issue_device_bundle(
            ws, profile, device_id, str(row.get("firmware_version", "") or "")
        )
```

Rewrite `device_sync` — full cycle under the lock, save gated on dispatch-or-stale:

```python
def device_sync(device: dict[str, Any]) -> dict[str, Any]:
    import web_server as ws

    device_id = str(device.get("device_id", "") or "")
    now = utcnow()
    with ws._profile_rw():
        profile = ws._safe_profile()
        if not isinstance(profile, dict):
            profile = {}

        sessions = ws._get_scoped_profile_section(profile, "device_sessions")
        session_row = (
            sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
        )
        prev_seen = ws._parse_iso_timestamp(str(session_row.get("last_seen", "") or ""))
        seen_stale = (
            prev_seen is None or (now - prev_seen).total_seconds() >= LAST_SEEN_PERSIST_SECONDS
        )
        session_row["last_seen"] = to_iso(now)
        sessions[device_id] = session_row
        profile["device_sessions"] = sessions

        key = _find_user_key_for_device(ws, profile, device_id)
        if not key:
            if seen_stale:
                ws._save_profile(profile)
            return {
                "server_time": to_iso(now),
                "commands": [],
                "desired_state": None,
                "state_version": "",
            }

        cmd_section = ws._get_scoped_profile_section(profile, "web_device_commands")
        raw_rows = cmd_section.get(key, [])
        raw_rows = raw_rows if isinstance(raw_rows, list) else []
        out_rows: list[dict[str, Any]] = []
        to_dispatch: list[dict[str, Any]] = []
        for row in raw_rows:
            cmd = ws._normalize_command_item(row if isinstance(row, dict) else {})
            status = str(cmd.get("status", "queued") or "queued")
            updated = ws._parse_iso_timestamp(str(cmd.get("updated_at", "") or "")) or now
            stale_dispatch = (
                status == "dispatched" and (now - updated).total_seconds() >= REDELIVER_SECONDS
            )
            if status == "queued" or stale_dispatch:
                cmd["status"] = "dispatched"
                cmd["updated_at"] = to_iso(now)
                to_dispatch.append(
                    {
                        "id": str(cmd.get("id", "") or ""),
                        "action": str(cmd.get("action", "") or ""),
                        "params": {},
                        "created_at": str(cmd.get("created_at", "") or ""),
                    }
                )
            out_rows.append(cmd)
        cmd_section[key] = out_rows
        profile["web_device_commands"] = cmd_section

        desired_state = _assemble_desired_state(ws, profile, key)
        if to_dispatch or seen_stale:
            ws._save_profile(profile)
    return {
        "server_time": to_iso(now),
        "commands": to_dispatch,
        "desired_state": desired_state,
        "state_version": _state_version(desired_state),
    }
```

Rewrite `device_command_result` — profile cycle under the lock; the DB write (`_persist_mobile_command_record`) stays OUTSIDE the lock (it does not touch the profile file, and holding a file lock across a DB call is needless serialization):

```python
def device_command_result(
    device: dict[str, Any], command_id: str, payload: DeviceCommandResultRequest
) -> dict[str, Any]:
    import web_server as ws

    device_id = str(device.get("device_id", "") or "")
    with ws._profile_rw():
        profile = ws._safe_profile()
        if not isinstance(profile, dict):
            profile = {}
        key = _find_user_key_for_device(ws, profile, device_id)
        if not key:
            raise HTTPException(status_code=404, detail="Device is not paired")

        cmd_section = ws._get_scoped_profile_section(profile, "web_device_commands")
        raw_rows = cmd_section.get(key, [])
        raw_rows = raw_rows if isinstance(raw_rows, list) else []
        target: dict[str, Any] | None = None
        out_rows: list[dict[str, Any]] = []
        for row in raw_rows:
            cmd = ws._normalize_command_item(row if isinstance(row, dict) else {})
            if str(cmd.get("id", "") or "") == str(command_id):
                cmd["status"] = payload.status
                cmd["updated_at"] = ws._now_utc_iso()
                if payload.status == "completed":
                    cmd["completed_at"] = ws._now_utc_iso()
                if payload.detail:
                    cmd["message"] = str(payload.detail)[:200]
                target = cmd
            out_rows.append(cmd)
        if target is None:
            raise HTTPException(status_code=404, detail="Command not found")

        cmd_section[key] = out_rows
        profile["web_device_commands"] = cmd_section
        ws._store_last_command_result(
            profile, key, ws._build_last_command_result_from_command(target)
        )
        ws._save_profile(profile)

        links = ws._get_scoped_profile_section(profile, "mobile_bed_links")
        link_row = links.get(key, {}) if isinstance(links.get(key, {}), dict) else {}

    ws._persist_mobile_command_record(
        user_id=str(link_row.get("user_id", "") or key), command=target
    )
    return {"ok": True, "command": target}
```

- [x] **Step 4: Run the bridge suite — green**

Run: `venv/Scripts/python.exe -m pytest tests/test_device_sync_contract.py tests/test_bed_command_poller.py -v`
Expected: ALL PASS (both new classes and all pre-existing bridge tests — the response shapes are unchanged).

- [x] **Step 5: Contract suite + commit**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -v` → green.

```bash
git add api/device_bridge.py tests/test_device_sync_contract.py
git commit -m "fix(bridge): profile cycles hold the RW lock; sync writes only on change (NEW-P0-A)"
```

---

### Task 2: Device auth is never open in production (NEW-P0-B)

**Files:**
- Modify: `api/device_bridge.py` (`device_auth`, lines with `required_secret`)
- Modify: `config/settings.py` (`validate_production_secrets`, after the AWS_SES check ~line 561)
- Test: `tests/test_device_sync_contract.py` (append class)

**Interfaces:**
- Consumes: `DANAH_ENV` production convention (Global Constraints).
- Produces: in production with `DEVICE_FACTORY_SECRET` unset, `POST /v1/device/auth` → 503 `"Device bridge is not configured"`; `validate_production_secrets()` gains a `DEVICE_FACTORY_SECRET` warning line (which Task 3 turns into a boot blocker).

- [x] **Step 1: Append the failing test** (`import os` is needed — add it to the test file's imports)

```python
class DeviceAuthProductionGateTests(DeviceBridgeContractCase):
    """NEW-P0-B: with no DEVICE_FACTORY_SECRET, /v1/device/auth is open —
    anyone with a provisioned serial can mint a device token. Production
    must refuse to serve open device auth."""

    def test_production_without_factory_secret_is_503(self):
        env = {"DANAH_ENV": "production", "DEVICE_FACTORY_SECRET": ""}
        with patch.dict(os.environ, env, clear=False):
            with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
                resp = self.client.post("/v1/device/auth", json={"device_id": "BED-P-01"})
        self.assertEqual(resp.status_code, 503, resp.text)

    def test_wrong_factory_secret_is_401(self):
        with patch.dict(os.environ, {"DEVICE_FACTORY_SECRET": "correct-secret"}, clear=False):
            with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
                resp = self.client.post(
                    "/v1/device/auth",
                    json={"device_id": "BED-P-02", "factory_secret": "wrong"},
                )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_correct_factory_secret_succeeds(self):
        with patch.dict(os.environ, {"DEVICE_FACTORY_SECRET": "correct-secret"}, clear=False):
            with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
                resp = self.client.post(
                    "/v1/device/auth",
                    json={"device_id": "BED-P-03", "factory_secret": "correct-secret"},
                )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["device_access_token"])

    def test_missing_secret_warns_for_production(self):
        from config.settings import validate_production_secrets

        env = {"DANAH_ENV": "production", "DEVICE_FACTORY_SECRET": ""}
        with patch.dict(os.environ, env, clear=False):
            warnings = validate_production_secrets()
        self.assertTrue(any("DEVICE_FACTORY_SECRET" in w for w in warnings), warnings)
```

- [x] **Step 2: Run to verify failure**

Run: `venv/Scripts/python.exe -m pytest tests/test_device_sync_contract.py::DeviceAuthProductionGateTests -v`
Expected: `test_production_without_factory_secret_is_503` FAILS (returns 200 today); `test_missing_secret_warns_for_production` FAILS (no such warning today); the 401/200 tests already pass.

- [x] **Step 3: Fix `device_auth`** — replace the `required_secret` block with:

```python
    required_secret = os.getenv("DEVICE_FACTORY_SECRET", "").strip()
    if not required_secret:
        if os.getenv("DANAH_ENV", "development").lower() == "production":
            # Never serve open device auth to a real fleet: anyone with a
            # serial could mint a device token (audit 2026-07-18 NEW-P0-B).
            raise HTTPException(status_code=503, detail="Device bridge is not configured")
    elif not hmac.compare_digest(str(payload.factory_secret or ""), required_secret):
        raise HTTPException(status_code=401, detail="Invalid factory secret")
```

- [x] **Step 4: Extend `validate_production_secrets`** — in `config/settings.py`, after the `aws_ses_from_email` check add:

```python
    if not os.getenv("DEVICE_FACTORY_SECRET", "").strip() and is_production:
        warnings.append(
            "DEVICE_FACTORY_SECRET not set — /v1/device/auth returns 503 until it is"
        )
```

- [x] **Step 5: Run tests + commit**

Run: `venv/Scripts/python.exe -m pytest tests/test_device_sync_contract.py -v` → green.

```bash
git add api/device_bridge.py config/settings.py tests/test_device_sync_contract.py
git commit -m "fix(bridge): device auth refuses to run open in production (NEW-P0-B)"
```

---

### Task 3: Missing production secrets block boot instead of logging (audit §6)

**Files:**
- Modify: `config/settings.py` (append after `validate_production_secrets`, ~line 564)
- Modify: `api/app_factory.py:39-47` (lifespan secrets block)
- Create: `tests/test_production_gates.py`

**Interfaces:**
- Produces: `config.settings.enforce_production_secrets() -> list[str]` — returns the warning list; raises `RuntimeError` when `DANAH_ENV=production` and the list is non-empty. The app_factory lifespan calls it with NO try/except (a production boot with missing secrets must die loudly, not limp).

- [x] **Step 1: Write the failing tests** — create `tests/test_production_gates.py`:

```python
"""Production fail-fast gates (audit §6: validate_production_secrets never blocked)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class EnforceProductionSecretsTests(unittest.TestCase):
    def test_dev_returns_warnings_without_raising(self):
        from config import settings as settings_module

        with patch.dict(os.environ, {"DANAH_ENV": "development"}, clear=False):
            with patch.object(
                settings_module, "validate_production_secrets", return_value=["X missing"]
            ):
                self.assertEqual(settings_module.enforce_production_secrets(), ["X missing"])

    def test_production_raises_on_warnings(self):
        from config import settings as settings_module

        with patch.dict(os.environ, {"DANAH_ENV": "production"}, clear=False):
            with patch.object(
                settings_module, "validate_production_secrets", return_value=["X missing"]
            ):
                with self.assertRaises(RuntimeError):
                    settings_module.enforce_production_secrets()

    def test_production_clean_boot_returns_empty(self):
        from config import settings as settings_module

        with patch.dict(os.environ, {"DANAH_ENV": "production"}, clear=False):
            with patch.object(settings_module, "validate_production_secrets", return_value=[]):
                self.assertEqual(settings_module.enforce_production_secrets(), [])


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run to verify failure**

Run: `venv/Scripts/python.exe -m pytest tests/test_production_gates.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'enforce_production_secrets'`.

- [x] **Step 3: Add the function** — in `config/settings.py`, directly after `validate_production_secrets`:

```python
def enforce_production_secrets() -> list[str]:
    """Fail-fast wrapper around validate_production_secrets.

    Dev: returns the warnings for the caller to log. Production
    (DANAH_ENV=production): raises so the app refuses to boot half-configured
    — the audit found warnings were logged and then ignored.
    """
    warnings = validate_production_secrets()
    if warnings and os.getenv("DANAH_ENV", "development").lower() == "production":
        raise RuntimeError(
            "Refusing to start with missing production secrets: " + "; ".join(warnings)
        )
    return warnings
```

- [x] **Step 4: Rewire the lifespan** — in `api/app_factory.py`, replace the lines 39-47 block (`# Validate production secrets on startup` through the `except ... "Secret validation error (non-fatal)"` clause) with:

```python
    # Validate production secrets on startup — warns in dev, refuses to boot
    # in production (deliberately NOT wrapped in try/except).
    from config.settings import enforce_production_secrets

    for w in enforce_production_secrets():
        logger.warning("Secret config: %s", w)
```

- [x] **Step 5: Run tests, contract suite, commit**

Run: `venv/Scripts/python.exe -m pytest tests/test_production_gates.py tests/test_app_factory_contract.py -v` → green (contract tests never run the lifespan, so nothing else changes).

```bash
git add config/settings.py api/app_factory.py tests/test_production_gates.py
git commit -m "fix(config): production boot fails on missing secrets instead of warning (audit S6)"
```

---

### Task 4: Truthful ops — migrations fail-fast in production, healthchecks hit /readyz (audit §4/§6)

**Files:**
- Modify: `scripts/docker-entrypoint.sh`
- Modify: `docker-compose.yml:46` (healthcheck test URL)
- Modify: `Dockerfile:45` (HEALTHCHECK URL)

**Interfaces:**
- Produces: entrypoint exits 1 on Alembic failure when `DANAH_ENV=production` (dev keeps the warn-and-continue behavior for DB-not-yet-up compose starts); container healthchecks probe `/readyz` (which actually checks DB/Redis) instead of `/healthz` (which checks nothing).

- [x] **Step 1: Rewrite `scripts/docker-entrypoint.sh`**

```bash
#!/usr/bin/env bash
# Docker entrypoint — runs Alembic migrations then starts the app.
set -e

echo "[entrypoint] Running database migrations..."
if ! python -m alembic upgrade head; then
  env_lower=$(echo "${DANAH_ENV:-development}" | tr '[:upper:]' '[:lower:]')
  if [ "$env_lower" = "production" ]; then
    echo "[entrypoint] FATAL: alembic migration failed in production — refusing to start" >&2
    exit 1
  fi
  echo "[entrypoint] WARNING: alembic migration failed (DB may not be ready)"
fi

echo "[entrypoint] Starting application..."
exec "$@"
```

- [x] **Step 2: Point both healthchecks at /readyz**

`docker-compose.yml` line 46: change
`test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]` →
`test: ["CMD", "curl", "-f", "http://localhost:8000/readyz"]`

`Dockerfile` line 45: change
`CMD curl -f http://localhost:${PORT:-8000}/healthz || exit 1` →
`CMD curl -f http://localhost:${PORT:-8000}/readyz || exit 1`

- [x] **Step 3: Verify + commit**

Run: `bash -n scripts/docker-entrypoint.sh` → no output (syntax OK).
Run: `grep -n "readyz" docker-compose.yml Dockerfile` → both hits present; `grep -n "healthz" docker-compose.yml Dockerfile` → no hits.

```bash
git add scripts/docker-entrypoint.sh docker-compose.yml Dockerfile
git commit -m "fix(deploy): migrations fail-fast in production; healthchecks probe /readyz (audit S4/S6)"
```

---

### Task 5: Delete the dead celery task queue (audit §3 duplication)

Compose runs the arq worker only; `tasks/celery_app.py` has no importers (verified 2026-07-18: the only "celery" hits outside it are `settings.celery_broker_url` — an alias that doubles as REDIS_URL and is used by health.py's Redis check — which stays).

**Files:**
- Delete: `tasks/celery_app.py`
- Modify: `requirements.txt` (remove the celery line if present)

- [x] **Step 1: Re-verify zero importers (abort if any appear)**

Run: `grep -rn "celery_app\|from celery\|import celery" --include="*.py" --exclude-dir={venv,.venv,.venv311,__pycache__} .`
Expected: hits ONLY inside `tasks/celery_app.py` itself. If any other file imports it, STOP — do not delete; report the importer instead.

- [x] **Step 2: Delete and clean requirements**

Run: `git rm tasks/celery_app.py`
Run: `grep -in "^celery" requirements.txt requirements-dev.txt requirements-pi.txt requirements-ml.txt` — remove any `celery==...` line found (leave `redis`/`arq` alone).

- [x] **Step 3: Prove the app still imports + commit**

Run: `venv/Scripts/python.exe -c "from api.app_factory import app; print('ok', len(app.routes))"`
Expected: `ok 255` (route count from the 2026-07-18 audit; any number ≥ 250 is fine — the point is a clean import).
Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -q` → green.

```bash
git add requirements.txt
git commit -m "chore: delete dead celery app — arq is the only task queue (audit S3)"
```

---

### Task 6: Delete both dead retry frameworks (audit §3 duplication)

2026-07-18 grep found `core/retry.py` imported by nothing, and `utils/retry.py` imported only by `utils/__init__.py`. Both are dead weight — but symbol-level re-verification is mandatory before deletion because callers may import via `from utils import <symbol>`.

**Files:**
- Delete: `core/retry.py`, `utils/retry.py`
- Modify: `utils/__init__.py` (remove the retry re-export)

- [x] **Step 1: Symbol-level verification (abort on any hit)**

List every top-level name each file defines:
Run: `grep -n "^def \|^class \|^[A-Z_]* =" core/retry.py utils/retry.py`

For EACH symbol name found, run:
`grep -rn "<symbol>" --include="*.py" --exclude-dir={venv,.venv,.venv311,__pycache__} . | grep -v "core/retry.py\|utils/retry.py\|utils/__init__.py"`
Expected: zero hits per symbol. If ANY symbol is referenced elsewhere, STOP for that file — keep it, delete only the truly dead one, and note the survivor in the commit message.

- [x] **Step 2: Delete + fix the package init**

Run: `git rm core/retry.py utils/retry.py`
Open `utils/__init__.py` and delete the line(s) importing from `.retry` (and any `__all__` entries naming its symbols).

- [x] **Step 3: Full suite + commit**

Run: `venv/Scripts/python.exe -m pytest -q` → no NEW failures beyond the Windows baseline.

```bash
git add utils/__init__.py
git commit -m "chore: delete both dead retry frameworks (audit S3 duplication)"
```

---

### Task 7: Repo hygiene — ignore and remove generated artifacts (NEW-BLOCKER-0, project share)

All three files are untracked, generated, and re-creatable (`repomix` output 134 MB, two old test logs). `.tmp/`, `runtime_data/tmp`, `output_audio`, `desktop.ini` are already gitignored.

**Files:**
- Modify: `.gitignore` (append)
- Delete (untracked, generated): `repomix-output.txt`, `test_results.txt`, `test_audit_unittest.log`

- [x] **Step 1: Append to `.gitignore`**

```
# Generated analysis/test artifacts — never commit
repomix-output.txt
test_results.txt
test_audit_unittest.log
```

- [x] **Step 2: Delete the artifacts (frees ~134 MB)**

Run: `rm repomix-output.txt test_results.txt test_audit_unittest.log`
(They are untracked — `git status` must show only the `.gitignore` change afterwards.)

- [x] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore + remove generated artifacts (134MB repomix dump, stale test logs)"
```

---

### Task 8: Final verification sweep — including the 9 disk-suspect test failures

**Files:** none (verification only)

- [x] **Step 1: Confirm free disk** — Run: `df -h /c | tail -1`. Expected: several GB available. If not, STOP and do the manual disk step below first; every result from a full disk is noise.

- [x] **Step 2: Re-run the 9 suspect failures from the 2026-07-18 run**

Run: `venv/Scripts/python.exe -m pytest tests/test_mobile_subscription_billing.py tests/test_mobile_timeline_db_events.py tests/test_mobile_timeline_db_first.py tests/test_mobile_vertical_slice_contract.py -v`
Expected: ALL PASS (they were disk-full casualties). If any still fail with free disk, they are REAL regressions from the Plan 5/6 commits — invoke superpowers:systematic-debugging on each before continuing; do not push with unexplained red.

- [x] **Step 3: Full suite** — Run: `venv/Scripts/python.exe -m pytest -q`. Expected: no failures beyond the 8-failure Windows baseline.

- [x] **Step 4: Lint** — Run: `venv/Scripts/python.exe -m ruff check .` → clean (fix anything flagged in files this plan touched).

- [x] **Step 5: Boot smoke** — Run: `venv/Scripts/python.exe -c "from fastapi.testclient import TestClient; from api.app_factory import app; c = TestClient(app); r = c.get('/healthz'); print(r.status_code, r.json())"` → `200 {...}`.

- [x] **Step 6: Update plan checkboxes, commit, push**

```bash
git add docs/superpowers/plans/2026-07-18-plan7-critical-blockers-and-dedup.md
git commit -m "docs: Plan 7 executed — new P0s closed, ops gates real, dead dup code deleted"
git push
```

---

## Manual step (user decision — NOT executed by this plan)

The C: drive is 100 % full. Inside the project, three virtualenvs exist: `venv/` (2.2 GB — the one every script and plan references), `.venv/` (2.7 GB), `.venv311/` (529 MB). Before deleting the extra two, check nothing references them:
`grep -rn "\.venv" scripts/ .claude/ *.md docs/ --include="*" -l`
If clean, removing `.venv/` and `.venv311/` frees ~3.2 GB. The rest of the full disk is outside this repo (Windows cleanup: temp files, Downloads, WinSxS, etc.).

## Follow-up plans (written just-in-time, per campaign convention)

| Plan | Scope (all verified still-open on 2026-07-18) |
|---|---|
| **Plan 8 — state → DB (campaign Phase 2)** | SubscriptionStore JSON sessions/checkout/idempotency/admin-audit → DB tables (unblocks GUNICORN_WORKERS>1); profile-JSON residual races: the ~19 unlocked `_save_profile` cycles in web_server, GET dashboard/timeline write-on-read (web_server.py ~6210, ~8500); device_sessions/bed_links/device_commands out of profile JSON; UndoManager/_CHAT_ENGINES/rate-limit per-process fallbacks. |
| **Plan 9 — web_server decomposition (campaign Phase 3)** | 11,035-line god module; 115 lazy-import seams in api/routers; second FastAPI app + second Sentry init (web_server.py:183 vs app_factory.py:68); pseudo-SSE (chat stream collects all chunks in a thread before emitting, web_server.py ~10229/10370/10577); service-registry merge (core/service_registry used by api/dependencies.py + api/monitoring.py vs api/service_registry); main.py shim (imported by 10 test files — migrate tests, then delete); except-Exception sweep of ai/ (36 files). |
| **Plan 10 — Flutter dedup (campaign Phase 4 leftovers)** | Merge the two routed UI trees — four live duplicate screen pairs (AlarmScreen/SmartAlarmScreen, IslamicScreen/IslamicModeScreen, DanaScreen+DanaChatScreen/dana twins, ScenesScreen/ScenesGalleryScreen); collapse two API clients (lib/src/core/api_client.dart Dio vs lib/services/api_service.dart http); dedupe journal_store + notification services (lib/services vs lib/src/core); fix ApiService.saveToken silent-swallow. |
| **Sensors upstream (campaign Phase 5 leftover)** | Bed→cloud telemetry: `/v1/mobile/sensors/live` returns nulls in cloud (SensorBridge has no hardware there); needs the bed to POST sensor readings via the device bridge and the route to read the stored readings. |
