# Device Command Bridge Implementation Plan (Plan 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The mobile app's device commands really reach the Pi and the Pi reports real results back — LED, alarms, scenes — with graceful fallback to the existing wall-clock simulator when no live bed is paired.

**Architecture:** Device-token short-poll bridge. New backend surface: `POST /v1/device/auth` + `POST /v1/device/token/refresh` (device JWT with `role="device"`), `GET /v1/device/sync` (commands + desired state), `POST /v1/device/commands/{id}/result`. Pi side: two new `BedBackendClient` methods + a `BedCommandPoller` daemon thread in `app_entry.py` sharing the existing `LEDController`/`ScheduleManager`. The wall-clock simulator in `_progress_user_commands` is gated off while the bed has synced within 15s.

**Tech Stack:** FastAPI (api.app_factory + web_server helpers), authlib JWT (`auth/jwt_handler.py`), JSON profile store (`web_server._safe_profile`/`_save_profile`), Python threading, unittest + FastAPI TestClient.

**Spec:** `docs/superpowers/specs/2026-07-16-device-command-bridge-design.md`

**⚠ Spec deviation discovered during planning:** the spec says "validates the *existing* device Bearer token (from `/v1/device/auth`)" — that endpoint **does not exist** on the backend (only the Pi client references it; it would 404). Task 1 builds device auth. Task 1 also amends the spec sentence.

## Global Constraints

- Windows dev box, py3.14 venv; **fast checks only** locally (new test files + contract suite); full suite runs on GitHub CI (Linux/py3.11 = arbiter). Never block on the 8 pre-existing local baseline failures (see `.superpowers/sdd/progress.md` ENV BASELINE).
- Run tests with the repo venv python: `python -m pytest <file> -v` (venv activated) from repo root.
- Lint before every commit: `ruff check .` and `ruff format <changed files>` (ruff pinned 0.15.20).
- Commit style: conventional (`feat(bridge): …`), end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Push to origin/main only at the end (Task 6), per campaign working mode.
- App dialect for alarm days is a list of ints **1–7 (Mon=1 … Sun=7)**; `ScheduleManager.repeat_days` is a comma-separated string of **0–6 (`datetime.weekday()`, Mon=0)**. Convert with `d - 1`.
- New backend logic lives in a NEW module `api/device_bridge.py` (keep the 10.3k-line `web_server.py` from growing); it lazy-imports `web_server` inside functions so test patching (`patch.object(web_server, …)`) keeps working. Routes go in the existing `api/routers/devices.py`.

## Existing API facts (verified 2026-07-17 — do not re-derive)

- `auth/jwt_handler.py`: `create_access_token(*, user_id, jti, exp, email="", client_name="", role="") -> str`; `decode_access_token(token) -> dict` (raises `JWTError`/`ExpiredSignatureError`). Claims: `sub`, `jti`, `type:"access"`, `iat`, `exp`, optional `role`.
- `auth/middleware.py`: `get_current_user` requires `type=="access"`, then a **DB revocation check** (`MobileAuthRepository().validate_access_token`) — device JWTs are not in that table, so device tokens are automatically rejected on all user routes with 401. `security = HTTPBearer(auto_error=False)`.
- `web_server.py` helpers (module-level): `_safe_profile()`, `_save_profile(payload)`, `_get_scoped_profile_section(profile, key) -> dict`, `_user_profile_key(user) -> str`, `_normalize_command_item(row) -> dict` (fields `id, action, event, message, status, trace_id, created_at, updated_at, completed_at`), `_parse_iso_timestamp(s) -> datetime|None`, `_now_utc_iso() -> str`, `_normalize_device_controls(d) -> {lights_on, audio_on, alarm_on, light_level}`, `_store_last_command_result(profile, key, result)`, `_build_last_command_result_from_command(cmd)`, `_persist_mobile_command_record(user_id, command)`, `PROFILE_PATH`.
- Profile sections: `web_device_commands[userkey] -> list[command rows]` (newest first, capped 60); `web_device_controls[userkey]`; `mobile_alarm_schedules[userkey] -> list[{alarm_id, time, days, enabled, label, sound, vibrate, created_at, updated_at}]`; `mobile_bed_links[userkey] -> {device_id, bed_location, paired_at, provisioning_verified, updated_at}`; `environment.saved_tonight_scene_key`; `web_last_command_result[userkey]`.
- Simulator: `web_server._progress_command_state(command, now)` (web_server.py:3178) advances on elapsed wall-clock (≥2s running, ≥5s completed). `_progress_user_commands(profile, key, user_id="")` (web_server.py:3201) maps it over the user's rows; 6 call sites.
- `POST /v1/mobile/device-commands` response: `{"ok", "action", "command_id", "command": {...}, "last_command_result", "message", "timeline"}`. `GET /v1/mobile/device-commands/{id}` response: `{"ok", "command", "last_command_result"}`. Catalog actions: `winddown, optimize_room, wake_recovery, reactive_lights, quiet_hours_override` (`_user_action_catalog`, web_server.py:3044). NOTE: `quiet_hours_override` returns early with `command_id: ""` and never queues a row — bridge tests use `winddown`/`optimize_room`.
- QR registry: `qr_code/pair_device.py` → `get_device_status(device_id) -> {success, user_id, bed_location, paired_at, ...}`; `web_server.mobile_bed_pair` (7847) writes `mobile_bed_links`, lazy-imports `qr_code.pair_device` inside the function, and gates on `web_server._load_registered_qr_device` + `web_server._pairing_claim_matches_device`.
- `Storage/schedule_manager.py`: `ScheduleManager.add_alarm(time_24h, label="Alarm", repeat_days="") -> AlarmItem(id, time_24h, label, enabled, next_trigger_iso, repeat_days)`; `remove_alarm(id) -> bool`; `list_alarms() -> List[AlarmItem]`; `is_valid_time_24h(s)`. Persists to `data/alarms.json`. `app_entry.process_due_alarms()` rings due alarms.
- `led/led_control.py` `LEDController`: `set_user_animation(name)` allowed `{"solid","breathing","pulse","rainbow","wave","strobe"}`; `set_user_brightness(float 0–1, capped)`; `set_color_value(name_or_hex)`; `set_state(state)`.
- `ai/environment_orchestrator.py` `EnvironmentOrchestrator.apply_scene(led, profile, scene)` where `scene = {key, animation, color, brightness, line}` (usage: app_entry.py:987–1003).
- `ai/bed_backend_client.py` `BedBackendClient._authorized_request(method, path, json=None) -> (ok: bool, body: dict|None, message: str)` — handles device auth + 401→refresh→retry. `_store_token_bundle` expects `{device_access_token, refresh_token, expires_at, entitlement}`.
- Contract test fixture: `tests/test_app_factory_contract.py::AppFactoryContractCase` — tmp sqlite `DATABASE_URL`, patched `web_server.store`, `reset_web_server_db_singletons`, plain `TestClient(app)` (no lifespan). Helpers `register(email)`, `bearer(auth)`.
- Scene catalog (web_server.py:2361): `calm_recovery` (brightness 0.25), `focus_momentum` (0.45), `discipline_night` (0.35), `balanced_default` (0.40).
- app_entry.py: `schedule = ScheduleManager()` (l.267), `environment_orchestrator` (l.272), `backend_client` (l.352), profile loaded (l.443), ring-automation wiring pattern to copy (l.519–537).

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `api/device_bridge.py` | create | All bridge logic: auth/refresh handlers, sync assembly, result recording. Lazy-imports web_server. |
| `auth/middleware.py` | modify | Add `get_current_device` dependency. |
| `api/routers/devices.py` | modify | Thin async route wrappers for the 4 new endpoints. |
| `web_server.py` | modify (small) | `_bed_is_live` helper + live-gate in `_progress_user_commands`; `user_id` added to bed-link row in `mobile_bed_pair`. |
| `ai/bed_backend_client.py` | modify | `fetch_sync()`, `report_command_result()`. |
| `ai/bed_command_poller.py` | create | `BedCommandPoller` thread: tick, handler map, reconciliation. |
| `app_entry.py` | modify (small) | Build + start poller after ring wiring. |
| `tests/test_device_sync_contract.py` | create | Backend contract tests (Tasks 1–3 accumulate here). |
| `tests/test_bed_backend_client_sync.py` | create | Client method unit tests. |
| `tests/test_bed_command_poller.py` | create | Poller unit tests with fakes. |

