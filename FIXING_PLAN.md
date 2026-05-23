# Smart Bed AI - Production Readiness Fixing Plan

**Current Completion: ~75%**  
**Target: v1.0 Production-Ready**  
**Estimated Timeline: 6-10 weeks**

---

## Executive Summary

This plan addresses critical gaps identified in the project review, prioritized by impact on production readiness. The focus is on **security**, **stability**, **observability**, and **documentation**.

---

## Sprint 1: Security & Authentication (CRITICAL - 2 weeks)

**Priority: P0 - Blocking Production Release**

### SEC-1: JWT Authentication Middleware
**Status:** Pending  
**Estimated Time:** 3 days  
**Files to Create/Modify:**
- `auth/middleware.py` - Create JWT verification middleware
- `api/dependencies.py` - Add `get_current_user()` dependency
- `api/app_factory.py` - Register auth middleware globally

**Implementation:**
```python
# auth/middleware.py
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import verify_access_token

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    return payload
```

**Routes to Protect:**
- All `/api/profile/*` endpoints
- All `/api/goals/*` endpoints
- All `/api/sleep/*` endpoints
- All `/api/admin/*` endpoints
- `/api/voice/process` endpoint
- Mobile app endpoints

**Testing:**
- [ ] Unit tests for JWT encoding/decoding
- [ ] Integration tests for protected routes (401 without token)
- [ ] Integration tests for valid token access

---

### SEC-2: User Registration & Login
**Status:** Pending  
**Estimated Time:** 2 days  
**Files to Create/Modify:**
- `api/routers/auth.py` - New router for auth endpoints
- `database/models.py` - Add User model if missing
- `alembic/versions/xxx_add_users_table.py` - Migration

**Endpoints to Create:**
```
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me
```

**Security Requirements:**
- bcrypt password hashing (already in requirements.txt)
- Email validation
- Password strength validation (min 8 chars, numbers, special chars)
- Rate limiting on login endpoint (max 5 attempts/minute)

**Testing:**
- [ ] Registration with valid/invalid data
- [ ] Login with correct/incorrect credentials
- [ ] Password hashing verification
- [ ] Rate limiting on brute force attempts

---

### SEC-3: Refresh Token Flow
**Status:** Pending  
**Estimated Time:** 2 days  
**Files to Modify:**
- `auth/jwt_handler.py` - Add refresh token generation
- `database/models.py` - Add refresh_tokens table
- `api/routers/auth.py` - Add refresh endpoint

**Implementation:**
- Access token: 15-minute expiry
- Refresh token: 7-day expiry
- Store refresh tokens in database (not just in-memory)
- Token rotation on refresh (old refresh token invalidated)
- Blacklist mechanism for logout

**Testing:**
- [ ] Access token expires after timeout
- [ ] Refresh token successfully generates new access token
- [ ] Old refresh token cannot be reused
- [ ] Logout invalidates all tokens

---

### SEC-4: Role-Based Access Control (RBAC)
**Status:** Pending  
**Estimated Time:** 2 days  
**Files to Modify:**
- `database/models.py` - Add role field to User model
- `auth/middleware.py` - Add role checking decorators
- `api/routers/admin.py` - Protect admin routes

**Roles:**
- `user` - Regular user (default)
- `admin` - Administrator (full access)
- `guest` - Guest mode (read-only, limited features)

**Implementation:**
```python
def require_role(*allowed_roles):
    async def role_checker(current_user = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

# Usage:
@router.get("/admin/users", dependencies=[Depends(require_role("admin"))])
```

**Testing:**
- [ ] Regular user cannot access admin routes (403)
- [ ] Admin can access all routes
- [ ] Guest user has read-only access

---

### SEC-5: Security Hardening
**Status:** Pending  
**Estimated Time:** 1 day  
**Files to Modify:**
- `.env.example` - Remove any hardcoded secrets
- `config/production.py` - Restrict CORS origins
- `api/app_factory.py` - Add security headers middleware

