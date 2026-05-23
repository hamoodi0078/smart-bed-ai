from __future__ import annotations

import logging
import math
import sys
import threading
import time
from dataclasses import dataclass


try:
    from rpi_ws281x import Color, PixelStrip
except Exception:  # pragma: no cover - optional runtime dependency
    Color = None
    PixelStrip = None


logger = logging.getLogger("hardware.pi_led")
SUPPORTED_GPIO_CHANNELS = {
    12: 0,
    18: 0,
    13: 1,
    19: 1,
}


@dataclass
class _LedFrameState:
    user_color: tuple[int, int, int] = (0, 0, 0)
    user_brightness: float = 0.5
    user_animation: str = "solid"
    state_color: tuple[int, int, int] = (0, 0, 0)
    state_brightness: float = 0.5


class NoopLedBackend:
    def __init__(self, reason: str):
        self._reason = str(reason or "LED hardware backend disabled.")

    def is_available(self) -> bool:
        return False

    def status_line(self) -> str:
        return self._reason

    def sync(self, frame_state: _LedFrameState) -> None:
        return

    def close(self) -> None:
        return


class RaspberryPiWs281xBackend:
    def __init__(
        self,
        *,
        user_strip_pin: int,
        state_strip_pin: int,
        user_strip_led_count: int,
        state_strip_led_count: int,
        frequency_hz: int = 800000,
        user_dma_channel: int = 10,
        state_dma_channel: int = 11,
        invert_signal: bool = False,
        led_max_brightness: int = 255,
        animation_fps: float = 20.0,
    ):
        self._frequency_hz = max(400000, int(frequency_hz))
        self._user_dma_channel = max(0, int(user_dma_channel))
        self._state_dma_channel = max(0, int(state_dma_channel))
        self._invert_signal = bool(invert_signal)
        self._led_max_brightness = max(8, min(255, int(led_max_brightness)))
        self._animation_fps = max(4.0, min(60.0, float(animation_fps)))
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._dirty_event = threading.Event()
        self._frame_state = _LedFrameState()
        self._started = False
        self._status = "LED hardware backend unavailable."
        self._user_strip = None
        self._state_strip = None

        if not sys.platform.startswith("linux"):
            self._status = "LED hardware disabled: non-Linux platform."
            return
        if PixelStrip is None or Color is None:
            self._status = "LED hardware disabled: install rpi-ws281x on the Raspberry Pi."
            return
        if user_strip_pin not in SUPPORTED_GPIO_CHANNELS:
            self._status = f"LED hardware disabled: user strip pin {user_strip_pin} is unsupported for WS2812 on Raspberry Pi."
            return
        if state_strip_pin not in SUPPORTED_GPIO_CHANNELS:
            self._status = f"LED hardware disabled: state strip pin {state_strip_pin} is unsupported for WS2812 on Raspberry Pi."
            return

        try:
            self._user_strip = self._build_strip(
                count=max(1, int(user_strip_led_count)),
                pin=int(user_strip_pin),
                dma_channel=self._user_dma_channel,
            )
            self._state_strip = self._build_strip(
                count=max(1, int(state_strip_led_count)),
                pin=int(state_strip_pin),
                dma_channel=self._state_dma_channel,
            )
            self._status = (
                "Raspberry Pi WS2812 backend active: "
                f"user pin {user_strip_pin} ({user_strip_led_count} LEDs), "
                f"state pin {state_strip_pin} ({state_strip_led_count} LEDs)."
            )
            self._started = True
            self._thread = threading.Thread(target=self._run_loop, name="pi-led-backend", daemon=True)
            self._thread.start()
        except Exception as exc:
            self._status = f"LED hardware unavailable: {exc}"
            logger.warning("Failed to initialize Raspberry Pi LED backend: %s", exc)
            self.close()

    def _build_strip(self, *, count: int, pin: int, dma_channel: int):
        channel = SUPPORTED_GPIO_CHANNELS[int(pin)]
        strip = PixelStrip(
            int(count),
            int(pin),
            self._frequency_hz,
            int(dma_channel),
            self._invert_signal,
            self._led_max_brightness,
            int(channel),
        )
        strip.begin()
        return strip

    def is_available(self) -> bool:
        return bool(self._started and self._user_strip is not None and self._state_strip is not None)

    def status_line(self) -> str:
        return self._status

    def sync(self, frame_state: _LedFrameState) -> None:
        if not self.is_available():
            return
        with self._lock:
            self._frame_state = frame_state
        self._dirty_event.set()

    def close(self) -> None:
        self._stop_event.set()
        strips = [self._user_strip, self._state_strip]
        self._user_strip = None
        self._state_strip = None
        self._started = False
        for strip in strips:
            if strip is None:
                continue
            try:
                self._fill_strip(strip, [(0, 0, 0)] * int(strip.numPixels()))
            except Exception:
                continue

    @staticmethod
    def _clamp_byte(value: float) -> int:
        return max(0, min(255, int(round(float(value)))))

    def _scaled_rgb(self, rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
        safe_factor = max(0.0, min(1.0, float(factor)))
        return (
            self._clamp_byte(rgb[0] * safe_factor),
            self._clamp_byte(rgb[1] * safe_factor),
            self._clamp_byte(rgb[2] * safe_factor),
        )

    @staticmethod
    def _wheel(position: int) -> tuple[int, int, int]:
        value = max(0, min(255, int(position)))
        if value < 85:
            return 255 - value * 3, value * 3, 0
        if value < 170:
            value -= 85
            return 0, 255 - value * 3, value * 3
        value -= 170
        return value * 3, 0, 255 - value * 3

    def _user_pixels_for_frame(self, frame_state: _LedFrameState, frame_idx: int, count: int) -> list[tuple[int, int, int]]:
        base_color = tuple(int(c) for c in frame_state.user_color)
        base_brightness = max(0.0, min(1.0, float(frame_state.user_brightness)))
        animation = str(frame_state.user_animation or "solid").strip().lower()
        now = time.monotonic()

        if animation == "breathing":
            factor = 0.18 + (0.82 * ((math.sin(now * 1.4) + 1.0) / 2.0))
            color = self._scaled_rgb(base_color, base_brightness * factor)
            return [color] * count
        if animation == "pulse":
            factor = 0.08 + (0.92 * ((math.sin(now * 3.0) + 1.0) / 2.0))
            color = self._scaled_rgb(base_color, base_brightness * factor)
            return [color] * count
        if animation == "strobe":
            factor = 1.0 if int(now * 8.0) % 2 == 0 else 0.0
            color = self._scaled_rgb(base_color, base_brightness * factor)
            return [color] * count
        if animation == "wave":
            pixels: list[tuple[int, int, int]] = []
            for idx in range(count):
                phase = ((idx / max(1, count)) * math.tau) + (now * 2.4)
                factor = 0.20 + (0.80 * ((math.sin(phase) + 1.0) / 2.0))
                pixels.append(self._scaled_rgb(base_color, base_brightness * factor))
            return pixels
        if animation == "rainbow":
            pixels = []
            for idx in range(count):
                position = int((idx * 256 / max(1, count)) + (frame_idx * 6)) % 256
                raw = self._wheel(position)
                pixels.append(self._scaled_rgb(raw, base_brightness))
            return pixels

        color = self._scaled_rgb(base_color, base_brightness)
        return [color] * count

    def _fill_strip(self, strip, colors: list[tuple[int, int, int]]) -> None:
        for idx, (r, g, b) in enumerate(colors):
            strip.setPixelColor(idx, Color(int(r), int(g), int(b)))
        strip.show()

    def _render_frame(self, frame_idx: int) -> None:
        user_strip = self._user_strip
        state_strip = self._state_strip
        if user_strip is None or state_strip is None:
            return
        with self._lock:
            frame_state = self._frame_state
        user_pixels = self._user_pixels_for_frame(frame_state, frame_idx, int(user_strip.numPixels()))
        state_color = self._scaled_rgb(frame_state.state_color, float(frame_state.state_brightness))
        state_pixels = [state_color] * int(state_strip.numPixels())
        self._fill_strip(user_strip, user_pixels)
        self._fill_strip(state_strip, state_pixels)

    def _run_loop(self) -> None:
        frame_idx = 0
        _render_failures = 0
        _max_render_failures = 3
        _render_backoff_seconds = 0.5
        while not self._stop_event.is_set():
            with self._lock:
                animation = str(self._frame_state.user_animation or "solid").strip().lower()

            is_animated = animation in {"breathing", "pulse", "strobe", "wave", "rainbow"}
            timeout = (1.0 / self._animation_fps) if is_animated else 0.4
            self._dirty_event.wait(timeout=timeout)
            self._dirty_event.clear()

            if self._stop_event.is_set():
                break

            try:
                self._render_frame(frame_idx)
                _render_failures = 0
            except Exception as exc:
                _render_failures += 1
                self._status = f"LED hardware render failed ({_render_failures}/{_max_render_failures}): {exc}"
                logger.warning(
                    "Raspberry Pi LED render failed (%s/%s): %s",
                    _render_failures,
                    _max_render_failures,
                    exc,
                )
                if _render_failures >= _max_render_failures:
                    logger.error("LED render failure threshold reached. Shutting down LED thread.")
                    self.close()
                    break
                time.sleep(_render_backoff_seconds)
            frame_idx = (frame_idx + 1) % 10_000


def build_led_backend(
    *,
    enabled: bool,
    backend_name: str,
    user_strip_pin: int,
    state_strip_pin: int,
    user_strip_led_count: int,
    state_strip_led_count: int,
    frequency_hz: int,
    user_dma_channel: int,
    state_dma_channel: int,
    invert_signal: bool,
    led_max_brightness: int,
    animation_fps: float,
):
    if not enabled:
        return NoopLedBackend("LED hardware backend disabled (LED_HARDWARE_ENABLED=0).")
    normalized_backend = str(backend_name or "auto").strip().lower()
    if normalized_backend not in {"auto", "ws281x"}:
        return NoopLedBackend(f"LED hardware backend '{normalized_backend}' is not supported.")
    return RaspberryPiWs281xBackend(
        user_strip_pin=user_strip_pin,
        state_strip_pin=state_strip_pin,
        user_strip_led_count=user_strip_led_count,
        state_strip_led_count=state_strip_led_count,
        frequency_hz=frequency_hz,
        user_dma_channel=user_dma_channel,
        state_dma_channel=state_dma_channel,
        invert_signal=invert_signal,
        led_max_brightness=led_max_brightness,
        animation_fps=animation_fps,
    )
