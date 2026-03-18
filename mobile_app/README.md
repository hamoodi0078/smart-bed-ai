# Smart Bed Mobile (Flutter)

Customer-facing Flutter app for the Smart Bed runtime.

## Active UI Track
- `lib/src/` is the only active and supported mobile UI track.
- Legacy prototypes under `lib/screens`, `lib/services`, `lib/theme`, and `lib/widgets` are excluded from analyzer and should not be used for new work.

## Requirements
- Flutter `3.41.4` (stable)
- Dart SDK matching project constraints

## Local Development
```powershell
cd mobile_app
flutter pub get
flutter analyze
flutter test
flutter run --dart-define=SMART_BED_API_BASE_URL=http://10.0.2.2:8001
```

## VS Code Run and Debug (Windows Desktop)
Use VS Code with the `Flutter` and `Dart` extensions and open this folder directly:
- `C:\Users\PC#####\Desktop\smart bed by me\mobile_app`

### One-time setup
```powershell
cd mobile_app
flutter pub get
```

### Start backend API (repo root terminal)
```powershell
.\scripts\start_backend.ps1
```

### Run from top-bar Run and Debug
- Select device: `Windows (desktop)`
- Press `F5` (or top-bar `Run and Debug`)
- Launch profile is preconfigured in `mobile_app/.vscode/launch.json`:

```json
{
  "name": "Flutter Windows (Smart Bed)",
  "request": "launch",
  "type": "dart",
  "program": "lib/main.dart",
  "deviceId": "windows",
  "toolArgs": [
    "--dart-define=SMART_BED_API_BASE_URL=http://127.0.0.1:8001"
  ]
}
```

## API Base URL Notes
- Android emulator: `http://10.0.2.2:8001`
- iOS simulator: `http://127.0.0.1:8001`
- Physical device/staging: set your reachable HTTPS backend via `SMART_BED_API_BASE_URL`

## Build
```powershell
flutter build apk --release
flutter build ipa
```