**Tasks:**
- [ ] Audit all files for hardcoded secrets (`grep -r "change-me"`)
- [ ] Update CORS to only allow specific origins (not `*`)
- [ ] Add security headers (HSTS, X-Frame-Options, CSP)
- [ ] Enable HTTPS redirect in production
- [ ] Add rate limiting to all public endpoints
- [ ] Review and fix any SQL injection risks

**Security Headers:**
```python
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

---

## Sprint 2: Database & Migrations (1 week)

### DB-1: Schema Audit & Migration
**Status:** Pending  
**Estimated Time:** 2 days

**Tasks:**
- [ ] Review all models in `database/models.py`
- [ ] Generate comprehensive migration from current state
- [ ] Verify all foreign keys and indexes
- [ ] Add missing tables (if any)
- [ ] Test migration on fresh database

**Command:**
```bash
alembic revision --autogenerate -m "comprehensive_schema_v1"
alembic upgrade head
```

---

### DB-2: User Authentication Table
**Status:** Pending  
**Estimated Time:** 1 day

**Schema:**
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);

CREATE TABLE refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(500) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
```

---

### DB-3: Backup & Restore
**Status:** Pending  
**Estimated Time:** 2 days

**Files to Create:**
- `scripts/backup_db.sh` - Automated backup script
- `scripts/restore_db.sh` - Restore from backup
- `docs/DATABASE_BACKUP.md` - Backup documentation

**Backup Script:**
```bash
#!/bin/bash
BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -h localhost -U postgres smart_bed_db > "$BACKUP_DIR/backup_$DATE.sql"
gzip "$BACKUP_DIR/backup_$DATE.sql"
# Keep only last 30 days of backups
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete
```

**Tasks:**
- [ ] Create backup script with rotation
- [ ] Test restore on clean database
- [ ] Add backup to docker-compose (volume mount)
- [ ] Schedule daily backups (cron or Docker healthcheck)
- [ ] Document backup/restore procedures

---

## Sprint 3: Testing & Quality (1-2 weeks)

### TEST-1: Coverage Measurement
**Status:** Pending  
**Estimated Time:** 1 day

**Setup:**
```bash
pip install pytest-cov
pytest --cov=. --cov-report=html --cov-report=term
```

**Files to Create:**
- `.coveragerc` - Coverage configuration
- `tests/coverage_requirements.txt` - Minimum coverage targets

**Coverage Targets:**
- Overall: 70%+
- Critical modules (auth, api, database): 85%+
- AI modules: 60%+ (harder to test)

---

### TEST-2: Voice Pipeline Integration Tests
**Status:** Pending  
**Estimated Time:** 3 days

**Files to Create:**
- `tests/integration/test_voice_e2e.py`
- `tests/integration/test_circuit_breaker.py`
- `tests/integration/test_intent_recognition.py`

**Test Scenarios:**
- [ ] Full voice flow: wake word → STT → intent → response → TTS
- [ ] Circuit breaker triggers on repeated failures
- [ ] Circuit breaker recovers after cooldown
- [ ] Offline fallback when API is down
- [ ] Barge-in during TTS playback
- [ ] Multiple intents in sequence

---

### TEST-3: API Integration Tests with Auth
**Status:** Pending  
**Estimated Time:** 2 days

**Files to Create:**
- `tests/integration/test_auth_flow.py`
- `tests/integration/test_protected_endpoints.py`

**Test Scenarios:**
- [ ] Register → Login → Access protected route
- [ ] Access protected route without token (401)
- [ ] Access protected route with expired token (401)
- [ ] Access admin route as regular user (403)
- [ ] Refresh token flow
- [ ] Logout invalidates tokens

---

## Sprint 4: Configuration & Documentation (1 week)

### CONFIG-1: Comprehensive .env.example
**Status:** Pending  
**Estimated Time:** 1 day

**File to Create:**
- `.env.example` - Full example with comments

**Required Variables (by category):**

**Database:**
```
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/smart_bed_db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

**Redis:**
```
# Redis Configuration
REDIS_URL=redis://localhost:6379/0
```

**AI/LLM:**
```
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-4

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-3-sonnet-20240229
```

**Voice:**
```
# Deepgram STT/TTS
DEEPGRAM_API_KEY=...
DEEPGRAM_TTS_API_KEY=...
STT_REQUIRE_API_STREAM=true
```

**External Services:**
```
# Weather API
WEATHER_API_KEY=...

