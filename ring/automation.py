"""Ring Automation Engine — biometric-triggered bed actions.

Listens to real-time HR / SpO2 / movement callbacks from RingBleClient and
fires automated bed effects (LED, TTS, event log) without requiring any voice
command from the user.

Priority:
    Ring automations have the LOWEST priority. Any explicit voice command
    suppresses ring-triggered automations for VOICE_SUPPRESS_SECONDS seconds.

Trigger table:
    HR > 100 bpm (sustained 3 min, sleep mode)   → dim LED to calm blue
    SpO2 < 93% (2 consecutive readings)           → TTS warning + amber LED pulse
    SpO2 < 88%                                    → EMERGENCY TTS + red LED flash
    No movement > 4 hours                         → mark deep sleep, suppress notifs
    Movement burst after stillness                → switch ambient audio
    HR < 60 bpm after restless period             → restore sleep LED scene
    Ring disconnects overnight                    → log gap, notify on wake
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ring.ble_client import RingBleClient, NoopRingClient
    from ring.models import RingAccelReading, RingHrReading, RingSpo2Reading

logger = logging.getLogger("ring.automation")

# ── Thresholds ────────────────────────────────────────────────────────────────
HR_HIGH_THRESHOLD = 100          # bpm — elevated HR during sleep
HR_HIGH_SUSTAINED_SECONDS = 180  # 3 minutes sustained to trigger
HR_SETTLED_THRESHOLD = 60        # bpm — considered resting / settled

SPO2_WATCH_THRESHOLD = 93        # % — first-level warning
SPO2_WATCH_CONSECUTIVE = 2       # consecutive readings needed
SPO2_EMERGENCY_THRESHOLD = 88    # % — clinical emergency level

STILLNESS_DEEP_SLEEP_SECONDS = 4 * 3600   # 4 hours without movement
MOVEMENT_BURST_ACCEL_G = 0.3              # g-force threshold for "burst"

VOICE_SUPPRESS_SECONDS = 300     # 5 min voice command suppression

# ── LED color codes used by set_color_value ───────────────────────────────────
LED_CALM_BLUE = "calm_blue"
LED_AMBER_PULSE = "amber"
LED_RED_EMERGENCY = "red"
LED_SLEEP = "sleep"


class RingAutomationEngine:
    """Subscribes to ring callbacks and fires automated bed effects.

    Usage::

        engine = RingAutomationEngine(ring_client, led, tts, tts_player, profile)
        engine.start()
        # ... later on shutdown:
        engine.stop()
    """

    def __init__(
        self,
        ring_client: "RingBleClient | NoopRingClient",
        led: object,
        tts: object,
        tts_player: object,
        profile: dict,
        *,
        say_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._ring = ring_client
        self._led = led
        self._tts = tts
        self._tts_player = tts_player
        self._profile = profile
        self._say = say_callback  # injected by app_entry after TTS is ready

        # State
        self._lock = threading.Lock()
        self._running = False

        # HR tracking
        self._hr_high_since: datetime | None = None
        self._last_hr_bpm: int = 0
        self._was_restless = False

        # SpO2 tracking (sliding window of last N readings)
        self._spo2_window: deque[int] = deque(maxlen=SPO2_WATCH_CONSECUTIVE)

        # Movement tracking
        self._last_movement_at: datetime = datetime.now()
        self._deep_sleep_flagged = False

        # Disconnect tracking
        self._disconnect_logged_at: datetime | None = None

        # Voice suppression
        self._voice_suppressed_until: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Register callbacks with the ring client and start the engine."""
        with self._lock:
            if self._running:
                return
            self._running = True

        ring = self._ring
        # Register callbacks (NoopRingClient accepts them silently)
        if hasattr(ring, "on_hr_reading"):
            ring.on_hr_reading(self._on_hr)
        if hasattr(ring, "on_spo2_reading"):
            ring.on_spo2_reading(self._on_spo2)
        if hasattr(ring, "on_movement"):
            ring.on_movement(self._on_movement)
        if hasattr(ring, "on_disconnect"):
            ring.on_disconnect(self._on_disconnect)

        logger.info("RingAutomationEngine started.")

    def stop(self) -> None:
        with self._lock:
            self._running = False
        logger.info("RingAutomationEngine stopped.")

    def suppress_for_voice_command(self) -> None:
        """Call this whenever the user issues a voice command.

        Suppresses ring automations for VOICE_SUPPRESS_SECONDS so explicit
        user intent always wins.
        """
        self._voice_suppressed_until = time.monotonic() + VOICE_SUPPRESS_SECONDS
        logger.debug("Ring automations suppressed for %ds after voice command.", VOICE_SUPPRESS_SECONDS)

    def notify_wake(self) -> str:
        """Return a morning ring summary for inclusion in the wake greeting."""
        ring = self._ring
        lines: list[str] = []

        if hasattr(ring, "last_hr"):
            hr = ring.last_hr
            bpm = getattr(hr, "heart_rate_bpm", 0) or 0
            if bpm > 0:
                if bpm < 60:
                    lines.append(f"Your resting heart rate overnight was {bpm} bpm — nice and calm.")
                elif bpm > 90:
                    lines.append(f"Your heart rate was a bit elevated overnight at {bpm} bpm.")
                else:
                    lines.append(f"Your overnight heart rate was {bpm} bpm — healthy range.")

        if hasattr(ring, "last_spo2"):
            spo2 = ring.last_spo2
            pct = getattr(spo2, "spo2_pct", 0) or 0
            if pct > 0:
                if pct < 93:
                    lines.append(f"Oxygen saturation dipped to {pct}% at some point — mention this to your doctor if it happens often.")
                else:
                    lines.append(f"Oxygen level was {pct}% — well within normal range.")

        if self._disconnect_logged_at is not None:
            lines.append("The smart ring briefly disconnected overnight. Make sure it's charged.")
            self._disconnect_logged_at = None

        return " ".join(lines)

    # ── Internal callbacks ────────────────────────────────────────────────────

    def _suppressed(self) -> bool:
        if not self._running:
            return True
        if time.monotonic() < self._voice_suppressed_until:
            return True
        return False

    def _is_sleep_mode(self) -> bool:
        return bool(self._profile.get("runtime_flags", {}).get("sleep_mode", False))

    def _on_hr(self, reading: "RingHrReading") -> None:
        bpm = int(getattr(reading, "heart_rate_bpm", 0) or 0)
        if bpm <= 0:
            return

        self._last_hr_bpm = bpm

        if self._suppressed():
            return

        now = datetime.now()

        if self._is_sleep_mode():
            # ── HIGH HR during sleep ──────────────────────────────────────
            if bpm > HR_HIGH_THRESHOLD:
                if self._hr_high_since is None:
                    self._hr_high_since = now
                    logger.debug("Ring: elevated HR detected (%d bpm). Monitoring.", bpm)
                else:
                    elapsed = (now - self._hr_high_since).total_seconds()
                    if elapsed >= HR_HIGH_SUSTAINED_SECONDS:
                        logger.info("Ring automation: sustained high HR (%d bpm, %.0fs). Dimming to calm blue.", bpm, elapsed)
                        self._set_led_calm()
                        self._hr_high_since = None  # reset until next trigger
                        self._was_restless = True
            else:
                self._hr_high_since = None

            # ── HR settled after restlessness ─────────────────────────────
            if self._was_restless and bpm < HR_SETTLED_THRESHOLD:
                logger.info("Ring automation: HR settled (%d bpm). Restoring sleep scene.", bpm)
                self._restore_sleep_scene()
                self._was_restless = False

    def _on_spo2(self, reading: "RingSpo2Reading") -> None:
        pct = int(getattr(reading, "spo2_pct", 0) or 0)
        if pct <= 0:
            return

        self._spo2_window.append(pct)

        if self._suppressed():
            return

        # ── Emergency threshold ───────────────────────────────────────────
        if pct <= SPO2_EMERGENCY_THRESHOLD:
            logger.warning("Ring automation: EMERGENCY SpO2 (%d%%). Firing safety alert.", pct)
            self._emergency_spo2_alert(pct)
            return

        # ── Watch threshold (two consecutive low readings) ────────────────
        if (
            len(self._spo2_window) >= SPO2_WATCH_CONSECUTIVE
            and all(v < SPO2_WATCH_THRESHOLD for v in self._spo2_window)
        ):
            logger.info("Ring automation: low SpO2 (%d%%) x %d readings. Alerting.", pct, SPO2_WATCH_CONSECUTIVE)
            self._spo2_warning_alert(pct)
            self._spo2_window.clear()  # reset window to avoid repeated alerts

    def _on_movement(self, reading: "RingAccelReading") -> None:
        magnitude = float(getattr(reading, "magnitude_g", 0.0) or 0.0)
        now = datetime.now()

        if not self._suppressed() and self._is_sleep_mode():
            # ── Deep sleep detection ──────────────────────────────────────
            if magnitude < MOVEMENT_BURST_ACCEL_G:
                stillness_seconds = (now - self._last_movement_at).total_seconds()
                if stillness_seconds >= STILLNESS_DEEP_SLEEP_SECONDS and not self._deep_sleep_flagged:
                    logger.info("Ring automation: deep sleep detected (%.1fh stillness). Suppressing automations.", stillness_seconds / 3600)
                    self._deep_sleep_flagged = True
                    self._profile.setdefault("runtime_flags", {})["ring_deep_sleep"] = True
            else:
                # Movement burst
                was_deep = self._deep_sleep_flagged
                self._last_movement_at = now
                self._deep_sleep_flagged = False
                self._profile.setdefault("runtime_flags", {})["ring_deep_sleep"] = False

                if was_deep:
                    # User stirred from deep sleep — flag potential restlessness
                    logger.info("Ring automation: movement burst after deep sleep. Flagging restlessness.")
                    self._was_restless = True
        elif magnitude >= MOVEMENT_BURST_ACCEL_G:
            self._last_movement_at = now

    def _on_disconnect(self) -> None:
        now = datetime.now()
        self._disconnect_logged_at = now
        logger.warning("Ring automation: ring disconnected at %s.", now.strftime("%H:%M"))

    # ── Effect helpers ────────────────────────────────────────────────────────

    def _set_led_calm(self) -> None:
        try:
            led = self._led
            if hasattr(led, "set_user_animation"):
                led.set_user_animation("breathing")  # type: ignore[union-attr]
            if hasattr(led, "set_user_brightness"):
                led.set_user_brightness(0.15)         # type: ignore[union-attr]
            if hasattr(led, "set_color_value"):
                led.set_color_value(LED_CALM_BLUE)    # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Ring automation: LED calm effect failed: %s", exc)

    def _restore_sleep_scene(self) -> None:
        try:
            led = self._led
            if hasattr(led, "set_state"):
                led.set_state("sleep")                # type: ignore[union-attr]
            if hasattr(led, "set_user_brightness"):
                led.set_user_brightness(0.1)          # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Ring automation: LED sleep restore failed: %s", exc)

    def _say_text(self, text: str) -> None:
        """Speak text if a say callback is wired in, otherwise log only."""
        if callable(self._say):
            try:
                self._say(text)
                return
            except Exception as exc:
                logger.warning("Ring automation: say callback failed: %s", exc)
        logger.info("Ring automation [SAY]: %s", text)

    def _spo2_warning_alert(self, pct: int) -> None:
        try:
            led = self._led
            if hasattr(led, "set_color_value"):
                led.set_color_value(LED_AMBER_PULSE)  # type: ignore[union-attr]
            if hasattr(led, "set_user_animation"):
                led.set_user_animation("pulse")       # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Ring automation: SpO2 LED effect failed: %s", exc)

        self._say_text(
            f"Your oxygen saturation is at {pct} percent. "
            "Please adjust your sleeping position to improve airflow."
        )

    def _emergency_spo2_alert(self, pct: int) -> None:
        try:
            led = self._led
            if hasattr(led, "set_color_value"):
                led.set_color_value(LED_RED_EMERGENCY)  # type: ignore[union-attr]
            if hasattr(led, "set_user_animation"):
                led.set_user_animation("flash")          # type: ignore[union-attr]
            if hasattr(led, "set_user_brightness"):
                led.set_user_brightness(1.0)             # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Ring automation: emergency LED failed: %s", exc)

        self._say_text(
            "[EMERGENCY] Critical oxygen level detected. "
            f"Your SpO2 is {pct} percent. Please wake up and sit upright immediately. "
            "If this continues, seek medical help."
        )
