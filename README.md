# Smart Bed AI Runtime

Production-ready backend runtime for the Smart Bed voice assistant, with realtime voice flow, adaptive personality, long-term memory, and web/mobile bridge APIs.

## Project Structure

```
├── ai/                  # AI modules (conversation, emotion, sleep intelligence)
├── alembic/             # Database migration scripts (Alembic)
├── api/                 # FastAPI routers and middleware
│   └── middleware/      # Rate limiter, auth helpers
├── automations/         # Automation engine and rule registry
├── commands/            # Command handlers and undo manager
├── constants/           # Centralized constants (voice, limits, scenes)
├── core/                # Core infrastructure (errors, logging, types)
├── database/            # SQLAlchemy models, repositories, connection
├── docs/adr/            # Architecture Decision Records
├── health/              # Health monitoring modules
├── mobile_app/          # Flutter mobile application
├── notifications/       # Email and push notification services
├── scenes/              # Scene management and weather-adaptive logic
├── scripts/             # Dev and deployment scripts
├── Storage/             # JSON file I/O and subscription store
├── subscriptions/       # Billing service integration
├── tests/               # Test suite (pytest)
├── web/                 # Static web assets
├── .github/workflows/   # CI/CD pipeline
├── Dockerfile           # Container image definition
├── docker-compose.yml   # Local dev orchestration (backend + PostgreSQL)
├── pyproject.toml       # Pytest and coverage configuration
├── requirements.txt     # Production Python dependencies
└── requirements-dev.txt # Dev/test Python dependencies
```

## Developer Quick Start (App Development Phase)

### 1) Prerequisites
- Python 3.11+
- Windows PowerShell (or bash on Linux/macOS)
- `.env` configured (copy from `.env.example`)

### 2) Install dependencies
```powershell
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pre-commit install
```

### 3) Configure environment
```powershell
Copy-Item .env.example .env
# Edit .env and fill in your API keys
```

Required keys:
- `DEEPGRAM_API_KEY` — STT, TTS, and Voice Agent
- `DEEPGRAM_VOICE_AGENT_MODEL` — LLM/agent model id
- `WAKE_WORD_MODE` — `keyboard` for desktop, `voice` on device

Optional:
- `DATABASE_URL` — PostgreSQL connection string (falls back to SQLite)
- `OPENAI_API_KEY` — Direct GPT route (set `USE_OPENAI_DIRECT=1`)
- `APP_BASE_URL` / `APP_BACKEND_BASE_URL` — If clients are external

### 4) Start backend
Preferred script flow:
```powershell
.\scripts\start_backend.ps1
```
Alternative:
```powershell
python main.py
```

### 5) Start web runtime API
```powershell
python -m uvicorn api.app_factory:app --host 127.0.0.1 --port 8000 --reload
```

### 6) Validate core health
- `GET /healthz` — basic liveness check
- `GET /healthz/detailed` — database, disk, API key status
- Run test suite:
```powershell
python -m pytest tests/ --cov --cov-report=term-missing -q
```

### 7) Docker (optional)
```bash
docker compose up --build
```

## Raspberry Pi 5 Runtime

The backend can run on Raspberry Pi OS 64-bit while the Flutter app stays on your phone.

Quick path:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
python main.py
python -m uvicorn api.app_factory:app --host 0.0.0.0 --port 8000
```

Pi-specific notes:
- Set `WAKE_WORD_MODE=voice`
- Set `APP_BASE_URL` and `APP_BACKEND_BASE_URL` to `http://<pi-ip>:8000`
- Enable real LED output with `LED_HARDWARE_ENABLED=1`
- Configure GPIO sensor pins with `SENSOR_PRESSURE_PIN` / `SENSOR_MOTION_PIN`
- Point the phone app at the Pi with `--dart-define=SMART_BED_API_BASE_URL=http://<pi-ip>:8000`