---

### Task 1: Device auth — `/v1/device/auth`, `/v1/device/token/refresh`, `get_current_device`

**Files:**
- Create: `api/device_bridge.py`
- Modify: `auth/middleware.py` (append), `api/routers/devices.py` (append)
- Create: `tests/test_device_sync_contract.py`
- Modify: `docs/superpowers/specs/2026-07-16-device-command-bridge-design.md` (one sentence)

**Interfaces:**
- Consumes: `create_access_token`/`decode_access_token` (auth/jwt_handler), `qr_code.pair_device.get_device_status`, web_server profile helpers.
- Produces:
  - `api.device_bridge.DeviceAuthRequest(device_id: str, firmware_version: str = "1.0.0", factory_secret: str = "")`
  - `api.device_bridge.DeviceTokenRefreshRequest(device_id: str, refresh_token: str)`
  - `api.device_bridge.device_auth(payload) -> dict` and `device_token_refresh(payload) -> dict` returning `{device_access_token, refresh_token, expires_at, entitlement}`
  - `auth.middleware.get_current_device` FastAPI dep -> `{"device_id": str}`
  - Profile section `device_sessions[device_id] = {refresh_token_hash, firmware_version, last_seen, created_at}`

- [ ] **Step 1: Write the failing contract tests**

Create `tests/test_device_sync_contract.py`:

```python
"""Contract tests for the device command bridge (app -> cloud -> bed).

Drives the PRODUCTION app (api.app_factory:app), like
tests/test_app_factory_contract.py. Device-facing routes authenticate with a
device JWT (role="device"), never the mobile user JWT.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from time_utils import to_iso, utcnow

from tests.test_app_factory_contract import AppFactoryContractCase

_QR_OK = {"success": True, "user_id": "", "bed_location": "Kuwait", "paired_at": ""}


class DeviceBridgeContractCase(AppFactoryContractCase):
    """Adds profile-store isolation + device helpers on top of the base fixture."""

    def setUp(self):
        super().setUp()
        import web_server

        profile_path = Path(self._tmp.name) / "profile.json"
        profile_path.write_text("{}", encoding="utf-8")
        self._profile_patcher = patch.object(web_server, "PROFILE_PATH", profile_path)
        self._profile_patcher.start()

    def tearDown(self):
        self._profile_patcher.stop()
        super().tearDown()

    # ── device helpers ────────────────────────────────────────────────────

    def device_token(self, device_id: str) -> dict:
        with patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)):
            resp = self.client.post(
                "/v1/device/auth",
                json={"device_id": device_id, "firmware_version": "1.0.0", "factory_secret": ""},
            )
        assert resp.status_code == 200, f"device auth failed: {resp.text}"
        return resp.json()

    def device_bearer(self, bundle: dict) -> dict:
        return {"Authorization": f"Bearer {bundle['device_access_token']}"}

    def pair_bed(self, auth: dict, device_id: str) -> str:
        """Pair a bed through the real API (QR service patched); return the profile key."""
        import web_server

        with (
            patch.object(
                web_server, "_load_registered_qr_device", return_value={"device_id": device_id}
            ),
            patch.object(web_server, "_pairing_claim_matches_device", return_value=True),
            patch("qr_code.pair_device.pair_device", return_value={"success": True}),
            patch("qr_code.pair_device.get_device_status", return_value=dict(_QR_OK)),
        ):
            resp = self.client.post(
                "/v1/mobile/bed/pair",
                json={"device_id": device_id, "qr_payload": "", "claim_token": ""},
                headers=self.bearer(auth),
            )
        assert resp.status_code == 200, f"pair failed: {resp.text}"
        profile = web_server._safe_profile()
        links = web_server._get_scoped_profile_section(profile, "mobile_bed_links")
        for key, row in links.items():
            if isinstance(row, dict) and str(row.get("device_id", "")) == device_id:
                return str(key)
        raise AssertionError("pairing did not create a bed link")


class DeviceAuthTests(DeviceBridgeContractCase):
    def test_device_auth_issues_token_bundle(self):
        bundle = self.device_token("bed-test-001")
        self.assertTrue(bundle["device_access_token"])
        self.assertTrue(bundle["refresh_token"])
        self.assertTrue(bundle["expires_at"])
        self.assertIn("entitlement", bundle)

    def test_device_auth_rejects_unprovisioned_device(self):
        with patch(
            "qr_code.pair_device.get_device_status", return_value={"success": False}
        ):
            resp = self.client.post(
                "/v1/device/auth",
                json={"device_id": "ghost-bed", "firmware_version": "1.0.0"},
            )
        self.assertEqual(resp.status_code, 404)

    def test_refresh_rotates_and_invalidates_old_token(self):
        bundle = self.device_token("bed-test-002")
        old_refresh = bundle["refresh_token"]
        resp = self.client.post(
            "/v1/device/token/refresh",
            json={"device_id": "bed-test-002", "refresh_token": old_refresh},
        )
        self.assertEqual(resp.status_code, 200)
        new_bundle = resp.json()
        self.assertNotEqual(new_bundle["refresh_token"], old_refresh)
        resp2 = self.client.post(
            "/v1/device/token/refresh",
            json={"device_id": "bed-test-002", "refresh_token": old_refresh},
        )
        self.assertEqual(resp2.status_code, 401)

    def test_device_token_rejected_on_mobile_route(self):
        bundle = self.device_token("bed-test-003")
        resp = self.client.get("/v1/mobile/dashboard", headers=self.device_bearer(bundle))
        self.assertEqual(resp.status_code, 401)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_device_sync_contract.py -v`
Expected: FAIL — `POST /v1/device/auth` returns 404 (route does not exist).

- [ ] **Step 3: Create `api/device_bridge.py` with auth handlers**

