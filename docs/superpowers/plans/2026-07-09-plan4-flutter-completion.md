# Plan 4: Flutter Completion — Wire the Decorative Screens (Phase 4)

Lean plan (user-approved mode: inline execution by controller, fast checks only —
`flutter analyze` + contract suite per task; full suite via GitHub CI per push).

**Goal:** The six decorative screens (achievements, health dashboard, journal,
winddown, sounds, partner) fetch and persist real data through `SmartBedApi`
against `/v1/automation/*`; localization actually registered.

**Spec:** `docs/superpowers/specs/2026-07-08-readiness-90-design.md` §4.4.

## Key discovery (changes the audit's assumption)

The 91 `/v1/automation/*` routes are broken as shipped: `_get_profile()` reads
`request.state.user_profile`, which **no middleware ever sets** → profile-using
routes 401 for every caller. Engines are bed-level (service_registry sets
`app.state.user_profile` from the voice JSON profile), not per-user.

**Architecture decision:** authenticate the automation router with the standard
Bearer `get_current_user` dependency, and make `_get_profile()` fall back to the
bed-level `app.state.user_profile`. Authenticated + working now; true per-user
engine state is deferred to the Phase 2/3 state unification (one bed = one
household today). Recorded as tech debt in the traceability table.

## Tasks

- [ ] **A. Backend unlock:** `api/automation_routes.py` — router gains
  `dependencies=[Depends(get_current_user)]`; `_get_profile` falls back to
  `request.app.state.user_profile`. Contract tests: unauthenticated
  `/v1/automation/achievements` → 401; authenticated → 200 (lifespan-less test
  seeds `app.state.services`/`user_profile` fakes).
- [ ] **B. `SmartBedApi` automation methods** (`mobile_app/lib/src/core/api_client.dart`):
  `getAchievements`, `getAchievementStats`, `recordDream`, `getDreamPrompt`,
  `getDreamPatterns`, `getStress`, `logHydration`, `getHydrationToday`,
  `getWeeklyHealthReport`, `getSleepDebt`, `getPartnerStatus`,
  `getPartnerComparison`, `recordPartnerSleep`, `createPartnerChallenge`,
  `getCircadianScene`, `getWakeSequence`. Models in `models.dart` as needed.
- [ ] **C. Achievements screen** → `/v1/automation/achievements` + `/stats`
  (canned list becomes fallback for offline).
- [ ] **D. Health dashboard** → stress, hydration (log + today), weekly report,
  sleep debt.
- [ ] **E. Journal screen** → `/dreams/record|prompt|patterns`; Hive stays as
  offline cache, backend is source of truth.
- [ ] **F. Winddown** → `/scenes/circadian` + `/sleep/wake-sequence` inform the
  journey; local flow otherwise unchanged.
- [ ] **G. Sounds** → stays local playback (no audio backend exists — honest
  scope); selection persisted via existing profile settings API.
- [ ] **H. Partner screen** → status/comparison/sleep/challenge.
- [ ] **I. Localization:** register `AppLocalizations.delegate` in `app.dart`
  (l10n tree already generated); en+ar strings for the six screens.

Each task ends: `flutter analyze` clean, `flutter test` green, commit. Backend
tasks also run the contract suite (~40s). Push at phase end → CI full suite.

## Traceability additions

| audit.md finding | Task |
|---|---|
| §1 decorative screens ×6 | C–H |
| §1 dead localization | I |
| (new) automation routes 401 for all callers | A |
| (debt) engines bed-level not per-user | deferred → Phase 2/3, revisit |
