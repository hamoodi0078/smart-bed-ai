$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

if (-not $env:WEB_ALLOWED_ORIGINS) {
    $env:WEB_ALLOWED_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
}

$venvPython = Join-Path $repoRoot ".venv311\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m uvicorn web_server:app --host 127.0.0.1 --port 8000 --reload
} else {
    python -m uvicorn web_server:app --host 127.0.0.1 --port 8000 --reload
}
