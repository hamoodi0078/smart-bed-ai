# Danah Smart Bed AI — Implementation Plan

> **Purpose**: Finalize, polish, and hand off the project so another developer can run, debug, and extend it confidently.
> **Timeline**: 2-day sprint.

---

## 1. Project Health Summary

| Area | Status | Notes |
|------|--------|-------|
| Backend (FastAPI) | Functional | Dual entry: `web_server.py` (legacy) + `api/app_factory.py` (new) |
| Voice Runtime | Functional | `app_entry.py` — main loop with STT/TTS/wake word |
| Database | Functional | SQLAlchemy ORM, sync + async, PostgreSQL + SQLite fallback |
| Mobile App (Flutter) | Functional | Riverpod state, Sentry, l10n, onboarding |
| CI/CD | Functional | GitHub Actions: lint, test, smoke, Flutter, secret scan |
| Docker | Functional | 4-service compose: api, voice, worker, redis, db |
| Tests | Partial | 86+ test files, but coverage gaps in integrations and AI modules |
| Documentation | Incomplete | README exists; no unified manual or onboarding guide |

---

## 2. Critical Fixes (Day 1 — Morning)

### 2.1 Duplicate Prometheus Metrics Collectors
- **Problem**: Both `web_server.py` and `api/app_factory.py` register identically-named Prometheus counters (`*_http_requests_total`, etc.). Running both simultaneously causes `ValueError: Duplicated timeseries`.
- **Fix**: Use a shared metrics module (`core/metrics.py`) that registers collectors once; import from both files.

### 2.2 `web_server.py` Migration Completion
- **Problem**: `web_server.py` is 10,000+ lines — the legacy monolith. `api/app_factory.py` mounts it as a catch-all sub-app, but route duplication and import-time side effects create fragility.
- **Fix (phased)**:
  1. Extract remaining route groups from `web_server.py` into dedicated routers under `api/routers/`.
  2. Move shared state (profile RW lock, DB singletons, subscription store) into `api/dependencies.py`.
  3. Remove the `application.mount("/", _legacy_app)` fallback once all routes are migrated.

### 2.3 Settings Module Collision
- **Problem**: `config/base.py` and `config/settings.py` both define configuration. `config/__init__.py` imports from `base.py` but runtime code imports from `config.settings`. Some settings live in only one place.
- **Fix**: Consolidate into `config/settings.py` (Pydantic `BaseSettings`) as the single source of truth. Keep `config/__init__.py` as a thin re-export shim.

### 2.4 Hardcoded Paths and Fallbacks
- **Problem**: Several modules hardcode paths like `"guest_mode/guest_state.json"`, `Path("data") / "sleep_history.json"` instead of using `RUNTIME_DATA_DIR`.
- **Fix**: Route all file I/O through `config.settings.runtime_data_dir` paths. Add a startup check that creates required subdirectories.

---

## 3. Code Quality Improvements (Day 1 — Afternoon)

### 3.1 Function Duplication
- `normalize_for_intent()` and `has_any()` are duplicated in `voice_handler.py`, `scene_manager.py`, `main.py`, and `app_entry.py`.
- **Fix**: Consolidate into `core/text_utils.py`; replace all copies with imports.

### 3.2 Type Annotations
- Many functions use `dict` instead of typed models. Profile data is a nested `dict` passed everywhere.
- **Fix (incremental)**:
  1. Create `core/models.py` with `TypedDict` or Pydantic models for `UserProfile`, `SleepData`, `Preferences`.
  2. Add type hints to the 10 most-called functions first.
  3. Enable `mypy --strict` on `api/` and `database/` (CI already runs informational mypy).

### 3.3 Error Handling Consistency
- Some modules use bare `except Exception`, swallowing errors silently.
- **Fix**: Replace with specific exception types; add `logger.debug/warning` on catch.

### 3.4 Import Hygiene
- `voice_handler.py` has 70+ imports. Mid-file imports exist in `stt_manager.py`.
- **Fix**: Group imports into lazy loaders where optional dependencies are involved. Move utility imports to module level.

---

## 4. Testing Improvements (Day 1 — Evening)

### 4.1 Coverage Gaps
Priority test additions:
| Module | Current | Target | Action |
|--------|---------|--------|--------|
| `voice_handler.py` | Low | 60% | Add intent detection unit tests |
| `automation_engine.py` | Medium | 80% | Add automation trigger/cooldown tests |
| `subscriptions/gate.py` | Medium | 90% | Add trial expiry edge cases |
| `qr_code/pair_device.py` | Low | 80% | Add pair/unpair/status tests |
| `islamic_mode/prayer_times.py` | Low | 70% | Mock Aladhan API, test cache fallback |
| `gamification/achievement_engine.py` | Low | 70% | Test unlock flow and metric gathering |

### 4.2 Integration Test Fixtures
- Create `tests/fixtures/sample_profile.json` with a realistic user profile.
- Create `tests/fixtures/prayer_cache.json` with cached Aladhan response.
- Create `tests/conftest.py` shared fixtures for DB session, test client, and mock settings.

### 4.3 Smoke Test Expansion
- `scripts/mobile_smoke.py` only hits health endpoints. Expand to cover:
  - Auth flow (register → login → refresh)
  - Profile CRUD
  - Scene list + apply
  - Alarm create + list

---

## 5. Automation & Library Improvements (Day 2 — Morning)

