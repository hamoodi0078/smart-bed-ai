# Plan 1: Keystone Contract Suite + P0/P1 Fixes (Phases 0–1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the contract test suite against the production app (`api.app_factory:app`) and fix all three P0s (alarms contract, admin auth, profile split-brain) plus the cheap P1s (engine-per-request, revoked tokens, event-loop blockers, multi-worker stopgap).

**Architecture:** Test-first: each fix is preceded by a failing contract test that encodes what the Flutter app / admin panel actually sends. Fixes land in the `api/routers/*` layer and `auth/`/`database/` support modules; `web_server.py` is touched only minimally (one function body) and is NOT deleted or restructured in this plan.

**Tech Stack:** FastAPI + SQLAlchemy 2.x (sync) + Alembic + pytest/unittest + fastapi.testclient. Windows dev machine; CI is Linux.

**Spec:** `docs/superpowers/specs/2026-07-08-readiness-90-design.md`. This is Plan 1 of the 7-phase campaign (see traceability table at the bottom).

## Global Constraints

- Run Python via the repo venv: `venv/Scripts/python.exe` (verified present). Tests: `venv/Scripts/python.exe -m pytest <path> -v`.
- Every task ends with the FULL suite green (`venv/Scripts/python.exe -m pytest`), then a commit. Never commit red.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Do NOT delete `web_server.py`, change its module-level singletons' structure, or remove its routes — that is Phase 3, gated on zero imports + green contract suite (spec constraint 1).
- Do NOT touch the Flutter app in this plan. The backend adopts the app's contract, not vice versa.
- The app's alarm contract (from `mobile_app/lib/src/core/models.dart:1348-1374`): field names `alarm_id`, `time`, `days` (ISO weekday ints 1=Mon…7=Sun), `enabled`, `label`, `sound`, `vibrate`; POST response must contain the full `alarms` list (`api_client.dart:554-567`).
- Existing legacy tests (29 files against `TestClient(web_server.app)`) must stay green — they are not migrated in this plan.
- New contract tests go in ONE file: `tests/test_app_factory_contract.py`, all inheriting `AppFactoryContractCase`.
- Spec deviation (deliberate): the spec's keystone walk also lists device-command and scene steps. Those flows currently pass (audit §2) and their contracts change in Phases 2/5 — their contract tests are added by Plan 2 (scenes, state) and Plan 5 (device commands, honest state machine) alongside the code they must pin down. Everything the three P0s broke is covered here.

---

### Task 1: Contract-test scaffolding + auth walk (Phase 0)

**Files:**
- Create: `tests/test_app_factory_contract.py`

**Interfaces:**
- Produces: `AppFactoryContractCase` (unittest base with `self.client`, `self.register(email=None) -> dict`, `self.bearer(auth) -> dict`, `self._web_server` module handle). All later tasks' tests subclass this.
- Consumes: `tests/env_isolation.py::reset_web_server_db_singletons`, `Storage/subscription_store.py::SubscriptionStore(db_path=...)`.

- [ ] **Step 1: Write the scaffolding and the (passing) auth-walk test**

```python
"""Contract tests against the PRODUCTION app (api.app_factory:app).

These exist because production serves app_factory while the legacy tests
exercise web_server.app — the seam where the 2026-07-08 audit found all
three P0 bugs. Every mobile-facing contract fix lands here first.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
from tests.env_isolation import reset_web_server_db_singletons


class AppFactoryContractCase(unittest.TestCase):
    """TestClient against api.app_factory.app with per-test sqlite isolation.

    Mirrors tests/env_isolation.py::IsolatedWebAuthTestCase, but drives the
    production app instead of web_server.app. web_server is still imported
    and patched because migrated routers lazy-import handlers from it.
    """

    test_password = "Contractpass123"
    test_name = "Contract Tester"

    def setUp(self):
        import web_server

        self._web_server = web_server
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        self._patchers = [
            patch.dict(
                os.environ,
                {"DATABASE_URL": f"sqlite:///{(tmp / 'test.sqlite3').as_posix()}"},
                clear=False,
            ),
            patch.object(
                web_server, "store", SubscriptionStore(db_path=tmp / "subscription_db.json")
            ),
        ]
        for p in self._patchers:
            p.start()
        reset_web_server_db_singletons(web_server)

        from api.app_factory import app

        # Plain TestClient (no context manager): lifespan is intentionally not
        # run, so Sentry/arq/async-DB init never fire in tests.
        self.client = TestClient(app)

    def tearDown(self):
        reset_web_server_db_singletons(self._web_server)
        for p in reversed(self._patchers):
            p.stop()
        self._tmp.cleanup()

    # ── helpers ───────────────────────────────────────────────────────────────

    def register(self, email: str = "contract-tester@example.com") -> dict:
        resp = self.client.post(
            "/v1/mobile/auth/register",
            json={"email": email, "password": self.test_password, "name": self.test_name},
        )
        assert resp.status_code == 200, f"register failed: {resp.text}"
        return resp.json()

    def bearer(self, auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}


class AuthWalkTests(AppFactoryContractCase):
    def test_register_login_me_dashboard(self):
        auth = self.register()
        self.assertTrue(auth["access_token"])
        self.assertTrue(auth["refresh_token"])
        user_id = auth["user"]["user_id"]
        self.assertTrue(user_id)

        resp = self.client.post(
            "/v1/mobile/auth/login",
            json={"email": "contract-tester@example.com", "password": self.test_password},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        headers = self.bearer(resp.json())
        resp = self.client.get("/v1/mobile/auth/me", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["user"]["user_id"], user_id)

        # Dashboard triggers the lazy web_server import — the full production path
        resp = self.client.get("/v1/mobile/dashboard", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it — must PASS (auth is the known-working flow)**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -v`