```python
"""Device command bridge — the app→cloud→bed seam (Plan 6).

Backend logic for device auth and (later tasks) sync + result reporting.
Lazy-imports web_server inside functions so contract-test patching of
web_server module attributes keeps working, and so importing this module
stays cheap.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from auth.jwt_handler import create_access_token
from time_utils import to_iso, utcnow

DEVICE_TOKEN_TTL_MINUTES = 60


class DeviceAuthRequest(BaseModel):
    device_id: str
    firmware_version: str = "1.0.0"
    factory_secret: str = ""


class DeviceTokenRefreshRequest(BaseModel):
    device_id: str
    refresh_token: str


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _default_entitlement() -> dict[str, Any]:
    return {"tier": "free", "status": "active", "cloud_enabled": False, "features": {}}


def _issue_device_bundle(ws, profile: dict[str, Any], device_id: str, firmware_version: str) -> dict[str, Any]:
    expires_at = utcnow() + timedelta(minutes=DEVICE_TOKEN_TTL_MINUTES)
    access_token = create_access_token(
        user_id=device_id,
        jti=secrets.token_hex(16),
        exp=expires_at,
        client_name="bed-device",
        role="device",
    )
    refresh_token = secrets.token_urlsafe(32)
    sessions = ws._get_scoped_profile_section(profile, "device_sessions")
    row = sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
    row.update(
        {
            "refresh_token_hash": _hash_refresh_token(refresh_token),
            "firmware_version": str(firmware_version or "1.0.0"),
            "last_seen": to_iso(utcnow()),
            "created_at": str(row.get("created_at", "") or "") or to_iso(utcnow()),
        }
    )
    sessions[device_id] = row
    profile["device_sessions"] = sessions
    ws._save_profile(profile)
    return {
        "device_access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": to_iso(expires_at),
        "entitlement": _default_entitlement(),
    }


def device_auth(payload: DeviceAuthRequest) -> dict[str, Any]:
    import web_server as ws

    device_id = str(payload.device_id or "").strip()
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

    profile = ws._safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    return _issue_device_bundle(ws, profile, device_id, payload.firmware_version)


def device_token_refresh(payload: DeviceTokenRefreshRequest) -> dict[str, Any]:
    import web_server as ws

    device_id = str(payload.device_id or "").strip()
    presented = str(payload.refresh_token or "").strip()
    if not device_id or not presented:
        raise HTTPException(status_code=422, detail="device_id and refresh_token are required")

    profile = ws._safe_profile()
    if not isinstance(profile, dict):
        profile = {}
    sessions = ws._get_scoped_profile_section(profile, "device_sessions")
    row = sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
    stored_hash = str(row.get("refresh_token_hash", "") or "")
    if not stored_hash or not hmac.compare_digest(stored_hash, _hash_refresh_token(presented)):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _issue_device_bundle(ws, profile, device_id, str(row.get("firmware_version", "") or ""))
```

- [ ] **Step 4: Add `get_current_device` to `auth/middleware.py`**

Append before `__all__` and add `"get_current_device"` to `__all__`:

```python
async def get_current_device(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Verify a device JWT (role="device") and return {"device_id": ...}.

    Device tokens are minted by /v1/device/auth with sub=device_id. They are
    not in the mobile session table, so get_current_user rejects them — and
    this dependency rejects user tokens (no device role claim), keeping the
    two token audiences strictly separated.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access" or payload.get("role") != "device":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    device_id = str(payload.get("sub", "") or "").strip()
    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"device_id": device_id}
```

- [ ] **Step 5: Add routes to `api/routers/devices.py`**

Append at the end of the file (module already imports `asyncio`, `Any`, `APIRouter`, `Depends`, `Request`):

```python
# ── Device bridge: auth (app→cloud→bed, Plan 6) ──────────────────────────────


@router.post("/v1/device/auth")
async def device_auth_route(request: Request) -> dict[str, Any]:
    from api.device_bridge import DeviceAuthRequest, device_auth as _bridge

    body = await request.json()
    payload = DeviceAuthRequest(**body)
    return await asyncio.to_thread(_bridge, payload)


@router.post("/v1/device/token/refresh")
async def device_token_refresh_route(request: Request) -> dict[str, Any]:
    from api.device_bridge import DeviceTokenRefreshRequest, device_token_refresh as _bridge

    body = await request.json()
    payload = DeviceTokenRefreshRequest(**body)
    return await asyncio.to_thread(_bridge, payload)
```

- [ ] **Step 6: Verify `_save_profile` writes via `web_server.PROFILE_PATH`**

Run: `grep -n "def _save_profile" -A 8 web_server.py` (lines ~876–890).
Expected: it writes through the module-global `PROFILE_PATH` (e.g. `locked_write_json(PROFILE_PATH, …)`), so the test's `patch.object(web_server, "PROFILE_PATH", …)` isolates both read and write. If it uses a different constant, patch that constant too in `DeviceBridgeContractCase.setUp`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_device_sync_contract.py -v`
Expected: 4 PASS.

- [ ] **Step 8: Amend the spec sentence + lint + commit**

In `docs/superpowers/specs/2026-07-16-device-command-bridge-design.md`, replace the sentence
"Validates the existing device Bearer token (from `/v1/device/auth`) and"
with
"Validates the device Bearer token issued by `/v1/device/auth` (built in this phase — the endpoint did not previously exist; the Pi client called it but got 404) and".

```bash
ruff check . && ruff format api/device_bridge.py auth/middleware.py api/routers/devices.py tests/test_device_sync_contract.py
git add api/device_bridge.py auth/middleware.py api/routers/devices.py tests/test_device_sync_contract.py docs/superpowers/specs/2026-07-16-device-command-bridge-design.md
git commit -m "feat(bridge): device auth — /v1/device/auth + token refresh + get_current_device

The Pi's BedBackendClient has called /v1/device/auth since it was written,
but the endpoint never existed on the backend (always 404). Mints device
JWTs (role=device, sub=device_id, 60min TTL) after QR-registry check +
optional DEVICE_FACTORY_SECRET gate; rotating refresh tokens hashed into
the device_sessions profile section.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `GET /v1/device/sync` — commands + desired state down to the bed

**Files:**
- Modify: `api/device_bridge.py` (append), `api/routers/devices.py` (append)
- Test: `tests/test_device_sync_contract.py` (append)

**Interfaces:**
- Consumes: `get_current_device` (Task 1), web_server helpers (`_normalize_command_item`, `_normalize_device_controls`, `_parse_iso_timestamp`, profile sections).
- Produces:
  - `api.device_bridge.device_sync(device: dict) -> dict` returning `{server_time, commands: [{id, action, params, created_at}], desired_state: {lighting, alarms, scene}|None, state_version: str}`
  - `api.device_bridge.REDELIVER_SECONDS = 30`, `LIVE_WINDOW_SECONDS = 15` (Task 3 imports the latter)
  - Route `GET /v1/device/sync`
  - Sync stamps `device_sessions[device_id].last_seen` and marks returned commands `dispatched`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device_sync_contract.py`:

```python
class DeviceSyncTests(DeviceBridgeContractCase):
    def test_sync_unpaired_device_returns_empty(self):
        bundle = self.device_token("bed-sync-000")
        resp = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["commands"], [])
        self.assertIsNone(body["desired_state"])
        self.assertEqual(body["state_version"], "")

    def test_sync_returns_queued_command_once_and_marks_dispatched(self):
        auth = self.register("sync-cmd@example.com")
        device_id = "bed-sync-001"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)

        create = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "winddown"},
            headers=self.bearer(auth),
        )
        self.assertEqual(create.status_code, 200, create.text)
        command_id = create.json()["command_id"]
        self.assertTrue(command_id)

        first = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(first.status_code, 200)
        actions = {c["id"]: c["action"] for c in first.json()["commands"]}
        self.assertEqual(actions.get(command_id), "winddown")

        second = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertEqual(
            [c["id"] for c in second.json()["commands"]],
            [],
            "already-dispatched command must not be re-offered within 30s",
        )

    def test_sync_desired_state_reflects_controls_and_alarms(self):
        auth = self.register("sync-state@example.com")
        device_id = "bed-sync-002"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)

        controls = self.client.post(
            "/v1/mobile/device-controls",
            json={"lights_on": True, "audio_on": False, "alarm_on": True, "light_level": 33},
            headers=self.bearer(auth),
        )
        self.assertEqual(controls.status_code, 200, controls.text)
        alarm = self.client.post(
            "/v1/mobile/alarms",
            json={"time": "06:45", "days": [1, 2, 3], "label": "Fajr", "enabled": True},
            headers=self.bearer(auth),
        )
        self.assertEqual(alarm.status_code, 200, alarm.text)

        resp = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        body = resp.json()
        state = body["desired_state"]
        self.assertEqual(state["lighting"]["light_level"], 33)
        self.assertTrue(state["lighting"]["lights_on"])
        times = [a["time"] for a in state["alarms"]]
        self.assertIn("06:45", times)
        self.assertTrue(body["state_version"])

    def test_user_jwt_rejected_on_sync(self):
        auth = self.register("sync-boundary@example.com")
        resp = self.client.get("/v1/device/sync", headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 401)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_device_sync_contract.py -v -k DeviceSyncTests`