# Fitbit
FITBIT_CLIENT_ID=...
FITBIT_CLIENT_SECRET=...

# SendGrid Email
SENDGRID_API_KEY=...
SENDGRID_FROM_EMAIL=noreply@smartbed.ai
```

**Security:**
```
# JWT
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
ALLOWED_ORIGINS=http://localhost:3000,https://app.smartbed.ai
```

**Hardware (Raspberry Pi):**
```
# Sensors
SENSOR_PRESSURE_ENABLED=true
SENSOR_MOTION_ENABLED=true
SENSOR_PRESSURE_PIN=17
SENSOR_MOTION_PIN=27

# LED Strip
LED_STRIP_ENABLED=true
LED_STRIP_PIN=18
LED_STRIP_COUNT=60
```

---

### CONFIG-2: Configuration Documentation
**Status:** Pending  
**Estimated Time:** 1 day

**File to Create:**
- `docs/CONFIGURATION.md`

**Content:**
- Description of each environment variable
- Required vs optional variables
- Default values
- Security considerations
- Environment-specific configs (dev vs prod)

---

### DOCS-1: Comprehensive README
**Status:** Pending  
**Estimated Time:** 1 day

**File to Update:**
- `README.md`

**Required Sections:**
```markdown
# Danah Smart Bed AI

## Overview
[Brief description of the project]

## Features
- Voice Assistant with wake word detection
- Sleep tracking and analytics
- Islamic mode (prayer times, Quran)
- Goal management and coaching
- Partner mode
- LED environment control
- Mobile app integration

## Tech Stack
- **Backend:** FastAPI, Python 3.11+
- **Database:** PostgreSQL with pgvector
- **Cache/Queue:** Redis, ARQ
- **AI:** OpenAI GPT-4, Anthropic Claude
- **Voice:** Deepgram STT/TTS
- **Mobile:** Flutter
- **Deployment:** Docker, Docker Compose

## Quick Start
[Installation and setup instructions]