Expected: `AuthWalkTests::test_register_login_me_dashboard PASSED`. If it fails, STOP — the scaffolding assumptions are wrong; debug before proceeding (check `auth["user"]["user_id"]` shape against `services/auth_service.py::build_auth_response`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_app_factory_contract.py
git commit -m "test: contract suite scaffolding against api.app_factory (Phase 0)"
```

---

### Task 2: Failing alarm-contract test (P0-1, test half)

**Files:**
- Modify: `tests/test_app_factory_contract.py` (append class)

**Interfaces:**
- Consumes: `AppFactoryContractCase` from Task 1.
- Produces: `AlarmContractTests` — the executable definition of the alarm contract. Task 4 makes it pass.

- [ ] **Step 1: Append the failing test class**

```python
class AlarmContractTests(AppFactoryContractCase):
    """The Flutter contract — mirrors AlarmSchedule.toJson()/fromJson() and
    api_client.dart upsertAlarm(), which expects {"alarms": [...]} back."""

    APP_PAYLOAD = {
        "alarm_id": "",
        "time": "06:30",
        "days": [1, 2, 3],  # ISO weekdays: Mon, Tue, Wed
        "enabled": True,
        "label": "Fajr",
        "sound": "default",
        "vibrate": True,
    }

    def test_create_list_edit_toggle_delete_roundtrip(self):
        auth = self.register("alarm-tester@example.com")
        headers = self.bearer(auth)

        # Create — app expects the FULL refreshed list back
        resp = self.client.post("/v1/mobile/alarms", json=self.APP_PAYLOAD, headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("alarms", body, f"POST must return the alarm list, got: {body}")
        self.assertEqual(len(body["alarms"]), 1)
        alarm = body["alarms"][0]
        self.assertTrue(alarm["alarm_id"], "alarm_id must be non-empty")
        self.assertEqual(alarm["days"], [1, 2, 3])
        self.assertEqual(alarm["sound"], "default")
        self.assertTrue(alarm["vibrate"])
        alarm_id = alarm["alarm_id"]

        resp = self.client.get("/v1/mobile/alarms", headers=headers)
        self.assertEqual(resp.json()["alarms"][0]["alarm_id"], alarm_id)

        # Edit via POST upsert (the app always POSTs) — must NOT duplicate
        edited = {**self.APP_PAYLOAD, "alarm_id": alarm_id, "label": "Fajr prayer"}
        resp = self.client.post("/v1/mobile/alarms", json=edited, headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body["alarms"]), 1, "edit must not create a duplicate")
        self.assertEqual(body["alarms"][0]["label"], "Fajr prayer")

        resp = self.client.post(
            f"/v1/mobile/alarms/{alarm_id}/toggle", json={"enabled": False}, headers=headers
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        resp = self.client.delete(f"/v1/mobile/alarms/{alarm_id}", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.get("/v1/mobile/alarms", headers=headers)
        self.assertEqual(resp.json()["alarms"], [])

    def test_unknown_alarm_id_is_404_not_duplicate(self):
        auth = self.register("alarm-tester-2@example.com")
        payload = {**self.APP_PAYLOAD, "alarm_id": "no-such-alarm"}
        resp = self.client.post("/v1/mobile/alarms", json=payload, headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 404, resp.text)
```

- [ ] **Step 2: Run to verify it FAILS for the right reason**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py::AlarmContractTests -v`
Expected: FAIL — `KeyError`/assertion on `"alarms"` (router returns `{"ok": True, "alarm": {...}}`) and `days` mismatch (router ignores the `days` field, expects `days_of_week`).

- [ ] **Step 3: Commit the red test (it documents the bug)**

```bash
git add tests/test_app_factory_contract.py
git commit -m "test: failing alarm contract test capturing P0-1 (app dialect vs router dialect)"
```

---

### Task 3: Alarm model — `sound`/`vibrate` columns + Alembic migration

**Files:**
- Modify: `database/models.py:552-561` (Alarm class)
- Modify: `database/repositories.py:2107-2135` (`create_alarm`), `:2149-2156` (allowed update fields)
- Create: `alembic/versions/<generated>_add_alarm_sound_vibrate.py`

**Interfaces:**
- Produces: `Alarm.sound: str` (default `"default"`), `Alarm.vibrate: bool` (default `True`); `AlarmRepository.create_alarm(..., sound="default", vibrate=True)`; `update_alarm` accepts `sound`/`vibrate` in `**fields`.

- [ ] **Step 1: Add columns to the ORM model**

In `database/models.py`, inside `class Alarm(Base)` after `smart_window_minutes`:

```python
    sound: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    vibrate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

- [ ] **Step 2: Extend the repository**

In `database/repositories.py`, `create_alarm` signature gains `sound: str = "default", vibrate: bool = True` (after `smart_window_minutes`), and the `Alarm(...)` constructor call gains `sound=sound, vibrate=vibrate`. In `update_alarm`, extend the `allowed` set with `"sound", "vibrate"`.

- [ ] **Step 3: Generate + fill the Alembic migration**

Run: `venv/Scripts/python.exe -m alembic heads` — confirm the single head is `084855be2828` (if different, use whatever it prints as `down_revision`).
Run: `venv/Scripts/python.exe -m alembic revision -m "add alarm sound vibrate"`
Fill the generated file's functions:

```python
def upgrade() -> None:
    op.add_column(
        "alarms",
        sa.Column("sound", sa.String(64), nullable=False, server_default="default"),
    )
    op.add_column(
        "alarms",
        sa.Column("vibrate", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("alarms", "vibrate")
    op.drop_column("alarms", "sound")
```

- [ ] **Step 4: Apply to the dev DB and run the full suite**

Run: `venv/Scripts/python.exe -m alembic upgrade head`
Expected: `Running upgrade 084855be2828 -> <newid>` with no error.
Run: `venv/Scripts/python.exe -m pytest`
Expected: same failures as before this task (only the red AlarmContractTests) — no new breakage. Test DBs get the columns automatically via `create_tables()`/`Base.metadata`.

- [ ] **Step 5: Commit**

```bash
git add database/models.py database/repositories.py alembic/versions/
git commit -m "feat(db): alarm sound + vibrate columns (app contract fields)"
```

---

### Task 4: Rewrite the alarms router to the app contract (P0-1, fix half)

**Files:**
- Modify: `api/routers/alarms.py` (full rewrite, below)

**Interfaces:**
- Consumes: `AlarmRepository` with `sound`/`vibrate` (Task 3).
- Produces: routes speaking the app dialect. `PUT /v1/mobile/alarms/{id}` is REMOVED (no caller: the app always POSTs; audit found no other client). Toggle/DELETE keep their paths and reply shapes.

- [ ] **Step 1: Replace the file content**

```python
"""Alarm routes — DB-backed, speaking the Flutter app's contract.

Contract (mobile_app/lib/src/core/models.dart AlarmSchedule):
  fields: alarm_id, time, days (ISO 1=Mon…7=Sun), enabled, label, sound,
  vibrate; POST is an upsert and returns the full refreshed alarm list
  (api_client.dart upsertAlarm reads json["alarms"]).

Routes:
  GET    /v1/mobile/alarms
  POST   /v1/mobile/alarms                     (upsert)
  POST   /v1/mobile/alarms/{alarm_id}/toggle
  DELETE /v1/mobile/alarms/{alarm_id}
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth.middleware import get_current_user

router = APIRouter(prefix="/v1/mobile/alarms", tags=["alarms"])

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class AlarmUpsertRequest(BaseModel):
    alarm_id: str = Field(default="", max_length=36)
    time: str = Field(default="07:00", max_length=5)
    label: str = Field(default="", max_length=100)
    enabled: bool = True
    days: list[int] = Field(default_factory=list)  # ISO weekdays 1=Mon … 7=Sun
    sound: str = Field(default="default", max_length=64)
    vibrate: bool = True

    @field_validator("time")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("time must be HH:MM")
        h, m = int(v[:2]), int(v[3:])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("time is out of range")
        return v

    @field_validator("days")
    @classmethod
    def _validate_days(cls, v: list[int]) -> list[int]:
        if any(d not in range(1, 8) for d in v):
            raise ValueError("days values must be 1–7 (ISO weekday, Monday=1)")
        return sorted(set(v))


class AlarmToggleRequest(BaseModel):
    enabled: bool


def _next_trigger_at_utc(time_str: str, days: list[int]) -> str:
    """Next UTC instant matching HH:MM on one of the ISO weekdays (any day if empty)."""
    from time_utils import to_iso

    now = datetime.now(timezone.utc)
    hour, minute = int(time_str[:2]), int(time_str[3:])
    for offset in range(0, 8):
        candidate = (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= now:
            continue
        if not days or candidate.isoweekday() in days:
            return to_iso(candidate)
    return ""


def _alarm_to_dict(alarm: Any) -> dict[str, Any]:
    from time_utils import to_iso, ensure_utc

    days = sorted(d + 1 for d in (alarm.days_of_week or []))  # DB 0–6 → ISO 1–7
    return {
        "alarm_id": alarm.id,
        "time": alarm.time,
        "label": alarm.label,
        "enabled": alarm.enabled,
        "days": days,
        "sound": alarm.sound,
        "vibrate": alarm.vibrate,
        "created_at": to_iso(ensure_utc(alarm.created_at)) if alarm.created_at else "",
        "updated_at": to_iso(ensure_utc(alarm.updated_at)) if alarm.updated_at else "",
        "next_trigger_at_utc": _next_trigger_at_utc(alarm.time, days) if alarm.enabled else "",
    }


def _alarm_list(repo: Any, user_id: str) -> dict[str, Any]:
    return {"ok": True, "alarms": [_alarm_to_dict(a) for a in repo.list_alarms(user_id)]}


@router.get("")
def list_alarms(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from database import AlarmRepository

    return _alarm_list(AlarmRepository(), current_user["sub"])


@router.post("")
def upsert_alarm(
    payload: AlarmUpsertRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from database import AlarmRepository

    user_id: str = current_user["sub"]
    repo = AlarmRepository()
    days_db = [d - 1 for d in payload.days]  # ISO 1–7 → DB 0–6
    if payload.alarm_id:
        alarm = repo.update_alarm(
            alarm_id=payload.alarm_id,
            user_id=user_id,
            time=payload.time,
            label=payload.label,
            enabled=payload.enabled,
            days_of_week=days_db,
            sound=payload.sound,
            vibrate=payload.vibrate,
        )
        if alarm is None:
            raise HTTPException(status_code=404, detail="Alarm not found")
    else:
        try:
            repo.create_alarm(
                user_id=user_id,
                time=payload.time,
                label=payload.label,
                enabled=payload.enabled,
                days_of_week=days_db,
                sound=payload.sound,
                vibrate=payload.vibrate,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _alarm_list(repo, user_id)


@router.post("/{alarm_id}/toggle")
def toggle_alarm(
    alarm_id: str, payload: AlarmToggleRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    from database import AlarmRepository

    alarm = AlarmRepository().update_alarm(
        alarm_id=alarm_id, user_id=current_user["sub"], enabled=payload.enabled
    )
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return {"ok": True, "alarm_id": alarm_id, "enabled": payload.enabled}


@router.delete("/{alarm_id}")
def delete_alarm(alarm_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    from database import AlarmRepository

    deleted = AlarmRepository().delete_alarm(alarm_id=alarm_id, user_id=current_user["sub"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return {"ok": True, "deleted_alarm_id": alarm_id}
```

- [ ] **Step 2: Run the contract test — now green**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -v`
Expected: ALL PASS, including both `AlarmContractTests`.

- [ ] **Step 3: Full suite + commit**

Run: `venv/Scripts/python.exe -m pytest`
Expected: green (legacy alarm tests target web_server's JSON handlers, untouched).

```bash
git add api/routers/alarms.py
git commit -m "fix(alarms): adopt the app contract — alarm_id/days 1-7/sound/vibrate, POST upsert returns list (P0-1)"
```

---

### Task 5: Admin cookie guard + dedupe admin auth routes (P0-2)

**Files:**
- Modify: `tests/test_app_factory_contract.py` (append class)
- Modify: `api/routers/admin.py:38-73` (guard + remove duplicate login/me)
- Modify: `api/app_factory.py` (remove `admin_public_router` import/include, ~lines 297/316)

**Interfaces:**
- Consumes: `web_server._cookie_admin(request)` (validates `sb_admin_token` against `store`), `auth.jwt_handler.decode_access_token`.
- Produces: `require_admin_session(request) -> dict` in `api/routers/admin.py` — cookie-first, JWT-role fallback. The ONLY admin login/me implementation left registered is `api/routers/auth.py:181/303` (cookie-based; it registers first today and is the live one).

- [ ] **Step 1: Append the failing test**

```python
class AdminContractTests(AppFactoryContractCase):
    """The web panel authenticates with the sb_admin_token cookie
    (web/assets/app.js sends credentials:"include", never a Bearer header)."""

    def test_cookie_login_then_protected_endpoints(self):
        auth = self.register("admin-tester@example.com")
        user_id = auth["user"]["user_id"]
        # Admin role records live in the subscription store today
        self._web_server.store.upsert_admin_user(
            user_id, "admin-tester@example.com", role="admin"
        )
        resp = self.client.post(
            "/v1/admin/auth/login",
            json={"email": "admin-tester@example.com", "password": self.test_password},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["admin"]["role"], "admin")

        # The cookie session must now open protected admin routes (P0-2:
        # today these 401 because the router demands a Bearer role JWT)
        resp = self.client.get("/v1/admin/overview")
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.get("/v1/admin/auth/me")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_anonymous_admin_calls_are_rejected(self):
        resp = self.client.get("/v1/admin/overview")
        self.assertEqual(resp.status_code, 401, resp.text)
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py::AdminContractTests -v`
Expected: `test_cookie_login_then_protected_endpoints` FAILS at `/v1/admin/overview` with 401 (login itself succeeds — auth.py's cookie login registers first and works). `test_anonymous...` passes already.

- [ ] **Step 3: Fix `api/routers/admin.py`**

Replace lines 38-73 (imports, routers, and the duplicate auth endpoints) with:

```python
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request


def require_admin_session(request: Request) -> dict[str, Any]:
    """Admin guard: cookie session (web panel) first, Bearer JWT role fallback.

    The panel sends the sb_admin_token cookie (credentials:"include"); JWTs
    carrying a role claim are accepted for non-browser API clients.
    """
    from web_server import _cookie_admin

    admin = _cookie_admin(request)
    if admin:
        return admin

    auth_header = str(request.headers.get("authorization", "") or "")
    if auth_header.lower().startswith("bearer "):
        from auth.jwt_handler import JWTError, decode_access_token

        try:
            claims = decode_access_token(auth_header[7:].strip())
        except JWTError:
            claims = {}
        if claims.get("type") == "access" and claims.get("role") in ("admin", "owner"):
            return {"user_id": str(claims.get("sub", "")), "role": str(claims.get("role"))}

    raise HTTPException(status_code=401, detail="Admin auth required")


# Every endpoint requires an authenticated admin session
router = APIRouter(
    prefix="/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_session)],
)
```

Delete from this file: `public_router` and its `admin_login` endpoint (dead duplicate — `auth.py:181` registers first and is cookie-correct), the `admin_me` endpoint (same — `auth.py:303`), and the now-unused `Response`/`require_role` imports. Update the module docstring route list accordingly.

- [ ] **Step 4: Fix `api/app_factory.py`**

Remove the `admin_public_router` import and its `include_router` call (line ~316). Keep `application.include_router(admin_router)`.

- [ ] **Step 5: Run tests, full suite, commit**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -v` → all green.
Run: `venv/Scripts/python.exe -m pytest` → green.

```bash
git add api/routers/admin.py api/app_factory.py tests/test_app_factory_contract.py
git commit -m "fix(admin): cookie-session guard on admin router; drop dead duplicate login/me (P0-2)"
```

---

### Task 6: Shared DatabaseConnection singleton (P1-5)

**Files:**
- Modify: `database/connection.py` (append), `database/__init__.py` (export), `database/repositories.py` (10 sites), `api/routers/profile.py:24`, `api/routers/health.py:35,70`, `tests/env_isolation.py`
- Test: `tests/test_app_factory_contract.py` (append class)

**Interfaces:**
- Produces: `database.connection.get_shared_connection() -> DatabaseConnection`, `database.connection.reset_shared_connection() -> None` (also exported from `database`). All repositories default to the shared connection. Task 7 depends on this (per-request revocation checks must not build engines).

- [ ] **Step 1: Append the failing test**

```python
class SharedConnectionTests(AppFactoryContractCase):
    def test_repositories_share_one_engine(self):
        from database import AlarmRepository
        from database.connection import get_shared_connection

        a, b = AlarmRepository(), AlarmRepository()
        self.assertIs(a.db.engine, b.db.engine)
        self.assertIs(a.db.engine, get_shared_connection().engine)
```

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py::SharedConnectionTests -v`
Expected: FAIL — `ImportError: cannot import name 'get_shared_connection'`.

- [ ] **Step 2: Add the singleton to `database/connection.py`** (append at end of file)

```python
_SHARED_CONNECTION: DatabaseConnection | None = None


def get_shared_connection() -> DatabaseConnection:
    """Process-wide DatabaseConnection.

    Repositories default to this instead of building a fresh engine + pool +
    SELECT-1 probe per instantiation (the audit's engine-per-request leak).
    Tests that repoint DATABASE_URL must call reset_shared_connection().
    """
    global _SHARED_CONNECTION
    if _SHARED_CONNECTION is None:
        _SHARED_CONNECTION = DatabaseConnection()
    return _SHARED_CONNECTION


def reset_shared_connection() -> None:
    global _SHARED_CONNECTION
    if _SHARED_CONNECTION is not None:
        try:
            _SHARED_CONNECTION.engine.dispose()
        except Exception:
            pass
    _SHARED_CONNECTION = None
```

Export both names from `database/__init__.py` (add to the existing import-from-connection line and `__all__` if present).

- [ ] **Step 3: Point everything at it**

- `database/repositories.py`: replace ALL 10 occurrences of `self.db = db or DatabaseConnection()` with `self.db = db or get_shared_connection()`; add `get_shared_connection` to the module's `from .connection import ...` line.
- `api/routers/profile.py:24`: replace the import-time global `_profile_repo = ProfileRepository()` with a function, and update all `_profile_repo.` call sites to `_profile_repo().`:

```python
def _profile_repo() -> ProfileRepository:
    # Per-request construction is cheap now that the connection is shared;
    # an import-time global would pin whatever DATABASE_URL was set first.
    return ProfileRepository()
```

- `api/routers/health.py`: in `readyz` and `healthz_detailed`, replace `from database.connection import DatabaseConnection` + `db_conn = DatabaseConnection()` with `from database.connection import get_shared_connection` + `db_conn = get_shared_connection()`.
- `tests/env_isolation.py`: at the end of `reset_web_server_db_singletons`, add:

```python
    from database.connection import reset_shared_connection

    reset_shared_connection()
```

- [ ] **Step 4: Run tests, full suite, commit**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -v` → green.
Run: `venv/Scripts/python.exe -m pytest` → green (watch specifically for Windows sqlite file-lock errors in teardown — if any appear, a singleton reset is missing in that test's isolation path).

```bash
git add database/connection.py database/__init__.py database/repositories.py api/routers/profile.py api/routers/health.py tests/env_isolation.py tests/test_app_factory_contract.py
git commit -m "fix(db): process-wide shared engine; kill engine-per-request in repos/profile/health (P1-5)"
```

---

### Task 7: Revoked access tokens must die immediately (P1-6)

**Files:**
- Modify: `auth/middleware.py:40-63` (`get_current_user`)
- Test: `tests/test_app_factory_contract.py` (append class)

**Interfaces:**
- Consumes: `MobileAuthRepository.validate_access_token(token) -> dict` (returns `{}` for revoked/expired/unknown; JWT fast-path checks the JTI revocation row), shared connection from Task 6.

- [ ] **Step 1: Append the failing test**

```python
class TokenRevocationTests(AppFactoryContractCase):
    def test_logout_revokes_access_token_on_migrated_routes(self):
        auth = self.register("revoke-tester@example.com")
        headers = self.bearer(auth)
        self.assertEqual(self.client.get("/v1/mobile/auth/me", headers=headers).status_code, 200)

        resp = self.client.post(
            "/v1/mobile/auth/logout",
            json={"refresh_token": auth["refresh_token"]},
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        # The old access token must now be rejected on every migrated route
        self.assertEqual(self.client.get("/v1/mobile/auth/me", headers=headers).status_code, 401)
        self.assertEqual(self.client.get("/v1/mobile/alarms", headers=headers).status_code, 401)
```

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py::TokenRevocationTests -v`
Expected: FAIL — the post-logout requests return 200 (get_current_user only checks signature/expiry).

- [ ] **Step 2: Add the DB revocation check to `get_current_user`**

In `auth/middleware.py`, inside the `try:` block, immediately after the `user_id`/`sub` check (after line ~60) and before `return payload`:

```python
        # DB revocation check: logout sets revoked=True on the session row;
        # signature-only validation would honor the token for up to 60 more
        # minutes (audit P1-6). validate_access_token maps JWT → JTI row.
        from database import MobileAuthRepository

        if not MobileAuthRepository().validate_access_token(token):
            logger.info("Revoked or unknown access token presented")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
```

(One indexed query per authenticated request — accepted in the spec; the shared connection from Task 6 makes it pool-reusing.)

- [ ] **Step 3: Run tests, full suite, commit**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -v` → green.
Run: `venv/Scripts/python.exe -m pytest` → green. If legacy tests fail with 401s here, they are minting JWTs without DB session rows — fix the test setup to register through the API rather than weakening this check.

```bash
git add auth/middleware.py tests/test_app_factory_contract.py
git commit -m "fix(auth): get_current_user enforces DB revocation — logout kills access tokens (P1-6)"
```

---

### Task 8: Profile read-through — DB is the source of truth (P0-3)

**Files:**
- Modify: `database/repositories.py` (ProfileRepository, append method)
- Modify: `api/routers/islamic.py` (resolver + premium gate)
- Modify: `web_server.py:2261-2277` (`_chat_profile_prefs_for_user`)
- Test: `tests/test_app_factory_contract.py` (append class)

**Interfaces:**
- Produces: `ProfileRepository.get_profile_prefs_if_exists(user_id) -> dict | None`; `api.routers.islamic._prayer_location(user, profile) -> dict` with keys `mode, latitude, longitude, city, country, method`.

- [ ] **Step 1: Append the failing tests**

```python
class ProfileReadThroughTests(AppFactoryContractCase):
    """P0-3: what the app saves via POST /v1/mobile/profile must drive
    prayer times, dashboard identity, and chat context — not the legacy
    JSON that nothing writes anymore."""

    PROFILE = {
        "display_name": "Danah",
        "location_mode": "auto",
        "latitude": 29.3759,
        "longitude": 47.9774,
        "city": "Kuwait City",
        "country_code": "KW",
    }

    def _save_profile(self, email: str) -> dict:
        auth = self.register(email)
        resp = self.client.post("/v1/mobile/profile", json=self.PROFILE, headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 200, resp.text)
        return auth

    def test_saved_profile_drives_prayer_location(self):
        auth = self._save_profile("profile-tester@example.com")
        from api.routers.islamic import _prayer_location

        loc = _prayer_location({"user_id": auth["user"]["user_id"]}, profile={})
        self.assertEqual(loc["latitude"], 29.3759)
        self.assertEqual(loc["longitude"], 47.9774)
        self.assertEqual(loc["mode"], "auto")

    def test_chat_prefs_read_db_first(self):
        auth = self._save_profile("profile-tester-2@example.com")
        prefs = self._web_server._chat_profile_prefs_for_user(
            {}, {"user_id": auth["user"]["user_id"]}
        )
        self.assertEqual(prefs["display_name"], "Danah")

    def test_islamic_overview_not_premium_gated(self):
        auth = self.register("free-tester@example.com")
        with patch.object(
            self._web_server, "_mobile_islamic_overview_payload", return_value={"islamic": {}}
        ):
            resp = self.client.get("/v1/mobile/islamic/overview", headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 200, resp.text)
```

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py::ProfileReadThroughTests -v`
Expected: FAIL — `_prayer_location` doesn't exist; chat prefs return `""`; overview returns 403.

- [ ] **Step 2: Add `get_profile_prefs_if_exists` to ProfileRepository** (after `get_profile_prefs`)

```python
    def get_profile_prefs_if_exists(self, user_id: str) -> dict[str, Any] | None:
        """Like get_profile_prefs, but None when the user has no saved row —
        callers use this to fall back to legacy JSON prefs."""
        uid = _clean_user_id(user_id)
        if not uid:
            return None
        with self.db.get_session() as session:
            row = session.execute(
                select(UserProfilePrefs).where(UserProfilePrefs.user_id == uid).limit(1)
            ).scalar_one_or_none()
            return None if row is None else self._prefs_to_dict(row)
```

- [ ] **Step 3: Rework `api/routers/islamic.py`**

Replace `_resolve_prayer_service` with a testable location resolver + thin service builder, and drop the premium gate (spec P2: prayer times are free-tier — a demo account must not 403):

```python
def _prayer_location(user: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Resolve prayer location: DB profile (what POST /v1/mobile/profile
    writes) first; legacy voice-profile JSON section as pre-migration fallback."""
    from config.settings import settings

    user_id = str(user.get("user_id", "") or "").strip()
    db_prefs: dict[str, Any] | None = None
    if user_id:
        try:
            from database import ProfileRepository

            db_prefs = ProfileRepository().get_profile_prefs_if_exists(user_id)
        except Exception:
            db_prefs = None

    legacy = (profile.get("users") or {}).get(user_id, {}) or {}
    legacy_loc = legacy.get("location") or {}
    method = int(legacy.get("prayer_method") or settings.islamic_prayer_method or 8)

    if db_prefs:
        return {
            "mode": str(db_prefs.get("location_mode", "auto") or "auto").lower(),
            "latitude": db_prefs.get("latitude"),
            "longitude": db_prefs.get("longitude"),
            "city": str(db_prefs.get("city") or settings.islamic_prayer_city or "Kuwait City"),
            "country": str(
                db_prefs.get("country_code") or settings.islamic_prayer_country or "Kuwait"
            ),
            "method": method,
        }
    return {
        "mode": str(legacy_loc.get("mode", "auto") or "auto").lower(),
        "latitude": legacy_loc.get("latitude"),
        "longitude": legacy_loc.get("longitude"),
        "city": str(legacy_loc.get("city") or settings.islamic_prayer_city or "Kuwait City"),
        "country": str(legacy_loc.get("country") or settings.islamic_prayer_country or "Kuwait"),
        "method": method,
    }


def _resolve_prayer_service(user: dict[str, Any], profile: dict[str, Any]):
    from islamic_mode.prayer_times import PrayerTimesService

    loc = _prayer_location(user, profile)
    if loc["mode"] == "auto" and loc["latitude"] is not None and loc["longitude"] is not None:
        return PrayerTimesService(
            method=loc["method"], latitude=float(loc["latitude"]), longitude=float(loc["longitude"])
        )
    return PrayerTimesService(city=loc["city"], country=loc["country"], method=loc["method"])
```

In all three handlers (`overview`, `prayer-times`, `next-prayer`): change the lazy import `_require_premium_plan` → `_require_user` and the call accordingly. Update the module docstring.

- [ ] **Step 4: Make `web_server._chat_profile_prefs_for_user` read the DB first**

Replace the function body (web_server.py:2261-2277) with:

```python
def _chat_profile_prefs_for_user(profile: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    defaults = _normalize_user_profile_prefs(
        {
            "display_name": "",
            "timezone": "Asia/Kuwait",
            "push_enabled": True,
            "email_enabled": False,
            "location_mode": "auto",
            "country_code": "KW",
            "city": "",
            "theme_mode": "system",
        }
    )
    # DB is the source of truth (POST /v1/mobile/profile writes there); the
    # legacy JSON section only serves pre-migration data (audit P0-3).
    user_id = str(user.get("user_id", "") or "").strip()
    if user_id:
        try:
            from database import ProfileRepository

            db_prefs = ProfileRepository().get_profile_prefs_if_exists(user_id)
        except Exception as exc:
            _event("warning", "profile_db_read_failed", error=str(exc))
            db_prefs = None
        if db_prefs:
            return _normalize_user_profile_prefs({**defaults, **db_prefs})
    key = _user_profile_key(user)
    section = _get_scoped_profile_section(profile, "web_profile_prefs")
    scoped = section.get(key, {}) if key and isinstance(section.get(key, {}), dict) else {}
    return _normalize_user_profile_prefs({**defaults, **scoped})
```

- [ ] **Step 5: Run tests, full suite, commit**

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py -v` → green.
Run: `venv/Scripts/python.exe -m pytest` → green. (Legacy web tests that exercise `_chat_profile_prefs_for_user` with JSON-only users still pass via the fallback branch; if one fails, check whether it asserts the JSON value while a DB row exists for that user id.)

```bash
git add database/repositories.py api/routers/islamic.py web_server.py tests/test_app_factory_contract.py
git commit -m "fix(profile): DB read-through for prayer location + chat prefs; islamic routes free-tier (P0-3)"
```

---

### Task 9: Stop blocking the event loop in async wrappers (P1-7)

**Files:**
- Modify: `api/routers/chat.py:42-50`, `api/routers/actions.py:21-27,48-54`, `api/routers/mobile_features.py:41-49,76-84,90-98,116-124`, `api/routers/scenes.py:37-61`

**Interfaces:**
- No interface changes — same routes, same responses. Sync handler calls move off the event loop via `asyncio.to_thread`.

- [ ] **Step 1: Apply the same mechanical change at every listed site**

Add `import asyncio` to each file's imports. Then, in each `async def` wrapper that ends with a direct call to a sync `_ws` function, change the return line. Example (chat.py `v1_command`):

```python
    return await asyncio.to_thread(_ws, payload=payload, request=request)
```

Exact sites (each currently `return _ws(...)` inside an `async def`):

| File | Handler |
|---|---|
| chat.py | `v1_command` |
| actions.py | `undo_last_action`, `mobile_undo_last_action` |
| mobile_features.py | `register_push_token`, `first_3_nights_complete`, `nightly_summary_feedback`, `mobile_user_actions` |
| scenes.py | `compose_scene`, `mobile_scene_preview`, `mobile_scene_save_tonight` |

Do NOT touch: `ai_chat`/`ai_chat_stream` (they await an async `_ws`), the sync `def` handlers (FastAPI already runs them in the threadpool), or websockets.

- [ ] **Step 2: Verify no stragglers**

Run: `grep -n "return _ws(" api/routers/*.py`
Expected: every remaining hit is inside a plain `def` handler (check each hit's enclosing function signature).

- [ ] **Step 3: Full suite + commit**

Run: `venv/Scripts/python.exe -m pytest`
Expected: green — behavior is identical, only the executing thread changes.

```bash
git add api/routers/chat.py api/routers/actions.py api/routers/mobile_features.py api/routers/scenes.py
git commit -m "fix(perf): move sync web_server handlers off the event loop via asyncio.to_thread (P1-7)"
```

---

### Task 10: Multi-worker stopgap — workers=1 until Phase 2 (P1-4 mitigation)

**Files:**
- Modify: `docker-compose.yml:30`, `nixpacks.toml:8`

- [ ] **Step 1: docker-compose.yml** — change line 30:

```yaml
      # TEMP (audit P1-4): JSON stores are per-process; sessions/billing corrupt
      # under >1 worker. Restore "4" after Phase 2 moves state to the DB.
      GUNICORN_WORKERS: "1"
```

- [ ] **Step 2: nixpacks.toml** — change `--workers 2` to `--workers 1` on line 8 and add above it:

```toml
# TEMP (audit P1-4): single worker until Phase 2 moves sessions to the DB
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml nixpacks.toml
git commit -m "fix(deploy): single gunicorn worker until sessions move to the DB (P1-4 stopgap)"
```

---

### Task 11: JWT role claim plumbing

**Files:**
- Modify: `auth/jwt_handler.py:53-75` (`create_access_token`)
- Test: `tests/test_app_factory_contract.py` (append class)

**Interfaces:**
- Produces: `create_access_token(..., role: str = "")` — emits a `role` claim when non-empty. Consumed today by `require_admin_session`'s JWT fallback (Task 5) and `require_role` (`auth/middleware.py:117` already reads `payload.get("role")`). Issuance of admin-role JWTs at login is deliberately deferred to Phase 2 (admin sessions move to the DB there; wiring role sources twice would be throwaway).

- [ ] **Step 1: Append the failing test**

```python
class JwtRoleClaimTests(unittest.TestCase):
    def test_role_claim_roundtrip(self):
        from datetime import datetime, timedelta, timezone

        from auth.jwt_handler import create_access_token, decode_access_token

        exp = datetime.now(timezone.utc) + timedelta(minutes=5)
        token = create_access_token(user_id="u1", jti="j1", exp=exp, role="admin")
        self.assertEqual(decode_access_token(token)["role"], "admin")

        token = create_access_token(user_id="u1", jti="j2", exp=exp)
        self.assertNotIn("role", decode_access_token(token))
```

Run: `venv/Scripts/python.exe -m pytest tests/test_app_factory_contract.py::JwtRoleClaimTests -v`
Expected: FAIL — `TypeError: create_access_token() got an unexpected keyword argument 'role'`.

- [ ] **Step 2: Add the parameter**

In `create_access_token`, add `role: str = ""` after `client_name`, and after the `client_name` claim block add:

```python
    if role:
        claims["role"] = role
```

- [ ] **Step 3: Run tests, full suite, commit**

```bash
git add auth/jwt_handler.py tests/test_app_factory_contract.py
git commit -m "feat(auth): optional role claim in access tokens (admin API clients)"
```

---

### Task 12: Final verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `venv/Scripts/python.exe -m pytest`
Expected: everything green, including all 6 contract-test classes.

- [ ] **Step 2: Lint**

Run: `venv/Scripts/python.exe -m ruff check .`
Expected: clean. Fix anything it flags in files this plan touched.

- [ ] **Step 3: Boot smoke — the production app imports and serves**

Run: `venv/Scripts/python.exe -c "from fastapi.testclient import TestClient; from api.app_factory import app; c = TestClient(app); r = c.get('/healthz'); print(r.status_code, r.json())"`
Expected: `200 {'ok': True, 'service': 'web_runtime'}`

- [ ] **Step 4: Update the plan checkboxes, commit, push**

```bash
git add docs/superpowers/plans/2026-07-08-plan1-phase0-1-p0-fixes.md
git commit -m "docs: Plan 1 (Phases 0-1) executed — all P0s + cheap P1s closed"
git push
```

---

## Campaign traceability: every audit.md finding → phase/plan

Phases per the spec. **Plan 1 = this document.** Plans 2–6 are written just-in-time when their phase starts.

| audit.md finding | Phase | Plan |
|---|---|---|
| P0-1 alarms contract broken end-to-end | 1 | **Plan 1 Tasks 2-4** |
| P0-2 admin panel 100% dead | 1 | **Plan 1 Task 5** |
| P0-3 profile split-brain / prayer location | 1 | **Plan 1 Task 8** |
| P1-4 multi-worker session/billing corruption | 1 (stopgap) + 2 (real fix) | **Plan 1 Task 10**, Plan 2 |
| P1-5 engine-per-request (alarms/OTP/readyz) | 1 | **Plan 1 Task 6** |
| P1-6 revoked-token acceptance | 1 | **Plan 1 Task 7** |
| P1-7 event-loop-blocking async wrappers | 1 | **Plan 1 Task 9** |
| P2: premium gate 403 on Islamic tab | 1 | **Plan 1 Task 8 step 3** |
| §6 CI smoke too narrow / zero app_factory tests | 0 + 6 | **Plan 1 Tasks 1,2,5,7,8**, Plan 6 |
| §7 duplicate admin auth routes registered twice | 1 | **Plan 1 Task 5** |
| P2: GETs with write side effects (dashboard/timeline) | 2 | Plan 2 |
| §4 SubscriptionStore JSON per-process (sessions/checkout/idempotency) | 2 | Plan 2 |
| §4 profile JSON read-modify-write races; SPOF quarantine reset | 2 | Plan 2 |
| §4 UndoManager/_CHAT_ENGINES/rate-limit per-process | 2 | Plan 2 |
| §6 migrations swallowed by entrypoint; create_tables() paper-over | 2 | Plan 2 |
| §3 two alarm systems / two profile stores / two session systems | 2-3 | Plans 2-3 |
| §2 lazy-import cost; second FastAPI app; duplicate Sentry init | 3 | Plan 3 |
| §3 god-module web_server.py; services extraction; delete (gated) | 3 | Plan 3 |
| §3 dead code: master_api, master_controller, fix_db_schema, sanity_checks, pack_code, manual_email_test, test_whatsapp, print_sendgrid_env, main.py shim, celery | 3 | Plan 3 |
| §3 two retry frameworks / two service registries / two task queues | 3 | Plan 3 |
| §3/§5 exception swallowing (main.save_profile, ApiService.saveToken, service_registry boot-with-dead-DB) | 3 (backend) + 4 (Flutter) | Plans 3-4 |
| §5 wrapper ValidationError→500 + ValueError echo | 3 | Plan 3 |
| P2 fake SSE streaming | 3 | Plan 3 |
| §6 validate_production_secrets never blocks | 3 | Plan 3 |
| §1 two Flutter UI trees / two API clients / dup stores+widgets | 4 | Plan 4 |
| §1 decorative screens (health, achievements, journal, winddown, sounds, partner) | 4 | Plan 4 |
| §1 dead localization (l10n unregistered) | 4 | Plan 4 |
| §2 LED/device commands fake; no bed-side consumer | 5 | Plan 5 |
| §2 alarm trigger not wired (mobile alarms never ring) | 5 | Plan 5 |
| §1 sensors hardcoded stub | 5 | Plan 5 |
| §6 voice container pointless in cloud | 5 + 7 | Plans 5, 7 |
| §4 /healthz proves nothing (probes point at it) | 7 | Plan 7 (probe → /readyz) |
| §2 WhatsApp needs env + worker in prod | 7 | Plan 7 |
| §8 re-audit ≥90% | 6 | Plan 6 |