Expected: FAIL — 404 on `/v1/device/sync`.

- [ ] **Step 3: Implement sync in `api/device_bridge.py`**

Append:

```python
import json as _json

REDELIVER_SECONDS = 30
LIVE_WINDOW_SECONDS = 15


def _find_user_key_for_device(ws, profile: dict[str, Any], device_id: str) -> str:
    links = ws._get_scoped_profile_section(profile, "mobile_bed_links")
    for key, row in links.items():
        if isinstance(row, dict) and str(row.get("device_id", "") or "").strip() == device_id:
            return str(key)
    return ""


def _assemble_desired_state(ws, profile: dict[str, Any], key: str) -> dict[str, Any]:
    controls_section = ws._get_scoped_profile_section(profile, "web_device_controls")
    controls = ws._normalize_device_controls(controls_section.get(key, {}))
    lighting = {
        "lights_on": bool(controls.get("lights_on", False)),
        "light_level": int(controls.get("light_level", 65) or 65),
    }

    alarms_section = ws._get_scoped_profile_section(profile, "mobile_alarm_schedules")
    raw_alarms = alarms_section.get(key, [])
    raw_alarms = raw_alarms if isinstance(raw_alarms, list) else []
    alarms = []
    for row in raw_alarms:
        if not isinstance(row, dict):
            continue
        alarms.append(
            {
                "alarm_id": str(row.get("alarm_id", "") or ""),
                "time": str(row.get("time", "07:00") or "07:00"),
                "days": [int(d) for d in row.get("days", []) if isinstance(d, (int, float))],
                "enabled": bool(row.get("enabled", True)),
                "label": str(row.get("label", "") or ""),
                "sound": str(row.get("sound", "default") or "default"),
                "vibrate": bool(row.get("vibrate", True)),
            }
        )

    env = profile.get("environment", {}) if isinstance(profile.get("environment", {}), dict) else {}
    scene_key = str(env.get("saved_tonight_scene_key", "") or "").strip()
    scene = {"scene_key": scene_key} if scene_key else None
    return {"lighting": lighting, "alarms": alarms, "scene": scene}


def _state_version(desired_state: dict[str, Any] | None) -> str:
    if not desired_state:
        return ""
    canonical = _json.dumps(desired_state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def device_sync(device: dict[str, Any]) -> dict[str, Any]:
    import web_server as ws

    device_id = str(device.get("device_id", "") or "")
    now = utcnow()
    profile = ws._safe_profile()
    if not isinstance(profile, dict):
        profile = {}

    sessions = ws._get_scoped_profile_section(profile, "device_sessions")
    session_row = sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
    session_row["last_seen"] = to_iso(now)
    sessions[device_id] = session_row
    profile["device_sessions"] = sessions

    key = _find_user_key_for_device(ws, profile, device_id)
    if not key:
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
    ws._save_profile(profile)
    return {
        "server_time": to_iso(now),
        "commands": to_dispatch,
        "desired_state": desired_state,
        "state_version": _state_version(desired_state),
    }
```

Note: move the `import json as _json` line up with the other imports at the top of the module when appending (ruff will flag it otherwise).

- [ ] **Step 4: Add the route**

Append to `api/routers/devices.py` (add `from auth.middleware import get_current_device` next to the existing `get_current_user` import at the top):

```python
@router.get("/v1/device/sync")
async def device_sync_route(device: dict = Depends(get_current_device)) -> dict[str, Any]:
    from api.device_bridge import device_sync as _bridge

    return await asyncio.to_thread(_bridge, device)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_device_sync_contract.py -v`
Expected: all PASS (Task 1's 4 + these 4). If `POST /v1/mobile/alarms` uses a different body dialect, check `tests/test_app_factory_contract.py` for the alarm contract shape (Plan 1 fixed it to `alarm_id/time/days 1-7/sound/vibrate`) and match it.

- [ ] **Step 6: Lint + commit**

```bash
ruff check . && ruff format api/device_bridge.py api/routers/devices.py tests/test_device_sync_contract.py
git add api/device_bridge.py api/routers/devices.py tests/test_device_sync_contract.py
git commit -m "feat(bridge): GET /v1/device/sync — bed pulls commands + desired state

Short-poll endpoint (device JWT): returns queued commands (marked
dispatched, re-offered after 30s if unacknowledged) plus desired state
assembled from web_device_controls, mobile_alarm_schedules and the saved
scene; stamps device last_seen as the liveness heartbeat.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `POST /v1/device/commands/{id}/result` + live-bed simulator gate

**Files:**
- Modify: `api/device_bridge.py` (append), `api/routers/devices.py` (append), `web_server.py` (3 small edits)
- Test: `tests/test_device_sync_contract.py` (append)

**Interfaces:**
- Consumes: `LIVE_WINDOW_SECONDS` (Task 2), `_store_last_command_result` / `_build_last_command_result_from_command` / `_persist_mobile_command_record` (web_server).
- Produces:
  - `api.device_bridge.DeviceCommandResultRequest(status: Literal["completed","failed"], detail: str = "", actual_state: dict = {})`
  - `api.device_bridge.device_command_result(device, command_id, payload) -> {"ok": True, "command": {...}}`
  - `web_server._bed_is_live(profile, key) -> bool`; `_progress_user_commands` returns rows un-advanced when live
  - `mobile_bed_pair` link rows gain `"user_id"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device_sync_contract.py`:

```python
class DeviceResultAndToggleTests(DeviceBridgeContractCase):
    def _seed_old_command(self, key: str, command_id: str, seconds_ago: int = 10) -> None:
        import web_server

        profile = web_server._safe_profile()
        old_iso = to_iso(utcnow() - timedelta(seconds=seconds_ago))
        section = web_server._get_scoped_profile_section(profile, "web_device_commands")
        section[key] = [
            {
                "id": command_id,
                "action": "winddown",
                "event": "Wind-down autopilot started",
                "message": "Wind-down autopilot is now active.",
                "status": "queued",
                "trace_id": "",
                "created_at": old_iso,
                "updated_at": old_iso,
                "completed_at": "",
            }
        ]
        profile["web_device_commands"] = section
        web_server._save_profile(profile)

    def test_real_result_reaches_mobile_status(self):
        auth = self.register("loop@example.com")
        device_id = "bed-loop-001"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)

        create = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "optimize_room"},
            headers=self.bearer(auth),
        )
        command_id = create.json()["command_id"]

        sync = self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.assertIn(command_id, [c["id"] for c in sync.json()["commands"]])

        result = self.client.post(
            f"/v1/device/commands/{command_id}/result",
            json={"status": "completed", "detail": "Scene applied on bed.", "actual_state": {}},
            headers=self.device_bearer(bundle),
        )
        self.assertEqual(result.status_code, 200, result.text)

        status = self.client.get(
            f"/v1/mobile/device-commands/{command_id}", headers=self.bearer(auth)
        )
        self.assertEqual(status.json()["command"]["status"], "completed")

    def test_failed_result_marks_failed(self):
        auth = self.register("loop-fail@example.com")
        device_id = "bed-loop-002"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)
        create = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "winddown"},
            headers=self.bearer(auth),
        )
        command_id = create.json()["command_id"]
        self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))
        self.client.post(
            f"/v1/device/commands/{command_id}/result",
            json={"status": "failed", "detail": "LED bus unavailable"},
            headers=self.device_bearer(bundle),
        )
        status = self.client.get(
            f"/v1/mobile/device-commands/{command_id}", headers=self.bearer(auth)
        )
        self.assertEqual(status.json()["command"]["status"], "failed")

    def test_simulator_suppressed_while_bed_live(self):
        auth = self.register("toggle-live@example.com")
        device_id = "bed-toggle-001"
        key = self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)
        self.client.get("/v1/device/sync", headers=self.device_bearer(bundle))  # last_seen = now

        self._seed_old_command(key, "cmd_toggle_live_1", seconds_ago=10)
        status = self.client.get(
            "/v1/mobile/device-commands/cmd_toggle_live_1", headers=self.bearer(auth)
        )
        self.assertNotIn(
            status.json()["command"]["status"],
            {"completed", "running"},
            "wall-clock simulator must not advance while the bed is live",
        )

    def test_simulator_advances_when_no_bed_live(self):
        auth = self.register("toggle-stale@example.com")
        device_id = "bed-toggle-002"
        key = self.pair_bed(auth, device_id)
        # No device sync — last_seen never stamped.
        self._seed_old_command(key, "cmd_toggle_stale_1", seconds_ago=10)
        status = self.client.get(
            "/v1/mobile/device-commands/cmd_toggle_stale_1", headers=self.bearer(auth)
        )
        self.assertEqual(status.json()["command"]["status"], "completed")

    def test_result_unknown_command_404(self):
        auth = self.register("loop-404@example.com")
        device_id = "bed-loop-404"
        self.pair_bed(auth, device_id)
        bundle = self.device_token(device_id)
        resp = self.client.post(
            "/v1/device/commands/cmd_does_not_exist/result",
            json={"status": "completed"},
            headers=self.device_bearer(bundle),
        )
        self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_device_sync_contract.py -v -k DeviceResultAndToggleTests`
Expected: FAIL — 404 on the result route; `test_simulator_suppressed_while_bed_live` fails with status "completed".

- [ ] **Step 3: Implement the result handler in `api/device_bridge.py`**

Append:

```python
class DeviceCommandResultRequest(BaseModel):
    status: Literal["completed", "failed"]
    detail: str = ""
    actual_state: dict = Field(default_factory=dict)


