$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

if (-not $env:WEB_ALLOWED_ORIGINS) {
    $env:WEB_ALLOWED_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
}

# api.app_factory:app is the PRODUCTION app (same one Docker/Railway run).
# web_server:app is the legacy dialect — do not serve it; the mobile app's
# contracts (alarms, admin, profile) are only correct on app_factory.
# Host 0.0.0.0 so a phone on the same Wi-Fi (or adb reverse) can connect.
$venvPython = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = Join-Path $repoRoot ".venv311\Scripts\python.exe"
}
if (Test-Path $venvPython) {
    & $venvPython -m uvicorn api.app_factory:app --host 0.0.0.0 --port 8000 --reload
} else {
    python -m uvicorn api.app_factory:app --host 0.0.0.0 --port 8000 --reload
}
