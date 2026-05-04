"""System health monitoring and auto-recovery for Smart Bed AI runtime.

Monitors API latency, memory, disk, CPU temperature, sensor connectivity,
and service health. Triggers auto-recovery actions when thresholds are exceeded.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("core.health_monitor")

_CHECK_INTERVAL_SECONDS = 300  # 5 minutes default


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_memory_usage_mb() -> float:
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except Exception:
        return -1.0


def _get_cpu_percent() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=1)
    except Exception:
        return -1.0


def _get_disk_free_mb(path: str = ".") -> float:
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024 * 1024)
    except Exception:
        return -1.0


def _get_cpu_temperature() -> float:
    """Read CPU temperature on Raspberry Pi. Returns -1 if unavailable."""
    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal_path.exists():
        try:
            raw = thermal_path.read_text().strip()
            return float(raw) / 1000.0
        except Exception:
            pass
    return -1.0


class HealthCheck:
    """Single health check result."""

    def __init__(self, name: str, status: str, value: Any = None, message: str = ""):
        self.name = name
        self.status = status  # "ok", "warning", "critical"
        self.value = value
        self.message = message
        self.checked_at = _utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "value": self.value,
            "message": self.message,
            "checked_at": self.checked_at,
        }


class HealthMonitor:
    """Monitors system health and triggers auto-recovery when needed."""

    def __init__(
        self,
        *,
        runtime_data_dir: Path,
        memory_warning_mb: float = 500.0,
        memory_critical_mb: float = 800.0,
        disk_warning_mb: float = 1000.0,
        disk_critical_mb: float = 500.0,
        cpu_temp_warning: float = 65.0,
        cpu_temp_critical: float = 75.0,
        api_latency_warning_ms: float = 2000.0,
        api_latency_critical_ms: float = 5000.0,
        check_interval_seconds: int = _CHECK_INTERVAL_SECONDS,
    ):
        self._runtime_data_dir = Path(runtime_data_dir).resolve()
        self._thresholds = {
            "memory_warning_mb": float(memory_warning_mb),
            "memory_critical_mb": float(memory_critical_mb),
            "disk_warning_mb": float(disk_warning_mb),
            "disk_critical_mb": float(disk_critical_mb),
            "cpu_temp_warning": float(cpu_temp_warning),
            "cpu_temp_critical": float(cpu_temp_critical),
            "api_latency_warning_ms": float(api_latency_warning_ms),
            "api_latency_critical_ms": float(api_latency_critical_ms),
        }
        self._check_interval = max(30, int(check_interval_seconds))
        self._state_path = self._runtime_data_dir / "health_state.json"
        self._alert_callbacks: list[Callable[[HealthCheck], None]] = []
        self._recovery_actions: dict[str, Callable[[], bool]] = {}
        self._api_latencies: list[float] = []
        self._last_results: list[HealthCheck] = []
        self._recovery_log: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._consecutive_failures: dict[str, int] = {}
        self._max_recovery_retries = 3

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def register_alert_callback(self, callback: Callable[[HealthCheck], None]) -> None:
        if callable(callback):
            self._alert_callbacks.append(callback)

    def register_recovery_action(self, check_name: str, action: Callable[[], bool]) -> None:
        if callable(action):
            self._recovery_actions[str(check_name)] = action

    def record_api_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._api_latencies.append(float(latency_ms))
            self._api_latencies = self._api_latencies[-200:]

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def check_memory(self) -> HealthCheck:
        usage = _get_memory_usage_mb()
        if usage < 0:
            return HealthCheck("memory", "ok", value=usage, message="Cannot read memory usage")
        if usage >= self._thresholds["memory_critical_mb"]:
            return HealthCheck("memory", "critical", value=round(usage, 1),
                               message=f"Memory usage {usage:.0f}MB exceeds critical threshold")
        if usage >= self._thresholds["memory_warning_mb"]:
            return HealthCheck("memory", "warning", value=round(usage, 1),
                               message=f"Memory usage {usage:.0f}MB exceeds warning threshold")
        return HealthCheck("memory", "ok", value=round(usage, 1))

    def check_disk(self) -> HealthCheck:
        free = _get_disk_free_mb(str(self._runtime_data_dir))
        if free < 0:
            return HealthCheck("disk", "ok", value=free, message="Cannot read disk usage")
        if free <= self._thresholds["disk_critical_mb"]:
            return HealthCheck("disk", "critical", value=round(free, 1),
                               message=f"Disk free {free:.0f}MB below critical threshold")
        if free <= self._thresholds["disk_warning_mb"]:
            return HealthCheck("disk", "warning", value=round(free, 1),
                               message=f"Disk free {free:.0f}MB below warning threshold")
        return HealthCheck("disk", "ok", value=round(free, 1))

    def check_cpu_temperature(self) -> HealthCheck:
        temp = _get_cpu_temperature()
        if temp < 0:
            return HealthCheck("cpu_temperature", "ok", value=temp, message="Temperature sensor not available")
        if temp >= self._thresholds["cpu_temp_critical"]:
            return HealthCheck("cpu_temperature", "critical", value=round(temp, 1),
                               message=f"CPU temperature {temp:.1f}°C exceeds critical threshold")
        if temp >= self._thresholds["cpu_temp_warning"]:
            return HealthCheck("cpu_temperature", "warning", value=round(temp, 1),
                               message=f"CPU temperature {temp:.1f}°C exceeds warning threshold")
        return HealthCheck("cpu_temperature", "ok", value=round(temp, 1))

    def check_api_latency(self) -> HealthCheck:
        with self._lock:
            recent = list(self._api_latencies[-50:])
        if not recent:
            return HealthCheck("api_latency", "ok", value=0, message="No latency data recorded")
        avg = sum(recent) / len(recent)
        if avg >= self._thresholds["api_latency_critical_ms"]:
            return HealthCheck("api_latency", "critical", value=round(avg, 1),
                               message=f"Average API latency {avg:.0f}ms exceeds critical threshold")
        if avg >= self._thresholds["api_latency_warning_ms"]:
            return HealthCheck("api_latency", "warning", value=round(avg, 1),
                               message=f"Average API latency {avg:.0f}ms exceeds warning threshold")
        return HealthCheck("api_latency", "ok", value=round(avg, 1))

    def check_pressure_sensor(self, sensor_available: bool = False) -> HealthCheck:
        if sensor_available:
            return HealthCheck("pressure_sensor", "ok", value=True)
        return HealthCheck("pressure_sensor", "warning", value=False,
                           message="Pressure sensor not connected or not responding")

    def check_runtime_data_integrity(self) -> HealthCheck:
        critical_files = ["user_profile.json", "automations_state.json"]
        missing: list[str] = []
        corrupt: list[str] = []
        for fname in critical_files:
            fpath = self._runtime_data_dir / fname
            if not fpath.exists():
                missing.append(fname)
                continue
            try:
                raw = fpath.read_text(encoding="utf-8").strip()
                if raw:
                    json.loads(raw)
            except json.JSONDecodeError:
                corrupt.append(fname)
            except OSError:
                missing.append(fname)

        if corrupt:
            return HealthCheck("data_integrity", "critical", value={"corrupt": corrupt},
                               message=f"Corrupt data files: {', '.join(corrupt)}")
        if missing:
            return HealthCheck("data_integrity", "warning", value={"missing": missing},
                               message=f"Missing data files: {', '.join(missing)}")
        return HealthCheck("data_integrity", "ok")

    # ------------------------------------------------------------------
    # Full health check run
    # ------------------------------------------------------------------

    def run_all_checks(self, sensor_available: bool = False) -> list[dict[str, Any]]:
        checks = [
            self.check_memory(),
            self.check_disk(),
            self.check_cpu_temperature(),
            self.check_api_latency(),
            self.check_pressure_sensor(sensor_available),
            self.check_runtime_data_integrity(),
        ]
        self._last_results = checks

        for check in checks:
            if check.status in ("warning", "critical"):
                self._fire_alert(check)
                if check.status == "critical":
                    self._attempt_recovery(check)

        self._save_state(checks)
        return [c.to_dict() for c in checks]

    def get_last_results(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._last_results]

    def get_health_summary(self) -> dict[str, Any]:
        if not self._last_results:
            return {"status": "unknown", "message": "No health checks have been run yet."}

        statuses = [c.status for c in self._last_results]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "checks_count": len(self._last_results),
            "critical_count": statuses.count("critical"),
            "warning_count": statuses.count("warning"),
            "ok_count": statuses.count("ok"),
            "last_checked": self._last_results[0].checked_at if self._last_results else "",
            "recovery_actions_taken": len(self._recovery_log),
        }

    # ------------------------------------------------------------------
    # Background scheduler
    # ------------------------------------------------------------------

    def start(self, sensor_available_fn: Callable[[], bool] | None = None) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            args=(sensor_available_fn,),
            daemon=True,
            name="health_monitor",
        )
        self._thread.start()
        logger.info("Health monitor started (interval=%ds)", self._check_interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def _monitor_loop(self, sensor_fn: Callable[[], bool] | None) -> None:
        while not self._stop_event.is_set():
            try:
                sensor_ok = sensor_fn() if callable(sensor_fn) else False
                self.run_all_checks(sensor_available=sensor_ok)
            except Exception as exc:
                logger.error("Health monitor check error: %s", exc)
            self._stop_event.wait(timeout=self._check_interval)

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def _attempt_recovery(self, check: HealthCheck) -> None:
        name = check.name
        count = self._consecutive_failures.get(name, 0) + 1
        self._consecutive_failures[name] = count

        if count > self._max_recovery_retries:
            logger.warning("Recovery skipped for %s: max retries (%d) exceeded", name, self._max_recovery_retries)
            return

        action = self._recovery_actions.get(name)
        if not callable(action):
            return

        try:
            success = action()
            entry = {
                "check": name,
                "attempt": count,
                "success": bool(success),
                "timestamp": _utcnow().isoformat(),
            }
            self._recovery_log.append(entry)
            self._recovery_log = self._recovery_log[-50:]

            if success:
                self._consecutive_failures[name] = 0
                logger.info("Recovery succeeded for %s on attempt %d", name, count)
            else:
                logger.warning("Recovery failed for %s on attempt %d", name, count)
        except Exception as exc:
            logger.error("Recovery action crashed for %s: %s", name, exc)

    def _fire_alert(self, check: HealthCheck) -> None:
        for callback in self._alert_callbacks:
            try:
                callback(check)
            except Exception as exc:
                logger.error("Alert callback error: %s", exc)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self, checks: list[HealthCheck]) -> None:
        state = {
            "last_check_at": _utcnow().isoformat(),
            "checks": [c.to_dict() for c in checks],
            "recovery_log": self._recovery_log[-20:],
            "consecutive_failures": dict(self._consecutive_failures),
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error("Failed to save health state: %s", exc)

    def get_recovery_log(self) -> list[dict[str, Any]]:
        return list(self._recovery_log)