def device_command_result(
    device: dict[str, Any], command_id: str, payload: DeviceCommandResultRequest
) -> dict[str, Any]:
    import web_server as ws

    device_id = str(device.get("device_id", "") or "")
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

- [ ] **Step 4: Add the route**

Append to `api/routers/devices.py`:

```python
@router.post("/v1/device/commands/{command_id}/result")
async def device_command_result_route(
    command_id: str, request: Request, device: dict = Depends(get_current_device)
) -> dict[str, Any]:
    from api.device_bridge import DeviceCommandResultRequest, device_command_result as _bridge

    body = await request.json()
    payload = DeviceCommandResultRequest(**body)
    return await asyncio.to_thread(_bridge, device, command_id, payload)
```

- [ ] **Step 5: Gate the simulator in `web_server.py`**

Edit 1 — add `_bed_is_live` directly above `_progress_command_state` (web_server.py:3178):

```python
def _bed_is_live(profile: dict[str, Any], key: str) -> bool:
    """True when the user's paired bed has polled /v1/device/sync recently.

    While live, the wall-clock command simulator must not advance statuses —
    the bed reports real results via /v1/device/commands/{id}/result.
    """
    from api.device_bridge import LIVE_WINDOW_SECONDS

    links = _get_scoped_profile_section(profile, "mobile_bed_links")
    link_row = links.get(key, {}) if isinstance(links.get(key, {}), dict) else {}
    device_id = str(link_row.get("device_id", "") or "").strip()
    if not device_id:
        return False
    sessions = _get_scoped_profile_section(profile, "device_sessions")
    session = sessions.get(device_id, {}) if isinstance(sessions.get(device_id, {}), dict) else {}
    last_seen = _parse_iso_timestamp(str(session.get("last_seen", "") or ""))
    if last_seen is None:
        return False
    return (utcnow() - last_seen).total_seconds() <= LIVE_WINDOW_SECONDS
```

Edit 2 — in `_progress_user_commands` (web_server.py:3201), insert the gate after `raw_rows` is computed and before `now = utcnow()`:

```python
    if _bed_is_live(profile, key):
        out = [_normalize_command_item(r if isinstance(r, dict) else {}) for r in raw_rows]
        return out[:60], False
```

Edit 3 — in `mobile_bed_pair` (web_server.py:7912), add the user id to the link row so the bridge can persist DB records under the right user:

```python
    links[key] = {
        "device_id": device_id,
        "user_id": user_id,
        "bed_location": str(status_payload.get("bed_location", "") or bed_location),
        "paired_at": str(status_payload.get("paired_at", "") or _now_utc_iso()),
        "provisioning_verified": True,
        "updated_at": _now_utc_iso(),
    }
```

- [ ] **Step 6: Run the whole contract file**

Run: `python -m pytest tests/test_device_sync_contract.py -v`
Expected: all PASS (Tasks 1–3, 14 tests).

- [ ] **Step 7: Guard against regressions in the existing contract suite**

Run: `python -m pytest tests/test_app_factory_contract.py tests/test_web_last_command_result.py tests/test_mobile_command_feedback_loop.py -v`
Expected: PASS (these exercise `_progress_user_commands` paths — the gate must be invisible when no bed is paired).

- [ ] **Step 8: Lint + commit**