## Documentation
- [API Documentation](docs/API.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [Developer Setup](docs/DEVELOPER_SETUP.md)
- [Hardware Setup](docs/HARDWARE_SETUP.md)

## License
[License information]
```

---

### DOCS-2: Developer Setup Guide
**Status:** Pending  
**Estimated Time:** 1 day

**File to Create:**
- `docs/DEVELOPER_SETUP.md`

**Content:**
1. Prerequisites (Python 3.11+, PostgreSQL, Redis, Docker)
2. Local development setup
3. Database migrations
4. Running tests
5. Code style and linting
6. Git workflow
7. Troubleshooting common issues

---

### DOCS-3: API Documentation
**Status:** Pending  
**Estimated Time:** 2 days

**Tasks:**
- [ ] Review all API routes in Swagger UI (`/docs`)
- [ ] Add descriptions to all endpoints
- [ ] Add request/response examples
- [ ] Document authentication requirements
- [ ] Create `docs/API.md` with endpoint reference

**Example:**
```python
@router.post(
    "/goals",
    response_model=GoalResponse,
    summary="Create a new goal",
    description="Creates a SMART goal with tracking and reminders",
    tags=["Goals"]
)
async def create_goal(
    goal: GoalCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new goal for the authenticated user.
    
    **Required fields:**
    - title: Goal title (max 100 chars)
    - category: One of [health, work, personal, sleep]
    - deadline: ISO 8601 date
    
    **Returns:**
    - Goal object with generated ID
    """
```

---

### DOCS-4: Hardware Setup Guide
**Status:** Pending  
**Estimated Time:** 1 day

**File to Create:**
- `docs/HARDWARE_SETUP.md`

**Content:**
1. Raspberry Pi requirements (model, OS version)
2. GPIO pin configuration
3. LED strip wiring diagram
4. Pressure sensor setup
5. Motion sensor setup
6. Audio setup (speakers, microphone)
7. Troubleshooting hardware issues

---

## Sprint 5: DevOps & Monitoring (1-2 weeks)

### DEVOPS-1: Prometheus & Grafana
**Status:** Pending  
**Estimated Time:** 2 days

**File to Modify:**
- `docker-compose.yml`

**Services to Add:**
```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  ports:
    - "9090:9090"
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'

grafana:
  image: grafana/grafana:latest
  volumes:
    - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
    - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    - grafana_data:/var/lib/grafana
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
  depends_on:
    - prometheus

volumes:
  prometheus_data:
  grafana_data:
```

**Files to Create:**
- `monitoring/prometheus.yml` - Prometheus config
- `monitoring/grafana/dashboards/api_metrics.json` - Grafana dashboard

---

### DEVOPS-2: Grafana Dashboards
**Status:** Pending  
**Estimated Time:** 2 days

**Dashboards to Create:**
1. **API Performance**
   - Request rate (requests/second)
   - Average latency (p50, p95, p99)
   - Error rate (4xx, 5xx)
   - Top slowest endpoints

2. **System Health**
   - CPU usage
   - Memory usage
   - Database connection pool
   - Redis connection count

3. **Voice Pipeline**
   - STT success rate
   - TTS generation time
   - Intent recognition accuracy
   - Circuit breaker state

4. **Business Metrics**
   - Active users
   - Voice interactions per hour
   - Goal completion rate
   - Sleep tracking entries

---

### DEVOPS-3: Alerting Rules
**Status:** Pending  
**Estimated Time:** 1 day

**File to Create:**
- `monitoring/alerting_rules.yml`

**Critical Alerts:**
```yaml
groups:
  - name: api_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High API error rate"
          
      - alert: DatabaseDown
        expr: up{job="postgres"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database is down"
          
      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis is down"
          
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API p95 latency above 2 seconds"
```

---

### DEVOPS-4: CI/CD Pipeline Enhancement
**Status:** Pending  
**Estimated Time:** 3 days

**File to Update:**
- `.github/workflows/ci.yml`

**Pipeline Stages:**

**1. Test Stage:**
```yaml
test:
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:15
      env:
        POSTGRES_PASSWORD: testpass
      options: >-
        --health-cmd pg_isready
        --health-interval 10s
    redis:
      image: redis:7
  steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    - name: Run tests with coverage
      run: |
        pytest --cov=. --cov-report=xml --cov-report=term
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

**2. Lint Stage:**
```yaml
lint:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v3
    - name: Run ruff
      run: ruff check .
    - name: Run black
      run: black --check .
    - name: Run mypy
      run: mypy .
```

**3. Build Stage:**
```yaml
build:
  runs-on: ubuntu-latest
  needs: [test, lint]
  steps:
    - uses: actions/checkout@v3
    - name: Build Docker image
      run: docker build -t smart-bed-ai:${{ github.sha }} .
    - name: Push to registry
      run: |
        echo ${{ secrets.DOCKER_PASSWORD }} | docker login -u ${{ secrets.DOCKER_USERNAME }} --password-stdin
        docker push smart-bed-ai:${{ github.sha }}
```

**4. Deploy Stage (if main branch):**
```yaml
deploy:
  runs-on: ubuntu-latest
  needs: build
  if: github.ref == 'refs/heads/main'
  steps:
    - name: Deploy to production
      run: |
        # SSH into server and pull latest image
        # Run migrations
        # Restart services
```

---

## Sprint 6: Mobile App Integration (1 week)

### MOBILE-1: API Integration Audit
**Status:** Pending  
**Estimated Time:** 2 days

**Task:**
- Review Flutter app API calls
- Create checklist of all endpoints used
- Verify all endpoints exist and work
- Document missing endpoints

**File to Create:**
- `docs/MOBILE_API_CHECKLIST.md`

---

### MOBILE-2: Push Notifications
**Status:** Pending  
**Estimated Time:** 2 days

**Verification:**
- [ ] FCM configuration correct
- [ ] Expo push notification setup complete
- [ ] Test notification on Android
- [ ] Test notification on iOS
- [ ] Notification triggers work (alarms, reminders, etc.)

**Files to Review:**
- `notifications/fcm_sender.py`
- `notifications/expo_sender.py`
- Mobile app notification handler

---

### MOBILE-3: QR Code Pairing
**Status:** Pending  
**Estimated Time:** 1 day

**End-to-End Test:**
- [ ] Generate QR code from backend
- [ ] Scan QR code from mobile app
- [ ] Device successfully pairs
- [ ] Mobile app can access device features
- [ ] Pairing persists across app restarts

**Files to Review:**
- `qr_code/generate_qr.py`
- `qr_code/pair_device.py`
- `qr_code/qr_api.py`

---

## Priority Matrix

| Sprint | Priority | Impact | Effort | Start Week |
|--------|----------|--------|--------|------------|
| Sprint 1: Security | P0 | Critical | High | Week 1-2 |
| Sprint 2: Database | P1 | High | Medium | Week 3 |
| Sprint 3: Testing | P1 | High | High | Week 4-5 |
| Sprint 4: Documentation | P2 | Medium | Medium | Week 6 |
| Sprint 5: DevOps | P1 | High | High | Week 7-8 |
| Sprint 6: Mobile | P2 | Medium | Low | Week 9 |

---

## Success Criteria (v1.0 Release Checklist)

### Security ✅
- [ ] All API routes protected with JWT authentication
- [ ] User registration and login working
- [ ] Refresh token flow implemented
- [ ] RBAC enforced on admin routes
- [ ] No hardcoded secrets in codebase
- [ ] CORS restricted to specific origins
- [ ] Security headers added

### Database ✅
- [ ] All migrations applied successfully
- [ ] User authentication table created
- [ ] Backup script created and tested
- [ ] Restore script tested on clean database

### Testing ✅
- [ ] Overall test coverage ≥ 70%
- [ ] Critical module coverage ≥ 85%
- [ ] Integration tests passing
- [ ] Voice pipeline E2E tests passing

### Configuration ✅
- [ ] `.env.example` complete with all variables
- [ ] Configuration documentation written
- [ ] No secrets in version control

### Documentation ✅
- [ ] README comprehensive and up-to-date
- [ ] Developer setup guide complete
- [ ] API documentation complete
- [ ] Hardware setup guide complete

### DevOps ✅
- [ ] Prometheus and Grafana running
- [ ] Dashboards created and working
- [ ] Alerting rules configured
- [ ] CI/CD pipeline enhanced with all stages
- [ ] Automated deployments working

### Mobile ✅
- [ ] All API endpoints verified working
- [ ] Push notifications tested
- [ ] QR code pairing tested E2E

---

## Post-v1.0 Improvements (Future Sprints)

### Performance Optimization
- Database query optimization
- Redis caching strategy
- Voice pipeline latency reduction
- Mobile app performance tuning

### Advanced Features
- Multi-user household support
- Voice biometric authentication
- Advanced sleep analytics (sleep stages via ML)
- Integration with smart home devices (Philips Hue, etc.)

### Scalability
- Kubernetes deployment manifests
- Horizontal scaling for API
- Database read replicas
- CDN for static assets

---

## Getting Started with the Fixing Plan

**Recommended Order:**
1. Start with **Sprint 1 (Security)** - blocking issue for production
2. Run **TEST-1 (Coverage)** early to establish baseline
3. Work on **DB-1** and **CONFIG-1** in parallel with security
4. Document as you go (don't leave docs for last)
5. Set up monitoring early to catch issues during development

**Daily Workflow:**
1. Pick highest-priority pending task
2. Create feature branch (`git checkout -b SEC-1-jwt-auth`)
3. Implement with tests
4. Run full test suite (`pytest`)
5. Update documentation
6. Create PR for review
7. Merge to main after approval

**Weekly Goals:**
- Week 1-2: Complete all SEC tasks
- Week 3: Complete DB tasks + TEST-1
- Week 4-5: Complete remaining TEST tasks
- Week 6: Complete all DOCS tasks
- Week 7-8: Complete DEVOPS tasks
- Week 9: Complete MOBILE tasks + final testing

---

**Last Updated:** 2026-05-15  
**Plan Version:** 1.0
