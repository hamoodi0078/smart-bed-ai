import os
from pathlib import Path
from typing import List

import requests


class HealthCheckResult:
    def __init__(self, name: str, ok: bool, detail: str):
        self.name = name
        self.ok = ok
        self.detail = detail


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return os.access(path, os.W_OK)
    except Exception:
        return False


def run_device_health_checks(settings, spotify, local_music, tts_player=None, led=None, sensor_monitor=None) -> List[HealthCheckResult]:
    results: List[HealthCheckResult] = []

    results.append(
        HealthCheckResult(
            "DEEPGRAM_API_KEY",
            bool(settings.deepgram_api_key),
            "Configured" if settings.deepgram_api_key else "Missing DEEPGRAM_API_KEY",
        )
    )

    results.append(
        HealthCheckResult(
            "SPOTIFY_CONFIG",
            spotify.is_configured(),
            "Spotify token configured" if spotify.is_configured() else "Spotify token not configured",
        )
    )

    results.append(
        HealthCheckResult(
            "LOCAL_MUSIC",
            local_music.is_ready(),
            "Local music player ready" if local_music.is_ready() else "Install pygame for local music",
        )
    )

    if tts_player is not None:
        ready = bool(tts_player.is_ready())
        results.append(
            HealthCheckResult(
                "TTS_OUTPUT",
                ready,
                "TTS playback ready" if ready else "TTS playback unavailable on this device",
            )
        )

    if bool(getattr(settings, "led_hw_enabled", False)) and led is not None:
        ready = bool(getattr(led, "hardware_ready", lambda: False)())
        detail = getattr(led, "hardware_status", lambda: "LED hardware status unavailable.")()
        results.append(
            HealthCheckResult(
                "LED_HARDWARE",
                ready,
                detail,
            )
        )

    if (
        bool(getattr(settings, "sensor_pressure_enabled", False))
        or bool(getattr(settings, "sensor_motion_enabled", False))
    ) and sensor_monitor is not None:
        ready = bool(getattr(sensor_monitor, "is_available", lambda: False)())
        detail = getattr(sensor_monitor, "status_line", lambda: "Sensor monitor status unavailable.")()
        results.append(
            HealthCheckResult(
                "SENSOR_INPUTS",
                ready,
                detail,
            )
        )

    data_writable = _is_writable_dir(Path("data"))
    results.append(
        HealthCheckResult(
            "DATA_STORAGE",
            data_writable,
            "Data storage writable" if data_writable else "Data folder is not writable",
        )
    )

    output_writable = _is_writable_dir(Path("output_audio"))
    results.append(
        HealthCheckResult(
            "OUTPUT_AUDIO",
            output_writable,
            "Output audio folder writable" if output_writable else "output_audio folder is not writable",
        )
    )

    try:
        response = requests.get("https://www.google.com", timeout=5)
        internet_ok = response.status_code < 500
    except Exception:
        internet_ok = False

    results.append(
        HealthCheckResult(
            "INTERNET",
            internet_ok,
            "Internet reachable" if internet_ok else "No internet access",
        )
    )

    return results


def format_health_report(results: List[HealthCheckResult]) -> str:
    total = len(results)
    ok_count = len([r for r in results if r.ok])
    lines = []
    for result in results:
        icon = "OK" if result.ok else "WARN"
        lines.append(f"[{icon}] {result.name}: {result.detail}")
    return f"Health summary {ok_count}/{total} checks passed. " + " | ".join(lines)
