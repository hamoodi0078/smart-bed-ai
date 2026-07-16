"""BedCommandPoller — the Pi side of the app→cloud→bed command bridge (Plan 6).

A daemon thread that short-polls GET /v1/device/sync (~2.5s), executes
commands on the real hardware through a handler map, reconciles the backend's
desired state (lighting, alarms, scene) onto the shared LEDController /
ScheduleManager, and reports real results back. Runs inside app_entry.py so
one process owns the SPI LED bus.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from loguru import logger

from Storage.schedule_manager import is_valid_time_24h

ALARM_LABEL_PREFIX = "[app]"

# Scene key -> LED parameters. Brightness values mirror the backend's
# _scene_catalog; color/animation realize each scene's description on strip.
SCENE_LED_MAP: dict[str, dict[str, Any]] = {
    "calm_recovery": {"color": "cyan", "animation": "breathing", "brightness": 0.25},
    "focus_momentum": {"color": "white", "animation": "pulse", "brightness": 0.45},
    "discipline_night": {"color": "blue", "animation": "wave", "brightness": 0.35},
    "balanced_default": {"color": "white", "animation": "solid", "brightness": 0.40},
}

HandlerResult = tuple[bool, str, dict[str, Any]]


class BedCommandPoller:
    def __init__(
        self,
        backend_client,
        led,
        schedule,
        environment_orchestrator,
        profile: dict[str, Any],
        poll_interval_seconds: float = 2.5,
    ):
        self.backend_client = backend_client
        self.led = led
        self.schedule = schedule
        self.environment_orchestrator = environment_orchestrator
        self.profile = profile
        self.poll_interval_seconds = float(poll_interval_seconds)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_state_version = ""
        self._handlers: dict[str, Callable[[dict[str, Any]], HandlerResult]] = {
            "winddown": self._handle_winddown,
            "optimize_room": self._handle_optimize_room,
            "wake_recovery": self._handle_wake_recovery,
            "reactive_lights": self._handle_reactive_lights,
            "quiet_hours_override": self._handle_quiet_hours_override,
        }

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="bed-command-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval_seconds + 2)
            self._thread = None

    def _run(self) -> None:
        logger.info("Bed command poller running (every {}s).", self.poll_interval_seconds)
        while not self._stop_event.wait(self.poll_interval_seconds):
            try:
                self._tick()
            except Exception as exc:
                logger.warning("Bed command poller tick failed: {}", exc)

    # ── one poll cycle ────────────────────────────────────────────────────

    def _tick(self) -> None:
        ok, body, message = self.backend_client.fetch_sync()
        if not ok:
            logger.debug("Device sync unavailable: {}", message)
            return
        for command in body.get("commands", []) or []:
            if isinstance(command, dict):
                self._execute_command(command)
        version = str(body.get("state_version", "") or "")
        desired = body.get("desired_state")
        if isinstance(desired, dict) and version and version != self._last_state_version:
            self._reconcile(desired)
            self._last_state_version = version

    def _execute_command(self, command: dict[str, Any]) -> None:
        command_id = str(command.get("id", "") or "")
        action = str(command.get("action", "") or "").strip().lower()
        params = command.get("params") if isinstance(command.get("params"), dict) else {}
        handler = self._handlers.get(action)
        if handler is None:
            self.backend_client.report_command_result(
                command_id, "failed", f"unsupported action: {action}", {}
            )
            return
        try:
            ok, detail, actual_state = handler(params)
        except Exception as exc:
            logger.warning("Command {} ({}) failed: {}", command_id, action, exc)
            self.backend_client.report_command_result(
                command_id, "failed", f"{type(exc).__name__}: {exc}", {}
            )
            return
        self.backend_client.report_command_result(
            command_id, "completed" if ok else "failed", detail, actual_state
        )
        logger.info("App command executed: {} -> {}", action, detail)

    # ── desired-state reconciliation ──────────────────────────────────────

    def _reconcile(self, desired: dict[str, Any]) -> None:
        try:
            self._reconcile_scene(desired.get("scene"))
        except Exception as exc:
            logger.warning("Scene reconcile failed: {}", exc)
        try:
            self._reconcile_lighting(desired.get("lighting"))
        except Exception as exc:
            logger.warning("Lighting reconcile failed: {}", exc)
        try:
            self._reconcile_alarms(desired.get("alarms"))
        except Exception as exc:
            logger.warning("Alarm reconcile failed: {}", exc)

    def _reconcile_scene(self, scene: Any) -> None:
        scene_key = str((scene or {}).get("scene_key", "") or "").strip()
        led_params = SCENE_LED_MAP.get(scene_key)
        if not led_params:
            return
        self.environment_orchestrator.apply_scene(
            self.led,
            self.profile,
            {
                "key": scene_key,
                "animation": led_params["animation"],
                "color": led_params["color"],
                "brightness": led_params["brightness"],
                "line": f"Scene applied from app: {scene_key}.",
            },
        )

    def _reconcile_lighting(self, lighting: Any) -> None:
        data = lighting if isinstance(lighting, dict) else {}
        if not data:
            return
        # Applied AFTER the scene so an explicit lights-off always wins.
        if not bool(data.get("lights_on", True)):
            self.led.set_user_brightness(0.0)
            return
        level = int(data.get("light_level", 45) or 45)
        self.led.set_user_brightness(max(0.0, min(1.0, level / 100.0)))

    def _reconcile_alarms(self, alarms: Any) -> None:
        rows = alarms if isinstance(alarms, list) else []
        for alarm in self.schedule.list_alarms():
            if str(getattr(alarm, "label", "")).startswith(ALARM_LABEL_PREFIX):
                self.schedule.remove_alarm(alarm.id)
        for row in rows:
            if not isinstance(row, dict) or not bool(row.get("enabled", True)):
                continue
            time_24h = str(row.get("time", "") or "")
            if not is_valid_time_24h(time_24h):
                continue
            days = row.get("days") if isinstance(row.get("days"), list) else []
            # App dialect Mon=1..Sun=7 -> datetime.weekday() Mon=0..Sun=6.
            repeat = ",".join(
                str(int(d) - 1) for d in days if isinstance(d, (int, float)) and 1 <= int(d) <= 7
            )
            label = str(row.get("label", "") or "").strip() or "Alarm"
            self.schedule.add_alarm(
                time_24h, label=f"{ALARM_LABEL_PREFIX} {label}", repeat_days=repeat
            )

    # ── command handlers ──────────────────────────────────────────────────

    def _apply_led(self, animation: str, color: str, brightness: float) -> dict[str, Any]:
        self.led.set_user_animation(animation)
        self.led.set_color_value(color)
        self.led.set_user_brightness(brightness)
        return {"animation": animation, "color": color, "brightness": brightness}

    def _handle_winddown(self, params: dict[str, Any]) -> HandlerResult:
        state = self._apply_led("breathing", "orange", 0.2)
        return True, "Wind-down lighting active.", state

    def _handle_optimize_room(self, params: dict[str, Any]) -> HandlerResult:
        scene_key = str(params.get("scene_key", "") or "") or "balanced_default"
        led_params = SCENE_LED_MAP.get(scene_key, SCENE_LED_MAP["balanced_default"])
        state = self._apply_led(
            led_params["animation"], led_params["color"], led_params["brightness"]
        )
        return True, f"Room optimized with scene {scene_key}.", state

    def _handle_wake_recovery(self, params: dict[str, Any]) -> HandlerResult:
        state = self._apply_led("solid", "orange", 0.1)
        return True, "Gentle night light active for wake recovery.", state

    def _handle_reactive_lights(self, params: dict[str, Any]) -> HandlerResult:
        try:
            from led_controller import apply_music_led_preferences

            apply_music_led_preferences(self.led, self.profile, active=True)
            return True, "Music-reactive lights enabled.", {"reactive": True}
        except Exception:
            state = self._apply_led("pulse", "white", 0.4)
            return True, "Reactive lights enabled (pulse fallback).", state

    def _handle_quiet_hours_override(self, params: dict[str, Any]) -> HandlerResult:
        favorite = str(self.profile.get("preferences", {}).get("favorite_color", "") or "white")
        state = self._apply_led("solid", favorite, 0.45)
        return True, "Quiet hours override: user lighting restored.", state
