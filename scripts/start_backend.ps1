$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

if (-not $env:WEB_ALLOWED_ORIGINS) {
    $env:WEB_ALLOWED_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
}

# Local dev DEFAULTS to a fast on-disk sqlite. The .env DATABASE_URL points at
# Neon (us-east-1) — great for production, but every query is a trans-Atlantic
# round trip, so login/register take seconds from outside the US and the app
# times out. We set DATABASE_URL here BEFORE the app loads; config.settings uses
# load_dotenv(override=False), so this local value wins over .env.
# To test against Neon on purpose:  $env:DATABASE_URL="<neon url>"; before running.
if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = "sqlite:///./data/dev.sqlite3"
}
# No local Redis in dev — leave it empty so the rate limiter / brute-force guard
# fall back to in-memory instead of retrying a dead server on every request.
if (-not $env:REDIS_URL) {
    $env:REDIS_URL = ""
}

Write-Host "Danah backend -> DATABASE_URL=$($env:DATABASE_URL)" -ForegroundColor Cyan

# api.app_factory:app is the PRODUCTION app (same one Docker/Railway run).
# Host 0.0.0.0 so the Android emulator (10.0.2.2) or a phone on Wi-Fi can reach it.
$venvPython = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = Join-Path $repoRoot ".venv311\Scripts\python.exe"
}
if (Test-Path $venvPython) {
    & $venvPython -m uvicorn api.app_factory:app --host 0.0.0.0 --port 8000 --reload
} else {
    python -m uvicorn api.app_factory:app --host 0.0.0.0 --port 8000 --reload
}
