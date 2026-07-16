# Device Command Bridge — app → cloud → bed (Phase 5, part 1)

**Date:** 2026-07-16
**Status:** Approved
**Problem:** The app's device commands never reach the Pi. `POST /v1/mobile/device-commands`
queues a command in the user's profile, and `_progress_command_state`
(web_server.py) advances its status on a **wall-clock timer** (≥2s → running,
≥5s → completed) — no hardware involved. The Pi's only cloud client
(`ai/bed_backend_client.py`) can device-auth, fetch entitlements, and call AI
chat; it has no way to fetch commands or report results. There is no
device-facing command endpoint on the backend at all (every `device-commands`
route requires the mobile user's JWT).

**Goal:** the app really drives the bed — LED, alarms, scenes — and the bed
reports real results back, with graceful fallback to the existing simulator
when no live bed is paired.

## Scope

**In:** command delivery down to the bed, desired-state reconciliation
(lighting, alarm schedule, scene), real result reporting, real/simulated
toggle, contract + unit tests.

**Out (YAGNI):** WebSockets/push, multi-bed fan-out (single-tenant today), new
DB tables (rides existing profile sections), sensor upload Pi → cloud (Phase 5
part 2).

## Architecture

```
Mobile app ──POST command / upsert controls / set alarm──▶ Cloud backend (Neon)
                                                              │  queues + stores desired state
Pi runtime ──GET /v1/device/sync every ~2.5s (device token)─▶│
   │  ◀── { commands[], desired_state{lighting,alarms,scene}, state_version }
   ├─ executes each command on real hardware (handler map)
   ├─ reconciles desired_state → LED strips + alarm schedule + scene
   └─POST /v1/device/commands/{id}/result──────────────────▶ backend stores REAL result
                                                              │
Mobile app ──GET /v1/mobile/device-commands/{id}────────────▶│  real status, not a timer
```

Three pieces already exist and do not move: the cloud backend
(`api.app_factory` + `web_server.py` + Neon), the Flutter app, and the Pi
voice runtime (`app_entry.py`). This design adds one seam between backend and
Pi.

Transport decision: **short-poll (~2.5s) over HTTPS.** The Pi is behind a home
router and reaches the backend outbound only (Cloudflare tunnel); the backend
runs `workers=1`, so long-poll/WebSockets would tie up the lone worker.
2–3s latency is invisible for lights/alarms/scenes.

## Backend

### Auth: `get_current_device` dependency

Validates the device Bearer token issued by `/v1/device/auth` (built in this
phase — the endpoint did not previously exist; the Pi client called it but got
404) and resolves the paired user by reverse lookup in the `mobile_bed_links`
profile section (the row whose `device_id` matches the token's device). Single-tenant
today; the lookup generalizes later. Mobile-user JWTs are rejected on
device-facing routes and vice versa.

### `GET /v1/device/sync` (device token)

The poll. Side effects: stamps the device's `last_seen`; marks returned
commands `dispatched`. Response:

```json
{
  "server_time": "2026-07-16T18:00:00Z",
  "commands": [
    {"id": "...", "action": "winddown", "params": {}, "created_at": "..."}
  ],
  "desired_state": {
    "lighting": {"lights_on": true, "light_level": 40, "color": "warm",
                  "animation": "breathing"},
    "alarms": [{"alarm_id": "...", "time_24h": "06:30", "days": [1,2,3,4,5],
                 "label": "...", "sound": "...", "vibrate": true,
                 "enabled": true}],
    "scene": {"scene_key": "calm_recovery"}
  },
  "state_version": "<hash of desired_state>"
}
```

`state_version` lets the Pi skip reconciliation when nothing changed.
Desired state is assembled from the existing profile sections:
`web_device_controls` supplies `lights_on`/`light_level` (its only lighting
fields today); `color` and `animation` come from the active scene when one is
set, else the profile's saved preferences, else omitted (Pi keeps current).
Alarms come from the DB `AlarmRepository` (the mobile source of truth since
Plan 1), with the legacy `mobile_alarm_schedules` profile section as fallback;
the saved scene selection supplies `scene`. Device ids are canonicalized
(uppercase, `[A-Za-z0-9._-]` only — same rule as QR pairing) so the JWT sub,
session keys, and bed-link lookups always agree. Unpaired device → empty
commands, null desired_state.

### `POST /v1/device/commands/{id}/result` (device token)

Body: `{"status": "completed" | "failed", "detail": "...",
"actual_state": {...}}`. Backend writes it into the existing
`web_device_commands` row **and** `web_last_command_result`, so the app's
existing status endpoint (`GET /v1/mobile/device-commands/{id}`) returns the
real outcome **with zero app changes**.

No separate heartbeat endpoint — `sync` is the heartbeat.

### Real/simulated toggle

`_progress_command_state` gets one gate: if the paired device's `last_seen`
is within a live window (**~15s**), the wall-clock simulator does **not**
auto-advance — the command stays `dispatched`/`running` until the Pi's real
result lands. Stale or unpaired device → simulator behaves exactly as today.
Existing demos with no bed keep working; a real bed transparently takes over.

Command lifecycle: `queued → dispatched → completed | failed`. The Pi
executes fast LED/scene ops and reports terminal status only; `running` is a
simulator-only state (kept for app compatibility when no bed is live). A
command stuck in `dispatched` past ~30s is re-offered on the next sync
(re-delivery is safe because handlers are idempotent).

## Pi runtime

### `ai/bed_backend_client.py` — two new methods

- `fetch_sync() -> tuple[bool, dict, str]`
- `report_command_result(command_id, status, detail, actual_state) -> tuple[bool, str]`

Both reuse the existing `_authorized_request` plumbing (device auth, 401 →
refresh → retry).

### New `ai/bed_command_poller.py` — `BedCommandPoller`

A daemon **thread inside `app_entry.py`** (approach chosen over a separate
process because two processes cannot share the SPI LED bus, and over folding
into the voice loop because that loop blocks on wake-word/STT for seconds).
Dependencies injected, no globals: `backend_client`, `led`, `schedule`
(ScheduleManager), `environment_orchestrator`, `profile`.

Each ~2.5s tick:

1. `fetch_sync()` — network errors caught, retry next tick, never crash.
2. Dispatch each command through a handler map
   `{action_key -> callable(params) -> (ok, detail, actual_state)}`; each
   handler wrapped in try/except so one bad command can't kill the loop;
   report result after execution.
3. Reconcile `desired_state` (skipped when `state_version` unchanged):
   - `lighting` → `LEDController` (on/off, color, brightness, animation)
   - `alarms` → `ScheduleManager` add/remove, so the existing
     `process_due_alarms()` rings them
   - `scene` → `environment_orchestrator.apply_scene`

### Command handlers (the 5 catalog macros)

| action | hardware effect |
|---|---|
| `winddown` | breathing animation, warm color, dim per light_level |
| `optimize_room` | apply current scene/environment preset |
| `wake_recovery` | gentle low night light |
| `reactive_lights` | music-reactive LED animation on |
| `quiet_hours_override` | restore user lighting despite quiet hours |

Unknown action → reported `failed` with detail "unsupported action".

### `app_entry.py` wiring

Build the poller after `led` / `schedule` / `backend_client` /
`environment_orchestrator` exist; `.start()` as daemon wrapped in try/except —
same pattern as the ring-automation engine startup (app_entry.py:519–537).
Shares the single `LEDController`; no SPI contention. If
`backend_client.is_configured()` is false, log and skip (bed works offline).

## Error handling

- **Pi offline / network drop:** poll fails silently; last-known state stays
  applied; resumes on reconnect. Backend simulator resumes after the live
  window lapses, so the app is never stuck.
- **Device token expired:** existing refresh/re-auth path.
- **Handler throws / unknown action:** result `failed` + detail; loop lives.
- **Unpaired device:** sync returns empty; bed idles.
- **Crash mid-execution:** `dispatched` timeout re-offers the command;
  handlers idempotent (re-setting a light color is safe).

## Testing

- **Backend contract suite** — new `tests/test_device_sync_contract.py`, same
  style as `test_app_factory_contract.py`, driving the production
  `api.app_factory:app`:
  1. device-auth → user creates command → `GET /v1/device/sync` returns it and
     marks it dispatched → `POST result` → mobile status endpoint shows real
     `completed`.
  2. Toggle: no recent sync → timer advances as today; fresh sync → timer
     suppressed until real result.
  3. Auth boundaries: user JWT rejected on device routes; device token
     rejected on mobile routes.
- **Pi unit tests** — new `tests/test_bed_command_poller.py`:
  `BedCommandPoller` with fake client + stub LED/schedule — handler dispatch,
  desired-state reconciliation, `state_version` skip, result reporting, one
  throwing handler doesn't kill the loop. No real hardware needed.

Verification mode per campaign convention: fast checks locally (contract
suite), full suite via GitHub CI (Linux/py3.11 arbiter), push after green.
