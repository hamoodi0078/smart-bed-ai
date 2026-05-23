# Smart Bed AI — Gap Improvement Plan

**Based on production-readiness audit. This plan addresses every critical, high, and medium gap that can cause project failure.**

**Timeline:** 6 weeks (if executed sequentially; some tracks can run in parallel)
**Priority:** P0 = Ship-blocker, P1 = Security/stability risk, P2 = Quality/trust risk

---

## P0 — CRITICAL (Week 1 only)

> These are ship-blockers. Do not deploy or share the codebase externally until all P0 items are resolved.

---

### P0-1: Rotate All Live Secrets & Lock Down `.env`

**Gap:** Real API keys, database passwords, and PayPal credentials are stored in plaintext `.env` on disk.

**Implementation Steps:**
1. **Today**: Log into each provider dashboard and revoke/regenerate every leaked key:
   - OpenAI (https://platform.openai.com/api-keys)
   - Deepgram (https://console.deepgram.com/)
   - Neon PostgreSQL (reset password in project settings)
   - PayPal Developer (rotate client secret)
   - SendGrid (rotate API key)
   - Spotify Developer (reset client secret)
2. **Today**: Remove `c:\Users\PC#####\Desktop\smart bed by me\.env` from all cloud backups, email attachments, and zip archives.
3. **Day 1-2**: Add a secret-manager abstraction layer.
   - Create `config/secrets.py` that reads from environment variables *only* (no file on disk in production).
   - For local dev, use a `.env.local` that is gitignored and documented.
4. **Day 2**: Install `detect-secrets` or `ggshield` as a pre-commit hook.
   ```bash
   pip install pre-commit detect-secrets
   pre-commit install
   ```
   Add `.pre-commit-config.yaml`:
   ```yaml
   repos:
     - repo: https://github.com/Yelp/detect-secrets
       rev: v1.4.0
       hooks:
         - id: detect-secrets
   ```

**Acceptance Criteria:**
- [ ] `git log --all --full-history -- '.env'` shows no commits with `.env`.
- [ ] `detect-secrets scan` returns 0 high-entropy strings in source.
- [ ] All old API keys return 401/403 when tested.

---

### P0-2: Make JWT `SECRET_KEY` a Mandatory Startup Gate

**Gap:** `config/settings.py` warns but does not crash if `SECRET_KEY` is the default `"change-me-in-production"`. In some deployment flows the `DANAH_ENV` variable is missed, so the production check never fires.

**Implementation Steps:**
1. In `config/settings.py`, update `secret_key_must_be_secure`:
   ```python
   @validator("SECRET_KEY")
   def secret_key_must_be_secure(cls, v: str) -> str:
       unsafe = {"change-me-in-production", "changeme", "secret", "your-secret-key", "supersecret"}
       if v.strip().lower() in unsafe or len(v) < 32:
           raise ValueError(
               "SECRET_KEY is unsafe or too short. Generate one with:\n"
               "python -c 'import secrets; print(secrets.token_hex(32))'"
           )
       return v
   ```
2. Remove the `if not is_production()` guard from `secret_key_must_be_secure`. The validator should run **unconditionally**.
3. Add a test in `tests/config/test_settings.py`:
   ```python
   import pytest
   from pydantic import ValidationError
   from config.settings import Settings

   def test_settings_reject_default_secret_key():
       with pytest.raises(ValidationError):
           Settings(SECRET_KEY="change-me-in-production")
   ```

**Acceptance Criteria:**
- [ ] App crashes during startup with a clear error if `SECRET_KEY` is unsafe.
- [ ] Unit test passes: default secret is rejected.

---

### P0-3: Fix `validate_production_secrets()` Crash

**Gap:** `config/settings.py:479` references `settings.anthropic_api_key`, which does not exist on the `Settings` model. This raises `AttributeError` on every production startup.

**Implementation Steps:**
1. Open `config/settings.py`.
2. Locate `validate_production_secrets()`.
3. Either:
   - **Option A**: Remove the `anthropic_api_key` check entirely if you do not use Anthropic.
   - **Option B**: Add `anthropic_api_key: SecretStr | None = None` to the `Settings` class if you plan to use it.
4. Add a regression test in `tests/config/test_settings.py` that instantiates `Settings()` with `DANAH_ENV=production` (mock the env var) and confirms no `AttributeError` is raised.

**Acceptance Criteria:**
- [ ] `python -c "from config.settings import validate_production_secrets; validate_production_secrets()"` runs without error.
- [ ] CI test exists that validates production startup.

---

### P0-4: Hardware Safety Limits & Emergency Stop

**Gap:** A software bug or automation crash can lock LEDs to 100% brightness, blast audio at night, or leave GPIO pins in an unsafe state. There is no hardware-level safety net.

**Implementation Steps:**
1. **Software Caps (Day 1)**:
   - In `led/led_control.py` or `led_controller.py`, enforce a `MAX_BRIGHTNESS_PERCENT = 80` (or lower) at the **write** level. No caller should be able to override it without a physical jumper.
   - Add a `HARDWARE_EMERGENCY_STOP` flag to `config/settings.py` (default `False`).
2. **Automation Timeout (Day 1-2)**:
   - In `automation_engine.py`, wrap every automation effect in a `signal.alarm(5)` or `asyncio.wait_for(..., timeout=5)` so a stuck automation cannot run longer than 5 seconds.
3. **Night Mode Hard Lock (Day 2)**:
   - During configured quiet hours (22:00–06:00), require `quiet_mode_active=True` to suppress all non-emergency audio and cap LEDs to `music_lights_night_brightness_percent` (max 20%).
   - Make this logic live in `automation_engine.py` before any effect is emitted.
4. **Physical Mute (Day 2-3)**:
   - Document that the Raspberry Pi must have a physical button on GPIO pin (e.g., GPIO 26) that grounds the audio amplifier's `SHUTDOWN` pin or calls a system-level mute. This cannot be overridden by software.

**Acceptance Criteria:**
- [ ] Setting LED brightness to 100 via API is capped to 80 (or your chosen max) in hardware output.
- [ ] During quiet hours, any `say` automation is dropped unless prefixed with `[EMERGENCY]`.
- [ ] Automation effects time out after 5 seconds.

---

## P1 — HIGH (Weeks 2–4)

> These will cause data breaches, data loss, or product instability if not fixed before any user onboarding.

---

### P1-5: Local-First Fallback Architecture

**Gap:** The bed is entirely useless if the internet drops, because auth, sleep tracking, and voice depend on Neon PostgreSQL, Redis, and Deepgram/OpenAI cloud APIs.

**Implementation Steps:**
1. **Offline Auth Cache (Week 2)**:
   - Create `database/local_cache.py` using SQLite (`aiosqlite`) or JSON file.
   - On successful login, mirror the user's profile and tokens to the local cache.
   - If the async PostgreSQL connection fails (`_ASYNC_DB_AVAILABLE = False`), fall back to the local cache for read-only auth checks.
2. **Voice Pipeline Offline Mode (Week 2-3)**:
   - Your requirements already include `faster-whisper` and `piper-tts`. Create a `services/offline_voice.py` module.
   - When `STT_MODE=local` or Deepgram returns 429/5xx, route to the local Whisper model (`base` or `small`).
   - When `TTS_MODE=local` or Piper is available, synthesize locally instead of calling Deepgram TTS.
3. **Sleep Data Local Buffer (Week 3)**:
   - If the PostgreSQL connection drops during a sleep session, buffer sensor events to a local SQLite table.
   - When connectivity returns, replay the buffered events to the cloud database.

**Acceptance Criteria:**
- [ ] Disconnecting the internet does not crash the app or block login for a recently-authenticated user.
- [ ] Voice commands work in offline mode with degraded but functional accuracy.
- [ ] Sleep session data is not lost during a 24-hour outage.

---

### P1-6: Decompose `web_server.py` and `voice_handler.py`

**Gap:** `web_server.py` (~397 KB) and `voice_handler.py` (~173 KB) are monolithic unmaintainable blocks. Bug fixes are high-risk, code review is impractical, and test coverage is impossible.

**Implementation Steps:**
1. **Inventory (Week 2, Day 1)**:
   - Run `python -m cProfile -o profile.stats web_server.py` or manually list every route handler inside it.
   - Categorize by domain: auth, profile, sleep, scenes, music, admin, voice.
2. **Extract by Domain (Weeks 2–3)**:
   - Move auth handlers to `api/routers/auth.py` (already partially done).
   - Move profile handlers to `api/routers/profile.py`.
   - Move sleep/scene handlers to `api/routers/sleep.py`.
   - Move music/Spotify handlers to `api/routers/media.py`.
   - Move admin handlers to `api/routers/admin.py`.
3. **Extract Voice Pipeline (Week 2-3)**:
   - `voice_handler.py` should become:
     - `services/voice/stt.py` (speech-to-text orchestrator)
     - `services/voice/tts.py` (text-to-speech orchestrator)
     - `services/voice/intent.py` (intent recognition / NLU)
     - `services/voice/session.py` (voice session state machine)
4. **Delete `web_server.py` (Week 4)**:
   - Once all routers are in `api/routers/`, delete `web_server.py` entirely.
   - Update `api/app_factory.py` to import only the new routers.

**Acceptance Criteria:**
- [ ] `web_server.py` does not exist in the repo.
- [ ] `voice_handler.py` is < 200 lines (just a thin launcher if needed).
- [ ] Every route has at least one unit or integration test.

---

### P1-7: Field-Level Encryption for Health Data

**Gap:** Health and sleep data is stored in PostgreSQL in plaintext. A database breach exposes all user health records.

**Implementation Steps:**
1. **Choose Method (Week 2)**:
   - **Option A (Recommended)**: Application-level encryption using `cryptography` (Fernet or AES-GCM).
   - **Option B**: PostgreSQL `pgcrypto` extension.
2. **Implement Encryption Layer (Week 2-3)**:
   - Create `core/encryption.py`:
     ```python
     from cryptography.fernet import Fernet
     from config.settings import settings

     _cipher = Fernet(settings.data_encryption_key.get_secret_value().encode())

     def encrypt_field(plaintext: str) -> str:
         return _cipher.encrypt(plaintext.encode()).decode()

     def decrypt_field(ciphertext: str) -> str:
         return _cipher.decrypt(ciphertext.encode()).decode()
     ```
   - Add `data_encryption_key: SecretStr` to `Settings` (mandatory, 32-byte base64).
3. **Encrypt Sensitive Models (Week 3)**:
   - In `database/models.py`, encrypt these fields before SQLAlchemy persists them:
     - `User.full_name`
     - `SleepSession.*` (all health metrics)
     - `Event.payload` (if it contains health data)
   - Use SQLAlchemy TypeDecorator:
     ```python
     from sqlalchemy.types import TypeDecorator, Text as saText

     class EncryptedText(TypeDecorator):
         impl = saText
         def process_bind_param(self, value, dialect):
             return encrypt_field(value) if value else value
         def process_result_value(self, value, dialect):
             return decrypt_field(value) if value else value
     ```

**Acceptance Criteria:**
- [ ] `SELECT * FROM sleep_sessions` in a SQL client shows ciphertext, not plaintext heart rate or breathing data.
- [ ] Application queries return decrypted data correctly.

---

### P1-8: Harden CORS Credentials Logic

**Gap:** `api/app_factory.py` sets `allow_credentials=True` based on a brittle boolean expression. A misconfigured origin list could allow credentials with wildcard origins.

**Implementation Steps:**
1. In `api/app_factory.py`, replace the inline boolean with an explicit validation block:
   ```python
   if "*" in allowed_origins and allow_credentials:
       raise RuntimeError(
           "CORS misconfiguration: allow_credentials=True is incompatible with allow_origins=['*']"
       )
   ```
2. Add this check to the app startup lifespan, before `application.add_middleware(CORSMiddleware, ...)`.

**Acceptance Criteria:**
- [ ] Startup crashes with a clear error if `*` is in origins and credentials are enabled.
- [ ] Unit test exists for this validation.

---

### P1-9: Make Rate Limiting Mandatory

**Gap:** `RateLimitMiddleware` is wrapped in `try/except ImportError: pass`. If the import breaks, the app runs with **zero** rate limiting.

**Implementation Steps:**
1. In `api/app_factory.py`, remove the `try/except` block.
2. Make the import unconditional:
   ```python
   from api.middleware.rate_limiter import RateLimitMiddleware
   application.add_middleware(RateLimitMiddleware)
   ```
3. If `RateLimitMiddleware` currently depends on optional Redis, modify it to use an in-memory `dict` fallback when Redis is unavailable, but **never** skip rate limiting entirely.

**Acceptance Criteria:**
- [ ] App crashes on startup if `RateLimitMiddleware` cannot be imported.
- [ ] Brute-force tests (e.g., 100 login requests) are blocked after the configured threshold.

---

### P1-10: Replace File-Based Voice Circuit Breaker with Redis

**Gap:** `runtime_data/voice_circuit_reset_signal.json` is used for circuit breaker state. This is unreliable in multi-worker Gunicorn deployments and across Docker restarts.

**Implementation Steps:**
1. Create `services/circuit_breaker.py` using Redis (or `aioredis`) as the backend.
2. Store circuit state in a Redis key with TTL:
   ```python
   await redis.set("circuit:voice:state", "open", ex=60)
   ```
3. Replace all reads/writes to `VOICE_CIRCUIT_RESET_SIGNAL_PATH` with calls to the new service.
4. Delete `runtime_data/voice_circuit_reset_signal.json` references from `config/settings.py`.

**Acceptance Criteria:**
- [ ] Two concurrent Gunicorn workers see the same circuit state.
- [ ] Circuit state survives a single worker crash but not a full Redis flush (which is acceptable).

---

## P2 — MEDIUM (Weeks 5–6)

> These degrade user trust, product quality, and maintainability.

---

### P2-11: Add Security Headers Middleware

**Gap:** No `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`, or `X-Content-Type-Options` headers are set.

**Implementation Steps:**
1. Create `api/middleware/security_headers.py`:
   ```python
   from fastapi import Request
   from starlette.middleware.base import BaseHTTPMiddleware

   class SecurityHeadersMiddleware(BaseHTTPMiddleware):
       async def dispatch(self, request: Request, call_next):
           response = await call_next(request)
           response.headers["X-Frame-Options"] = "DENY"
           response.headers["X-Content-Type-Options"] = "nosniff"
           response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
           response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
           return response
   ```
2. Register it in `api/app_factory.py` before CORS middleware.
3. If running in production with HTTPS, add `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`.

**Acceptance Criteria:**
- [ ] Security scan (Mozilla Observatory or `securityheaders.com`) scores B or higher.

---

### P2-12: Make Push Notifications Critical-Path

**Gap:** Firebase FCM is wrapped in `try/except` and silently skipped on failure. For a health/wake-up device, missing a prayer-time or health alert push is a product failure.

**Implementation Steps:**
1. In the notification service, do not swallow Firebase errors:
   ```python
   # Instead of:
   try:
       await fcm.send(...)
   except Exception:
       pass

   # Do:
   try:
       await fcm.send(...)
   except Exception as exc:
       logger.error("FCM push failed for user %s: %s", user_id, exc)
       # Retry with exponential backoff via your job queue (ARQ)
       raise  # Let the job queue retry
   ```
2. Add a local notification fallback: if FCM fails 3 times, log a critical alert so the user knows the device needs attention.
3. Add health check endpoint `/health/push` that verifies FCM token validity on startup.

**Acceptance Criteria:**
- [ ] Failed push notifications are retried at least 3 times with backoff.
- [ ] A failed push after retries triggers a visible error in logs/metrics.

---

### P2-13: Fix `get_current_user_optional` Exception Swallowing

**Gap:** `get_current_user_optional` in `auth/middleware.py` catches all `HTTPException` and returns `None`. This hides expired tokens and invalid signatures from the caller.

**Implementation Steps:**
1. Change the function to explicitly distinguish cases:
   ```python
   async def get_current_user_optional(
       credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
   ) -> Optional[dict]:
       if not credentials:
           return None
       try:
           return await get_current_user(credentials)
       except HTTPException as exc:
           if exc.status_code == 401:
               # Re-raise so the client knows the token is bad/expired
               raise
           return None
   ```
2. Update any routes that use `get_current_user_optional` to handle `401` explicitly.

**Acceptance Criteria:**
- [ ] A route with an expired token returns `401`, not `200` with `user=null`.

---

### P2-14: Add Regression Test for Production Startup

**Gap:** The `validate_production_secrets` bug shows there is no test that simulates production startup end-to-end.

**Implementation Steps:**
1. Create `tests/test_production_startup.py`:
   ```python
   import os
   import pytest
   from fastapi.testclient import TestClient

   @pytest.fixture
   def prod_env():
       old_env = os.environ.copy()
       os.environ["DANAH_ENV"] = "production"
       os.environ["SECRET_KEY"] = "a" * 64  # valid test key
       os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"
       os.environ["REDIS_URL"] = "redis://localhost:6379/0"
       yield
       os.environ.clear()
       os.environ.update(old_env)

   def test_app_starts_in_production(prod_env):
       from api.app_factory import create_app
       app = create_app()
       with TestClient(app) as client:
           response = client.get("/health")
           assert response.status_code == 200
   ```
2. Run this test in CI on every PR.

**Acceptance Criteria:**
- [ ] CI pipeline fails if production startup raises any exception.

---

## Cross-Cutting Concerns

| Concern | Action | Owner |
|---------|--------|-------|
| **Documentation** | Update `README.md` with secret rotation checklist and hardware safety wiring diagram. | You |
| **CI/CD** | Add GitHub Actions (or similar) job that runs `detect-secrets`, `pytest`, and `bandit` on every PR. | You |
| **Monitoring** | Add a Grafana alert for `rate(error_logs[5m]) > 0` specifically for auth and hardware modules. | You |
| **Mobile App** | Ensure the Flutter app caches auth tokens offline and gracefully degrades when the API is unreachable. | Mobile dev |

---

## Weekly Execution Checklist

### Week 1 — P0 Critical
- [ ] P0-1: Rotate all secrets, install pre-commit hooks
- [ ] P0-2: Enforce JWT secret at startup
- [ ] P0-3: Fix `validate_production_secrets` bug + regression test
- [ ] P0-4: Hardware caps, automation timeout, night mode lock

### Week 2 — P1 Infrastructure
- [ ] P1-5: Offline auth cache
- [ ] P1-6: Inventory `web_server.py` routes; begin extraction
- [ ] P1-9: Make rate limiting mandatory

### Week 3 — P1 Security & Data
- [ ] P1-6: Continue monolith extraction; voice handler split
- [ ] P1-7: Implement field-level encryption on sensitive models
- [ ] P1-5: Voice pipeline offline mode (Whisper local)

### Week 4 — P1 Stability
- [ ] P1-6: Delete `web_server.py`; final router migration
- [ ] P1-8: Harden CORS validation
- [ ] P1-10: Redis-based circuit breaker

### Week 5 — P2 Quality
- [ ] P2-11: Security headers middleware
- [ ] P2-12: Push notification retries & health check
- [ ] P2-13: Fix `get_current_user_optional`

### Week 6 — P2 Polish & CI
- [ ] P2-14: Production startup regression test
- [ ] Cross-cutting: CI/CD pipeline with secret scanning, bandit, pytest
- [ ] Final security audit & penetration test of auth endpoints

---

*Do not begin Weeks 2–6 until all Week 1 P0 items are verified complete. P0 gaps can destroy the project regardless of how good the rest of the architecture becomes.*