Full setup steps are in [`docs/raspberry-pi-setup.md`](/c:/Users/PC#####/Desktop/smart%20bed%20by%20me/docs/raspberry-pi-setup.md).

### 7) Run mobile smoke flow (manual E2E helper)
With backend running on `127.0.0.1:8000`, execute:
```powershell
.\.venv311\Scripts\python.exe .\scripts\mobile_smoke.py --base-url http://127.0.0.1:8000
```
This validates: `signup/register -> dashboard -> quick action -> scene preview -> timeline update`.

### 8) Check Day 36-45 beta exit gate (admin API)
- Endpoint: `GET /v1/admin/mobile/beta-acceptance?max_testers=5&min_required=3`
- Auth: admin session required
- Returns: scoped tester rows + blockers + `exit_gate_pass` so you can decide if the cohort is ready to move past the first 45-day window.

### 9) Track Month 2 Kuwait cohort progress (admin API)
- Enroll/update tester: `POST /v1/admin/mobile/beta-cohort/enroll`
- Cohort report: `GET /v1/admin/mobile/beta-cohort?cohort_key=kuwait_beta&target_min=10&target_max=15`
- Returns active tester counts, target-gap status, and tester-level rollout metrics.

### 10) Run one Day-45 gate command (recommended)
From repo root:
```powershell
.\.venv311\Scripts\python.exe .\scripts\day45_gate.py --base-url http://127.0.0.1:8000
```
Useful options:
- `--skip-smoke` if backend is not running yet
- `--skip-flutter` for backend-only checks
- `--flutter-cmd "C:\src\flutter\flutter\bin\flutter.bat"` if `flutter` is not on PATH

## Flutter Mobile Shell

The primary customer surface is now the Flutter app in [`mobile_app/`](/c:/Users/PC#####/Desktop/smart%20bed%20by%20me/mobile_app).

### Mobile quick start
```powershell
cd mobile_app
flutter pub get
flutter analyze
flutter test
flutter run --dart-define=SMART_BED_API_BASE_URL=http://10.0.2.2:8000
```

### VS Code Run and Debug (Windows desktop)
- Open `mobile_app` as your workspace for the cleanest Flutter debug flow.
- Use launch profile `Flutter Windows (Smart Bed)` from `mobile_app/.vscode/launch.json`.
- If you keep the repo root open, use `Flutter Windows (Smart Bed / mobile_app)` from `.vscode/launch.json`.
- Start backend first from repo root:
```powershell
.\scripts\start_backend.ps1
```

Notes:
- Android emulator defaults to `http://10.0.2.2:8000`
- iOS simulator defaults to `http://127.0.0.1:8000`
- Use `--dart-define=SMART_BED_API_BASE_URL=https://your-host` for staging or physical-device testing
- Mobile settings now include automation controls: `bedtime_drift_automation_enabled`, `quiet_hours_override_limit_minutes`, and `weekly_insight_enabled`
- Mobile automation feedback loop is live: `POST /v1/mobile/device-commands/{command_id}/feedback` and dashboard field `automation_feedback_loop`

## CI Quality Gates

GitHub Actions now blocks merges unless both lanes pass:

- `backend`: Python 3.11 dependency install + `ruff check .` + `python -m unittest discover -s tests -p "test_*.py"`
- `mobile`: Flutter 3.41.4 + `flutter pub get` + `flutter analyze` + `flutter test`

## New Unified State Bridge API

### `GET /v1/bed/state`
Unified state snapshot for website/mobile clients to render the AI and device runtime in near realtime.

**Auth:** user or admin session cookie required.

**Response shape:**
```json
{
  "ok": true,
  "generated_at": "2026-02-24T18:40:00+00:00",
  "emotion_state": "neutral",
  "active_personality": "guide",
  "last_memory_context": "Last memory turn: user='...'; ...",
  "biometric_summary": {
    "recovery_mode": false,
    "challenge_level": 1,
    "night_wake_count": 0,
    "bedtime_samples": 12,
    "wake_samples": 12,
    "partner_mode_enabled": false,
    "last_bedtime_drift_alert_date": ""
  },
  "device_health_status": {
    "deepgram_configured": true,
    "spotify_connected_users": 1,
    "led": {
      "user_strip_pin": 18,
      "state_strip_pin": 13,
      "user_strip_led_count": 120,
      "state_strip_led_count": 60
    },
    "last_scene_key": "balanced_default",
    "last_preload_phase": "sleep",
    "sensor_pressure_active": false,
    "sensor_motion_active": false
  }
}
```

## App Integration Notes

- Poll `/v1/bed/state` every 2-5 seconds for live dashboard state.
- Use `emotion_state + active_personality + last_memory_context` for conversational UI continuity.
- Use `device_health_status` to surface setup diagnostics and LED/device telemetry.
- Use `biometric_summary` for sleep widgets and adaptive coaching cards.

## Final System Check Scope

`tests/final_system_check.py` simulates:
1. User speech (STT)
2. LLM streaming response
3. Parallel TTS pipeline playback
4. Memory persistence

This is the baseline release check before onboarding new pilot customers.

## Raspberry Pi 5 (Backend-Only Transfer)

For runtime-only Pi deployment (without Flutter mobile source on Pi), use:
- `docs/raspberry-pi-backend-only-transfer.md`

---

## Authentication & Security

### JWT Authentication

The backend now uses industry-standard JWT authentication for API access.

**Setup:**
1. Generate a secure secret key:
   ```bash
   openssl rand -hex 32
   ```
2. Add to `.env`:
   ```bash
   SECRET_KEY=your-generated-key-here
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=15
   REFRESH_TOKEN_EXPIRE_DAYS=7
   ```

**Token Flow:**
- Access tokens: 15 minutes (short-lived, stateless)
- Refresh tokens: 7 days (stored in DB, revocable)
- Token rotation on refresh (old token automatically revoked)

### User Registration & Login

**Register:**
```bash
POST /v1/auth/register
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "full_name": "John Doe"
}
```

**Login:**
```bash
POST /v1/auth/login
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}

# Response:
{
  "access_token": "eyJ...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Protected Routes:**
```bash
GET /api/user/profile
Authorization: Bearer eyJ...
```

### Role-Based Access Control (RBAC)

**Roles:**
- `user` - Standard user (default)
- `admin` - Administrator
- `superadmin` - Super administrator

**Example:**
```python
from fastapi import Depends
from auth.middleware import require_role

@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: dict = Depends(require_role("admin"))
):
    # Only admins can access this endpoint
    pass
```

### Security Features

✅ **Bcrypt password hashing** (12 rounds)  
✅ **JWT token authentication** with refresh token rotation  
✅ **Role-based access control** (RBAC)  
✅ **Token blacklisting** for logout  
✅ **Account status checking** (is_active flag)  
✅ **Production secret validation**  
✅ **CORS security** (environment-aware, HTTPS-only in production)  
✅ **Last login tracking**  
✅ **Password strength requirements** (min 8 chars, numbers, special chars)

---

## Monitoring & Observability

### Prometheus Metrics

Metrics exposed at `/metrics` endpoint:
- HTTP request count (by method, path, status)
- Request latency (histograms)
- Error rates
- Process memory/CPU usage

**Access Prometheus:**
```bash
docker-compose up -d prometheus
# Open http://localhost:9090
```

### Grafana Dashboards

Pre-configured dashboards for:
- API performance
- Error rates
- Resource usage
- Business metrics

**Access Grafana:**
```bash
docker-compose up -d grafana
# Open http://localhost:3000 (admin/admin)
```

### Alert Rules

Configured alerts for:
- High error rate (>5% for 5min)
- High latency (P95 >2s for 5min)
- Service downtime (>2min)
- High memory usage (>1GB for 10min)
- High authentication failure rate (>5/s for 10min)

---

## Database Management

### Migrations

Run migrations:
```bash
alembic upgrade head
```

Create new migration:
```bash
alembic revision --autogenerate -m "description"
```

### Backup & Restore

**Backup:**
```bash
export DB_PASSWORD=your_password
./scripts/backup_db.sh
```

**Restore:**
```bash
./scripts/restore_db.sh /backups/postgres/backup_smartbed_20260515_233000.sql.gz
```

**Features:**
- Timestamped backups with compression
- 30-day retention policy
- Integrity verification
- Automatic cleanup

---

## Testing & Coverage

Run tests with coverage:
```bash
pytest --cov=. --cov-report=html --cov-report=term
```

View HTML coverage report:
```bash
open htmlcov/index.html
```

**Coverage threshold:** 70% (configured in `.coveragerc`)

---

## Production Deployment Checklist

Before deploying to production:

### Security
- [ ] Generate strong `SECRET_KEY` (not default value)
- [ ] Set `DANAH_ENV=production`
- [ ] Configure `WEB_ALLOWED_ORIGINS` (no wildcards)
- [ ] Ensure all origins use HTTPS
- [ ] Set strong `GRAFANA_ADMIN_PASSWORD`
- [ ] Configure database credentials securely

### Database
- [ ] Run all migrations: `alembic upgrade head`
- [ ] Set up automated backups (cron job)
- [ ] Test restore procedure
- [ ] Configure connection pooling

### Monitoring
- [ ] Start Prometheus and Grafana services
- [ ] Configure alert notifications (email/Slack)
- [ ] Set up log aggregation
- [ ] Configure retention policies

### Performance
- [ ] Set appropriate `GUNICORN_WORKERS` (2-4× CPU cores)
- [ ] Configure Redis connection limits
- [ ] Set up CDN for static assets
- [ ] Enable HTTP/2 and compression

### Documentation
- [ ] Document runbook for common issues
- [ ] Document disaster recovery procedures
- [ ] Document scaling procedures
- [ ] Update API documentation