```bash
ruff check . && ruff format api/device_bridge.py api/routers/devices.py web_server.py tests/test_device_sync_contract.py
git add api/device_bridge.py api/routers/devices.py web_server.py tests/test_device_sync_contract.py
git commit -m "feat(bridge): real device results + live-bed gate on the command simulator

POST /v1/device/commands/{id}/result writes the bed's real outcome into
web_device_commands + web_last_command_result, so the app's status
endpoint shows truth with zero app changes. While the bed has synced
within 15s, _progress_user_commands no longer advances statuses on
wall-clock time; with no live bed the simulator behaves exactly as before.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Pi client — `fetch_sync` + `report_command_result`

**Files:**
- Modify: `ai/bed_backend_client.py` (append methods to `BedBackendClient`)
- Create: `tests/test_bed_backend_client_sync.py`

**Interfaces:**
- Consumes: `BedBackendClient._authorized_request(method, path, json=None) -> (bool, dict|None, str)`.
- Produces:
  - `BedBackendClient.fetch_sync() -> tuple[bool, dict, str]`
  - `BedBackendClient.report_command_result(command_id: str, status: str, detail: str = "", actual_state: dict | None = None) -> tuple[bool, str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bed_backend_client_sync.py`:

```python
"""Unit tests for the BedBackendClient device-sync methods (Plan 6)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai.bed_backend_client import BedBackendClient


class FetchSyncTests(unittest.TestCase):
    def _client(self) -> BedBackendClient:
        return BedBackendClient(base_url="http://backend.test", device_id="bed-unit-1")

    def test_fetch_sync_returns_body(self):
        client = self._client()
        payload = {"commands": [], "desired_state": None, "state_version": ""}
        with patch.object(
            client, "_authorized_request", return_value=(True, payload, "ok")
        ) as mocked:
            ok, body, message = client.fetch_sync()
        self.assertTrue(ok)
        self.assertEqual(body, payload)
        mocked.assert_called_once_with("GET", "/v1/device/sync")

    def test_fetch_sync_failure_returns_empty_dict(self):
        client = self._client()
        with patch.object(
            client, "_authorized_request", return_value=(False, None, "Backend request failed.")
        ):
            ok, body, message = client.fetch_sync()
        self.assertFalse(ok)
        self.assertEqual(body, {})
        self.assertEqual(message, "Backend request failed.")

    def test_report_command_result_posts_payload(self):
        client = self._client()
        with patch.object(
            client, "_authorized_request", return_value=(True, {"ok": True}, "ok")
        ) as mocked:
            ok, message = client.report_command_result(
                "cmd_1", "completed", detail="done", actual_state={"animation": "breathing"}
            )
        self.assertTrue(ok)
        mocked.assert_called_once_with(
            "POST",
            "/v1/device/commands/cmd_1/result",
            json={
                "status": "completed",
                "detail": "done",
                "actual_state": {"animation": "breathing"},
            },
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bed_backend_client_sync.py -v`
Expected: FAIL — `AttributeError: 'BedBackendClient' object has no attribute 'fetch_sync'`.

- [ ] **Step 3: Implement the methods**

Append inside `BedBackendClient` (after `is_feature_allowed`, before `status_line`):

```python
    def fetch_sync(self) -> tuple[bool, dict, str]:
        """Poll the backend for pending commands + desired state."""
        ok, body, message = self._authorized_request("GET", "/v1/device/sync")
        if not ok or not isinstance(body, dict):
            return False, {}, message
        return True, body, "ok"

    def report_command_result(
        self,
        command_id: str,
        status: str,
        detail: str = "",
        actual_state: Optional[dict] = None,
    ) -> tuple[bool, str]:
        """Report a command's real outcome ("completed" or "failed")."""
        payload = {
            "status": status,
            "detail": detail,
            "actual_state": actual_state or {},
        }
        ok, _body, message = self._authorized_request(
            "POST", f"/v1/device/commands/{command_id}/result", json=payload
        )
        return ok, message
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bed_backend_client_sync.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check . && ruff format ai/bed_backend_client.py tests/test_bed_backend_client_sync.py
git add ai/bed_backend_client.py tests/test_bed_backend_client_sync.py
git commit -m "feat(pi): BedBackendClient learns fetch_sync + report_command_result

Reuses the existing device-auth/refresh plumbing; the client previously
had no way to receive app commands or report outcomes.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `BedCommandPoller` — the Pi-side bridge loop

**Files:**
- Create: `ai/bed_command_poller.py`
- Create: `tests/test_bed_command_poller.py`

**Interfaces:**
- Consumes: `BedBackendClient.fetch_sync` / `report_command_result` (Task 4), `LEDController` (`set_user_animation`, `set_user_brightness`, `set_color_value`), `ScheduleManager` (`add_alarm(time_24h, label, repeat_days)`, `remove_alarm(id)`, `list_alarms()`), `EnvironmentOrchestrator.apply_scene(led, profile, scene)`, `Storage.schedule_manager.is_valid_time_24h`.
- Produces: `ai.bed_command_poller.BedCommandPoller(backend_client, led, schedule, environment_orchestrator, profile, poll_interval_seconds=2.5)` with `start()`, `stop()`, `_tick()` (tick is unit-testable synchronously). Constant `ALARM_LABEL_PREFIX = "[app]"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bed_command_poller.py`:

```python
"""Unit tests for BedCommandPoller (Plan 6) — fakes only, no hardware/thread."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from ai.bed_command_poller import ALARM_LABEL_PREFIX, BedCommandPoller


class FakeBackend:
    def __init__(self, payload: dict):
        self.payload = payload
        self.results: list[tuple[str, str, str]] = []

    def fetch_sync(self):
        return True, self.payload, "ok"

    def report_command_result(self, command_id, status, detail="", actual_state=None):
        self.results.append((command_id, status, detail))
        return True, "ok"


class FakeLed:
    def __init__(self):
        self.calls: list[tuple] = []

    def set_user_animation(self, name):
        self.calls.append(("animation", name))

    def set_user_brightness(self, value, log=True):
        self.calls.append(("brightness", round(float(value), 3)))

    def set_color_value(self, value):
        self.calls.append(("color", value))


class FakeSchedule:
    def __init__(self):
        self.alarms: list[SimpleNamespace] = []

    def add_alarm(self, time_24h, label="Alarm", repeat_days=""):
        item = SimpleNamespace(
            id=uuid4().hex[:8], time_24h=time_24h, label=label,
            enabled=True, next_trigger_iso="", repeat_days=repeat_days,
        )
        self.alarms.append(item)
        return item

    def remove_alarm(self, alarm_id):
        before = len(self.alarms)
        self.alarms = [a for a in self.alarms if a.id != alarm_id]
        return len(self.alarms) != before

    def list_alarms(self):
        return list(self.alarms)


class FakeOrchestrator:
    def __init__(self):
        self.scenes: list[dict] = []

    def apply_scene(self, led, profile, scene):
        self.scenes.append(scene)
        return str(scene.get("line", ""))


def make_poller(payload: dict):
    backend = FakeBackend(payload)
    led = FakeLed()
    schedule = FakeSchedule()
    orchestrator = FakeOrchestrator()
    poller = BedCommandPoller(
        backend_client=backend,
        led=led,
        schedule=schedule,
        environment_orchestrator=orchestrator,
        profile={"preferences": {"favorite_color": "teal"}},
    )
    return poller, backend, led, schedule, orchestrator


def sync_payload(commands=None, desired_state=None, state_version=""):
    return {
        "server_time": "2026-07-17T00:00:00+00:00",
        "commands": commands or [],
        "desired_state": desired_state,
        "state_version": state_version,
    }


class CommandDispatchTests(unittest.TestCase):
    def test_known_command_reports_completed(self):
        payload = sync_payload(commands=[{"id": "c1", "action": "winddown", "params": {}}])
        poller, backend, led, _, _ = make_poller(payload)
        poller._tick()
        self.assertEqual(backend.results[0][:2], ("c1", "completed"))
        self.assertIn(("animation", "breathing"), led.calls)

    def test_unknown_action_reports_failed(self):
        payload = sync_payload(commands=[{"id": "c2", "action": "teleport", "params": {}}])
        poller, backend, _, _, _ = make_poller(payload)
        poller._tick()
        self.assertEqual(backend.results[0][:2], ("c2", "failed"))

    def test_handler_exception_reports_failed_and_loop_survives(self):
        payload = sync_payload(
            commands=[
                {"id": "bad", "action": "winddown", "params": {}},
                {"id": "good", "action": "wake_recovery", "params": {}},
            ]
        )
        poller, backend, led, _, _ = make_poller(payload)

        def boom(params):
            raise RuntimeError("SPI bus locked")

        poller._handlers["winddown"] = boom
        poller._tick()
        statuses = {cid: status for cid, status, _ in backend.results}
        self.assertEqual(statuses["bad"], "failed")
        self.assertEqual(statuses["good"], "completed")


class ReconcileTests(unittest.TestCase):
    def test_alarms_reconcile_owns_only_app_alarms(self):
        desired = {
            "lighting": {"lights_on": True, "light_level": 40},
            "alarms": [
                {"alarm_id": "a1", "time": "06:30", "days": [1, 2], "enabled": True,
                 "label": "Fajr", "sound": "default", "vibrate": True},
                {"alarm_id": "a2", "time": "22:00", "days": [], "enabled": False,
                 "label": "Off", "sound": "default", "vibrate": True},
            ],
            "scene": None,
        }
        poller, _, _, schedule, _ = make_poller(sync_payload(desired_state=desired, state_version="v1"))
        schedule.add_alarm("05:00", label="voice alarm")  # not app-owned
        schedule.add_alarm("09:00", label=f"{ALARM_LABEL_PREFIX} stale")  # app-owned leftover
        poller._tick()
        labels = [a.label for a in schedule.list_alarms()]
        self.assertIn("voice alarm", labels)
        self.assertNotIn(f"{ALARM_LABEL_PREFIX} stale", labels)
        app_alarms = [a for a in schedule.list_alarms() if a.label.startswith(ALARM_LABEL_PREFIX)]
        self.assertEqual(len(app_alarms), 1)
        self.assertEqual(app_alarms[0].time_24h, "06:30")
        self.assertEqual(app_alarms[0].repeat_days, "0,1")  # app days 1,2 -> weekday 0,1

    def test_scene_applied_via_orchestrator(self):
        desired = {"lighting": {"lights_on": True, "light_level": 45},
                   "alarms": [], "scene": {"scene_key": "calm_recovery"}}
        poller, _, _, _, orchestrator = make_poller(
            sync_payload(desired_state=desired, state_version="v1")
        )
        poller._tick()
        self.assertEqual(orchestrator.scenes[0]["key"], "calm_recovery")
        self.assertEqual(orchestrator.scenes[0]["animation"], "breathing")

    def test_unchanged_state_version_skips_reconcile(self):
        desired = {"lighting": {"lights_on": True, "light_level": 45},
                   "alarms": [], "scene": {"scene_key": "calm_recovery"}}
        poller, _, _, _, orchestrator = make_poller(
            sync_payload(desired_state=desired, state_version="v1")
        )
        poller._tick()
        poller._tick()
        self.assertEqual(len(orchestrator.scenes), 1)

    def test_lights_off_wins_over_scene(self):
        desired = {"lighting": {"lights_on": False, "light_level": 45},
                   "alarms": [], "scene": {"scene_key": "calm_recovery"}}
        poller, _, led, _, _ = make_poller(
            sync_payload(desired_state=desired, state_version="v1")
        )
        poller._tick()
        self.assertEqual(led.calls[-1], ("brightness", 0.0))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bed_command_poller.py -v`
Expected: FAIL — `ModuleNotFoundError: ai.bed_command_poller`.

- [ ] **Step 3: Create `ai/bed_command_poller.py`**

```python
"""BedCommandPoller — the Pi side of the app→cloud→bed command bridge (Plan 6).

A daemon thread that short-polls GET /v1/device/sync (~2.5s), executes
commands on the real hardware through a handler map, reconciles the backend's
desired state (lighting, alarms, scene) onto the shared LEDController /
ScheduleManager, and reports real results back. Runs inside app_entry.py so
one process owns the SPI LED bus.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from loguru import logger

from Storage.schedule_manager import is_valid_time_24h

ALARM_LABEL_PREFIX = "[app]"

# Scene key -> LED parameters. Brightness values mirror the backend's
# _scene_catalog; color/animation realize each scene's description on strip.
SCENE_LED_MAP: dict[str, dict[str, Any]] = {
    "calm_recovery": {"color": "cyan", "animation": "breathing", "brightness": 0.25},
    "focus_momentum": {"color": "white", "animation": "pulse", "brightness": 0.45},
    "discipline_night": {"color": "blue", "animation": "wave", "brightness": 0.35},
    "balanced_default": {"color": "white", "animation": "solid", "brightness": 0.40},
}

HandlerResult = tuple[bool, str, dict[str, Any]]


class BedCommandPoller:
    def __init__(
        self,
        backend_client,
        led,
        schedule,
        environment_orchestrator,
        profile: dict[str, Any],
        poll_interval_seconds: float = 2.5,
    ):
        self.backend_client = backend_client
        self.led = led
        self.schedule = schedule
        self.environment_orchestrator = environment_orchestrator
        self.profile = profile
        self.poll_interval_seconds = float(poll_interval_seconds)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_state_version = ""
        self._handlers: dict[str, Callable[[dict[str, Any]], HandlerResult]] = {
            "winddown": self._handle_winddown,
            "optimize_room": self._handle_optimize_room,
            "wake_recovery": self._handle_wake_recovery,
            "reactive_lights": self._handle_reactive_lights,
            "quiet_hours_override": self._handle_quiet_hours_override,
        }

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="bed-command-poller", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval_seconds + 2)
            self._thread = None

    def _run(self) -> None:
        logger.info("Bed command poller running (every {}s).", self.poll_interval_seconds)
        while not self._stop_event.wait(self.poll_interval_seconds):
            try:
                self._tick()
            except Exception as exc:
                logger.warning("Bed command poller tick failed: {}", exc)

    # ── one poll cycle ────────────────────────────────────────────────────

    def _tick(self) -> None:
        ok, body, message = self.backend_client.fetch_sync()
        if not ok:
            logger.debug("Device sync unavailable: {}", message)
            return
        for command in body.get("commands", []) or []:
            if isinstance(command, dict):
                self._execute_command(command)
        version = str(body.get("state_version", "") or "")
        desired = body.get("desired_state")
        if isinstance(desired, dict) and version and version != self._last_state_version:
            self._reconcile(desired)
            self._last_state_version = version

    def _execute_command(self, command: dict[str, Any]) -> None:
        command_id = str(command.get("id", "") or "")
        action = str(command.get("action", "") or "").strip().lower()
        params = command.get("params") if isinstance(command.get("params"), dict) else {}
        handler = self._handlers.get(action)
        if handler is None:
            self.backend_client.report_command_result(
                command_id, "failed", f"unsupported action: {action}", {}
            )
            return
        try:
            ok, detail, actual_state = handler(params)
        except Exception as exc:
            logger.warning("Command {} ({}) failed: {}", command_id, action, exc)
            self.backend_client.report_command_result(
                command_id, "failed", f"{type(exc).__name__}: {exc}", {}
            )
            return
        self.backend_client.report_command_result(
            command_id, "completed" if ok else "failed", detail, actual_state
        )
        logger.info("App command executed: {} -> {}", action, detail)

    # ── desired-state reconciliation ──────────────────────────────────────

    def _reconcile(self, desired: dict[str, Any]) -> None:
        try:
            self._reconcile_scene(desired.get("scene"))
        except Exception as exc:
            logger.warning("Scene reconcile failed: {}", exc)
        try:
            self._reconcile_lighting(desired.get("lighting"))
        except Exception as exc:
            logger.warning("Lighting reconcile failed: {}", exc)
        try:
            self._reconcile_alarms(desired.get("alarms"))
        except Exception as exc:
            logger.warning("Alarm reconcile failed: {}", exc)

    def _reconcile_scene(self, scene: Any) -> None:
        scene_key = str((scene or {}).get("scene_key", "") or "").strip()
        led_params = SCENE_LED_MAP.get(scene_key)
        if not led_params:
            return
        self.environment_orchestrator.apply_scene(
            self.led,
            self.profile,
            {
                "key": scene_key,
                "animation": led_params["animation"],
                "color": led_params["color"],
                "brightness": led_params["brightness"],
                "line": f"Scene applied from app: {scene_key}.",
            },
        )

    def _reconcile_lighting(self, lighting: Any) -> None:
        data = lighting if isinstance(lighting, dict) else {}
        if not data:
            return
        # Applied AFTER the scene so an explicit lights-off always wins.
        if not bool(data.get("lights_on", True)):
            self.led.set_user_brightness(0.0)
            return
        level = int(data.get("light_level", 45) or 45)
        self.led.set_user_brightness(max(0.0, min(1.0, level / 100.0)))

    def _reconcile_alarms(self, alarms: Any) -> None:
        rows = alarms if isinstance(alarms, list) else []
        for alarm in self.schedule.list_alarms():
            if str(getattr(alarm, "label", "")).startswith(ALARM_LABEL_PREFIX):
                self.schedule.remove_alarm(alarm.id)
        for row in rows:
            if not isinstance(row, dict) or not bool(row.get("enabled", True)):
                continue
            time_24h = str(row.get("time", "") or "")
            if not is_valid_time_24h(time_24h):
                continue
            days = row.get("days") if isinstance(row.get("days"), list) else []
            # App dialect Mon=1..Sun=7 -> datetime.weekday() Mon=0..Sun=6.
            repeat = ",".join(
                str(int(d) - 1) for d in days if isinstance(d, (int, float)) and 1 <= int(d) <= 7
            )
            label = str(row.get("label", "") or "").strip() or "Alarm"
            self.schedule.add_alarm(
                time_24h, label=f"{ALARM_LABEL_PREFIX} {label}", repeat_days=repeat
            )

    # ── command handlers ──────────────────────────────────────────────────

    def _apply_led(self, animation: str, color: str, brightness: float) -> dict[str, Any]:
        self.led.set_user_animation(animation)
        self.led.set_color_value(color)
        self.led.set_user_brightness(brightness)
        return {"animation": animation, "color": color, "brightness": brightness}

    def _handle_winddown(self, params: dict[str, Any]) -> HandlerResult:
        state = self._apply_led("breathing", "orange", 0.2)
        return True, "Wind-down lighting active.", state

    def _handle_optimize_room(self, params: dict[str, Any]) -> HandlerResult:
        scene_key = str(params.get("scene_key", "") or "") or "balanced_default"
        led_params = SCENE_LED_MAP.get(scene_key, SCENE_LED_MAP["balanced_default"])
        state = self._apply_led(
            led_params["animation"], led_params["color"], led_params["brightness"]
        )
        return True, f"Room optimized with scene {scene_key}.", state

    def _handle_wake_recovery(self, params: dict[str, Any]) -> HandlerResult:
        state = self._apply_led("solid", "orange", 0.1)
        return True, "Gentle night light active for wake recovery.", state

    def _handle_reactive_lights(self, params: dict[str, Any]) -> HandlerResult:
        try:
            from led_controller import apply_music_led_preferences

            apply_music_led_preferences(self.led, self.profile, active=True)
            return True, "Music-reactive lights enabled.", {"reactive": True}
        except Exception:
            state = self._apply_led("pulse", "white", 0.4)
            return True, "Reactive lights enabled (pulse fallback).", state

    def _handle_quiet_hours_override(self, params: dict[str, Any]) -> HandlerResult:
        favorite = str(
            self.profile.get("preferences", {}).get("favorite_color", "") or "white"
        )
        state = self._apply_led("solid", favorite, 0.45)
        return True, "Quiet hours override: user lighting restored.", state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bed_command_poller.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check . && ruff format ai/bed_command_poller.py tests/test_bed_command_poller.py
git add ai/bed_command_poller.py tests/test_bed_command_poller.py
git commit -m "feat(pi): BedCommandPoller — bed executes app commands for real

Daemon-thread short-poll loop: dispatches the 5 catalog macros through a
handler map onto the shared LEDController, reconciles desired state
(lighting, [app]-owned alarms with 1-7->weekday conversion, scenes via
EnvironmentOrchestrator.apply_scene), reports real results, and survives
handler exceptions and network drops.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Wire the poller into `app_entry.py`, ledger, push

**Files:**
- Modify: `app_entry.py` (insert after the ring-router registration block, ~line 537)
- Modify: `.superpowers/sdd/progress.md` (append Plan 6 status)

**Interfaces:**
- Consumes: `BedCommandPoller` (Task 5); `app_entry.main()` locals `backend_client`, `led`, `schedule`, `environment_orchestrator`, `profile` (all built before line 537).

- [ ] **Step 1: Insert the wiring**

In `app_entry.py`, directly after the "Register ring client with the API router" try/except block (ends ~line 537), insert:

```python
    # ── App→bed command bridge: poll the backend for mobile commands ──
    command_poller = None
    try:
        from ai.bed_command_poller import BedCommandPoller

        if backend_client.is_configured():
            command_poller = BedCommandPoller(
                backend_client=backend_client,
                led=led,
                schedule=schedule,
                environment_orchestrator=environment_orchestrator,
                profile=profile,
            )
            command_poller.start()
            logger.info(
                "Bed command poller started (every {}s).",
                command_poller.poll_interval_seconds,
            )
        else:
            logger.info(
                "Bed command poller disabled: set APP_BACKEND_BASE_URL and "
                "BED_DEVICE_ID to receive app commands."
            )
    except Exception as _poller_exc:
        logger.warning("Bed command poller could not start: {}", _poller_exc)
```

NOTE: `profile` is loaded at ~line 443, before this insertion point — verify the block lands AFTER `profile = load_profile()` resolves and AFTER `backend_client` is constructed (line 352). The ring block satisfies both; keep the insertion adjacent to it.

- [ ] **Step 2: Import smoke check**

Run: `python -c "import ast; ast.parse(open('app_entry.py', encoding='utf-8').read()); import ai.bed_command_poller; print('ok')"`
Expected: `ok` (app_entry parses; poller module imports cleanly without hardware).

- [ ] **Step 3: Run the fast check battery**

Run: `python -m pytest tests/test_device_sync_contract.py tests/test_bed_backend_client_sync.py tests/test_bed_command_poller.py tests/test_app_factory_contract.py -v`
Expected: all PASS.

- [ ] **Step 4: Update the progress ledger**

Append to `.superpowers/sdd/progress.md`:

```markdown
=== PLAN 6 (device command bridge) COMPLETE ===
App→bed loop is REAL: /v1/device/auth (+refresh) built (endpoint never existed
— Pi client 404'd since it was written), GET /v1/device/sync short-poll,
POST /v1/device/commands/{id}/result, live-bed gate on the wall-clock
simulator (suppressed while bed synced <15s; unchanged when no bed).
Pi: BedBackendClient.fetch_sync/report_command_result + BedCommandPoller
daemon thread in app_entry (handler map for the 5 catalog macros, desired-
state reconcile: lighting, [app]-owned alarms, scenes). New suites:
test_device_sync_contract, test_bed_backend_client_sync,
test_bed_command_poller. Bed link rows now carry user_id (pair time).
REMAINING for Phase 5: sensor upload Pi→cloud; on-device verify on real Pi
(pi5neo LED backend still unverified on silicon).
```

- [ ] **Step 5: Lint, commit, push, watch CI**

```bash
ruff check . && ruff format app_entry.py
git add app_entry.py .superpowers/sdd/progress.md
git commit -m "feat(pi): start BedCommandPoller in app_entry — the app now drives the bed

Plan 6 complete: app→cloud→bed command loop is real end to end. Poller
shares the voice runtime's LEDController/ScheduleManager (one owner for
the SPI bus) and no-ops gracefully when APP_BACKEND_BASE_URL/BED_DEVICE_ID
are unset.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
gh run watch --exit-status || gh run list --limit 3
```

Expected: push succeeds; CI (Linux/py3.11 arbiter) green. If CI fails on something the local fast checks missed, fix forward before calling the plan done.

---

## Self-Review (done at write time)

- **Spec coverage:** auth (Task 1 — spec deviation noted), sync + desired state + state_version + last_seen (Task 2), result + toggle + lifecycle/re-offer (Tasks 2–3), client methods (Task 4), poller thread + handler map + reconciliation + error handling (Task 5), app_entry wiring + `is_configured` no-op (Task 6), contract + unit tests (Tasks 1–5), auth boundaries both directions (Tasks 1–2).
- **Types:** `fetch_sync() -> (bool, dict, str)` consistent across Tasks 4–5; `report_command_result(command_id, status, detail="", actual_state=None)` consistent; `HandlerResult = (ok, detail, actual_state)`; `device -> {"device_id"}` consistent across routes.
- **Known judgment calls:** `quiet_hours_override` never queues a command row (early-return path) so bridge tests use `winddown`/`optimize_room`; scene reconcile runs before lighting so lights-off wins; alarm ownership via `[app]` label prefix survives poller restarts.
