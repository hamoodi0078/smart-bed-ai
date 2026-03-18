# Raspberry Pi 5 Backend-Only Transfer Guide

This guide is for the runtime deployment model where:
- Raspberry Pi runs the bed runtime + backend API
- Flutter mobile app stays on your development/build machine

## 1) Recommended transfer strategy: git clone/pull

On Raspberry Pi:

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv portaudio19-dev libatlas-base-dev
cd /home/pi
git clone <your-repo-url> smart-bed
cd smart-bed
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pygame
```

For future updates:

```bash
cd /home/pi/smart-bed
git pull
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Required files and folders on Pi (and why)

- `.env`: secrets, hardware pins, API URLs, runtime switches.
- `.env.example`: template reference when rotating/rebuilding `.env`.
- `requirements.txt`: Python dependency source.
- `main.py`, `app_entry.py`: bed runtime startup and orchestration.
- `web_server.py`: FastAPI endpoints for mobile/admin/runtime bridge.
- `config.py`: shared env loading and runtime path config.
- `time_utils.py`, `automation_engine.py`, `led_controller.py`, `prayer_handler.py`, `scene_manager.py`, `voice_handler.py`: runtime helper modules imported by entry points.
- `ai/`: conversation/STT/TTS/safety/sleep/Spotify modules used by runtime/API.
- `Storage/`: persistence layer (subscription store, schedules, profile/cache IO).
- `automations/`, `commands/`, `core/`: automation registry, command handlers, core types/errors/logging.
- `subscriptions/`, `database/`, `scenes/`, `islamic_mode/`, `led/`: API billing/auth repos, scene store, Islamic features, LED hardware support.
- `web/`: static login/admin pages and assets served by backend routes.
- `runtime_data/`: runtime JSON state files and operational memory.
- `data/`: persistent app data such as sleep history and scene artifacts.

## 3) Folders not required for backend-only Pi runtime

- `mobile_app/` (Flutter source for phone/desktop builds)
- `tests/`
- `.venv*`, `.pytest_cache`, `.tmp`
- build artifacts (`build/`, `mobile_app/build/`)
- local development documents and notes under `docs/` (optional)

## 4) Environment setup on Pi

```bash
cd /home/pi/smart-bed
cp .env.example .env
```

Edit `.env` and set at minimum:
- `DEEPGRAM_API_KEY`
- `APP_BACKEND_BASE_URL` (if using external cloud backend bridge)
- `BED_DEVICE_ID`
- `BED_FIRMWARE_VERSION`
- `USER_STRIP_PIN`, `STATE_STRIP_PIN` (if using LED strips)
- any Spotify/PayPal/OpenAI keys required by your enabled features

## 5) Smoke start commands

Backend API:

```bash
cd /home/pi/smart-bed
source .venv/bin/activate
python3 -m uvicorn web_server:app --host 0.0.0.0 --port 8000
```

Bed runtime:

```bash
cd /home/pi/smart-bed
source .venv/bin/activate
python3 main.py
```

Health check:

```bash
curl http://127.0.0.1:8000/healthz
```

## 6) Optional production boot setup

Use the `systemd` service templates in `DEPLOYMENT_CHECKLIST.md` to auto-start:
- Smart Bed runtime service
- Smart Bed backend API service
