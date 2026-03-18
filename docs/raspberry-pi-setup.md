# Raspberry Pi 5 Setup

Use the Pi as the backend and hardware host, and keep the Flutter app on a phone or tablet.

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev portaudio19-dev libatlas-base-dev bluez
```

If you are driving WS2812 LEDs, enable the required Raspberry Pi interfaces and install the `rpi_ws281x` kernel support expected by the library.

## 2. Copy the repo and install Python packages

```bash
git clone <your-repo-url> /opt/smart-bed
cd /opt/smart-bed
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pi.txt
```

## 3. Configure `.env`

Minimum Pi-specific changes:

```dotenv
WAKE_WORD_MODE=voice
APP_BASE_URL=http://<pi-ip>:8001
APP_BACKEND_BASE_URL=http://<pi-ip>:8001
LED_HARDWARE_ENABLED=1
USER_STRIP_PIN=18
STATE_STRIP_PIN=13
SENSOR_PRESSURE_ENABLED=1
SENSOR_PRESSURE_PIN=23
SENSOR_MOTION_ENABLED=1
SENSOR_MOTION_PIN=24
```

Adjust the GPIO pins and active-low flags for your actual wiring.

## 4. Run manually

Voice runtime:

```bash
python main.py
```

Web/mobile API:

```bash
python -m uvicorn web_server:app --host 0.0.0.0 --port 8001
```

## 5. Phone app connection

Do not change the Flutter source for Pi deployment. Launch the phone app with:

```bash
flutter run --dart-define=SMART_BED_API_BASE_URL=http://<pi-ip>:8001
```

## 6. Optional systemd services

Service templates are in `scripts/systemd/`. Copy them into `/etc/systemd/system/`, adjust the working directory if needed, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable smart-bed-runtime.service
sudo systemctl enable smart-bed-api.service
sudo systemctl start smart-bed-runtime.service
sudo systemctl start smart-bed-api.service
```
