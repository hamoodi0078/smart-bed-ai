Set-Location "C:\Users\PC#####\Desktop\smart bed by me"
$env:WEB_ALLOWED_ORIGINS = "https://app.danaabuhalifa.com,https://admin.danaabuhalifa.com"
python -m uvicorn web_server:app --host 127.0.0.1 --port 8001