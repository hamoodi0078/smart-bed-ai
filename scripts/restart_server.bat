@echo off
setlocal

REM Project root
set "ROOT=C:\Users\PC#####\Desktop\smart bed by me"

REM Kill old python web server processes (safe for local dev)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
  taskkill /PID %%a /F >nul 2>&1
)

cd /d "%ROOT%"
start "SmartBedServer" cmd /k "set WEB_ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000 && python -m uvicorn web_server:app --host 127.0.0.1 --port 8000 --reload"

endlocal