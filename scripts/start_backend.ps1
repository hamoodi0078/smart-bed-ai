$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

if (-not $env:WEB_ALLOWED_ORIGINS) {
    $env:WEB_ALLOWED_ORIGINS = "http://127.0.0.1:8001,http://localhost:8001"
}

$venvPython = Join-Path $repoRoot ".venv311\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m uvicorn web_server:app --host 127.0.0.1 --port 8001
} else {
    python -m uvicorn web_server:app --host 127.0.0.1 --port 8001
}