### 5.1 Replace Manual HTTP with `httpx`
- `stt_manager.py`, `tts_manager.py`, `prayer_times.py`, and `voice_handler.py` use synchronous `requests.post/get`.
- **Recommendation**: Replace with `httpx` (already async-friendly) for consistency with the FastAPI async stack. Add `httpx` to `requirements.txt`.

### 5.2 Structured Logging Everywhere
- `core/structured_logging.py` exists with `emit_json_log()` but many modules still use `print()` or raw `logging`.
- **Fix**: Replace all `print(f"[FLOW]...")` in `app_entry.py` and `voice_handler.py` with `emit_json_log()`. This enables log aggregation in production.

### 5.3 Celery → ARQ Migration
- Both Celery and ARQ are in `requirements.txt` and `tasks/`. The Docker compose uses ARQ for the worker.
- **Fix**: Complete migration to ARQ only. Remove Celery deps (`celery`, `celery_app.py`) to reduce dependency surface.

### 5.4 Database Migration Tooling
- Alembic is configured but only has a few migration files.
- **Fix**: Auto-generate a migration for each ORM model change. Add `alembic upgrade head` to the Docker entrypoint and CI pipeline.

### 5.5 Dependency Pinning
- `requirements.txt` has no version pins. This causes reproducibility issues.
- **Fix**: Pin all direct dependencies. Generate a `requirements.lock` with `pip-compile` for reproducible builds.

---

## 6. Security Hardening (Day 2 — Morning)

### 6.1 Secret Validation on Startup
- `config/settings.py` has `validate_production_secrets()` but it's never called on startup.
- **Fix**: Call it in `api/app_factory.py` lifespan and log warnings.

### 6.2 Rate Limiting Coverage
- Rate limiting middleware exists but only applies to the new `app_factory` app, not the legacy `web_server.py`.
- **Fix**: Apply `RateLimitMiddleware` to both apps, or complete the route migration (Section 2.2).

### 6.3 CORS Tightening
- Default CORS allows `*` localhost origins. Production must restrict to actual frontend domains.
- **Fix**: Document in `.env.example` and add a startup warning if `WEB_ALLOWED_ORIGINS` contains `*`.

---

## 7. DevOps & Deployment Polish (Day 2 — Afternoon)

### 7.1 Docker Compose Improvements
- Add a `migrations` service that runs `alembic upgrade head` before `api` starts.
- Add volume mounts for `local_music/` directory.
- Add Prometheus + Grafana services for monitoring stack.

### 7.2 Systemd Services
- `scripts/systemd/` has service files but they reference hardcoded paths.
- **Fix**: Templatize with `EnvironmentFile=/etc/danah/.env`.

### 7.3 Health Check Completeness
- `/healthz` only checks API liveness. Add `/readyz` that verifies DB, Redis, and Deepgram connectivity.
- The app_factory already has this — ensure the legacy app exposes the same.

---

## 8. Documentation Deliverables (Day 2 — Afternoon/Evening)

### 8.1 PROJECT_MANUAL.md (separate file)
- Full system architecture, module-by-module explanation, library reference, voice command catalog, API endpoint list, admin panel guide, mobile app guide, QR pairing instructions, and deployment runbook.

### 8.2 README.md Refresh
- Update with quick-start commands, `.env` setup steps, Docker launch instructions, and links to PROJECT_MANUAL.md.

### 8.3 ADR (Architecture Decision Records)
- `docs/adr/0001-use-deepgram-for-voice.md` exists. Add:
  - `0002-dual-entry-point-migration.md` (web_server → app_factory)
  - `0003-arq-over-celery.md`

---

## 9. Handoff Checklist

Before handing off to the next developer:

- [ ] All tests pass: `pytest tests/ -q --tb=short`
- [ ] Ruff lint clean: `ruff check .`
- [ ] Ruff format clean: `ruff format --check .`
- [ ] Bandit security scan clean: `bandit -c bandit.yml -r . --exclude .venv,tests,mobile_app -ll`
- [ ] Docker compose starts cleanly: `docker compose up --build`
- [ ] Health check passes: `curl http://localhost:8000/healthz`
- [ ] `.env.example` is complete and up to date
- [ ] `PROJECT_MANUAL.md` is complete
- [ ] `IMPLEMENTATION_PLAN.md` is complete (this file)
- [ ] No secrets in git history: `gitleaks detect`
- [ ] Database migrations are current: `alembic upgrade head`
- [ ] Mobile app builds: `cd mobile_app && flutter build apk`

---

## 10. Priority Matrix

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Fix Prometheus duplicate collectors | 30 min | Blocks running both apps |
| P0 | Consolidate settings modules | 1 hr | Eliminates config confusion |
| P0 | Fix hardcoded file paths | 1 hr | Prevents runtime failures |
| P1 | Deduplicate utility functions | 1 hr | Reduces maintenance burden |
| P1 | Pin dependencies in requirements.txt | 30 min | Reproducible builds |
| P1 | Complete PROJECT_MANUAL.md | 3 hr | Enables handoff |
| P1 | Expand test coverage (top 6 modules) | 3 hr | Confidence for new dev |
| P2 | Migrate remaining web_server.py routes | 4 hr | Clean architecture |
| P2 | Replace requests with httpx | 2 hr | Async consistency |
| P2 | Remove Celery, keep ARQ only | 1 hr | Simpler deps |
| P2 | Add structured logging everywhere | 2 hr | Production observability |
| P3 | Prometheus + Grafana in compose | 1 hr | Monitoring |
| P3 | ADR documentation | 1 hr | Architectural context |
