# ADR 0002 — Dual Entry-Point Migration (web_server → app_factory)

**Status**: In Progress
**Date**: 2025-05

## Context

The original API was a single monolithic file (`web_server.py`, ~10,000 lines) containing all routes, middleware, database singletons, and business logic. As the project grew, this became difficult to maintain, test, and review.

## Decision

Introduce `api/app_factory.py` as a new FastAPI application factory that:

1. Assembles middleware (CORS, rate limiting, metrics, error handling) in a clean stack.
2. Includes modular routers from `api/routers/` (health, auth, alarms, sleep, scenes, profile, islamic, metrics).
3. Manages async lifecycle (DB pool, Redis, Firebase, ARQ) via FastAPI lifespan.
4. Mounts `web_server.py` as a catch-all fallback at `/` so un-migrated routes still work.

Routes are migrated incrementally from `web_server.py` into dedicated router files. Once all routes are migrated, the `mount("/", _legacy_app)` line is removed and `web_server.py` is archived.

## Consequences

- **Positive**: Clean separation of concerns, testable routers, standard FastAPI patterns.
- **Positive**: New developers only need to understand `app_factory.py` + the router they're working on.
- **Negative**: During migration, some routes exist in both files — care needed to avoid duplication.
- **Negative**: Shared state (profile lock, DB singletons) must be coordinated between both apps.

## Migration Checklist

- [x] Health, metrics, Islamic routers
- [x] Auth, alarms, sleep, scenes, profile routers
- [ ] Mobile API routes (pairing, commands, feedback)
- [ ] Spotify OAuth routes
- [ ] Billing / subscription routes
- [ ] Admin panel routes
- [ ] Chat / conversation routes
- [ ] Remove legacy mount
