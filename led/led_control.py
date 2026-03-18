from __future__ import annotations

from config import settings
from hardware.pi_led import _LedFrameState, build_led_backend


class LEDController:
    NAMED_COLORS = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "purple": (128, 0, 128),
        "white": (255, 255, 255),
        "cyan": (0, 255, 255),
        "orange": (255, 165, 0),
        "pink": (255, 105, 180),
    }

    def __init__(
        self,
        user_strip_pin: int = 18,
        state_strip_pin: int = 13,
        user_strip_led_count: int = 120,
        state_strip_led_count: int = 60,
        backend=None,
    ):
        self.color = (0, 0, 0)
        self.state_strip_color = (0, 0, 0)
        self.user_strip_color = (0, 0, 0)
        self.brightness = 0.5  # 0.0 to 1.0
        self.user_strip_brightness = 0.5
        self.user_strip_animation = "solid"
        self.user_strip_pin = max(0, int(user_strip_pin))
        self.state_strip_pin = max(0, int(state_strip_pin))
        self.user_strip_led_count = max(1, int(user_strip_led_count))
        self.state_strip_led_count = max(1, int(state_strip_led_count))
        self.music_reactive_enabled = True
        self.music_reactive_active = False
        self.music_reactive_mode = "pulse"
        self.music_reactive_energy = "calm"
        self.music_reactive_target = "both"
        self.music_reactive_brightness = 0.35
        self._last_state = "standby"
        self._custom_backend = backend
        self._backend = None
        self.state_colors = {
            "standby": (57, 255, 220),
            "listening": (0, 255, 0),
            "thinking": (0, 0, 255),
            "speaking": (128, 0, 128),
            "error": (255, 0, 0),
            "offline": (255, 140, 0),
            "sleep": (0, 0, 0),
        }
        self._rebuild_backend()

    def _build_backend(self):
        if self._custom_backend is not None:
            return self._custom_backend
        return build_led_backend(
            enabled=bool(settings.led_hw_enabled),
            backend_name=str(settings.led_backend),
            user_strip_pin=self.user_strip_pin,
            state_strip_pin=self.state_strip_pin,
            user_strip_led_count=self.user_strip_led_count,
            state_strip_led_count=self.state_strip_led_count,
            frequency_hz=int(settings.led_frequency_hz),
            user_dma_channel=int(settings.led_user_dma_channel),
            state_dma_channel=int(settings.led_state_dma_channel),
            invert_signal=bool(settings.led_invert_signal),
            led_max_brightness=int(settings.led_max_brightness),
            animation_fps=float(settings.led_animation_fps),
        )

    def _frame_state(self) -> _LedFrameState:
        return _LedFrameState(
            user_color=tuple(self.user_strip_color),
            user_brightness=float(self.user_strip_brightness),
            user_animation=str(self.user_strip_animation),
            state_color=tuple(self.state_strip_color),
            state_brightness=float(self.brightness),
        )

    def _sync_hardware(self):
        if self._backend is None:
            return
        try:
            self._backend.sync(self._frame_state())
        except Exception as exc:
            print(f"[LED][Hardware] Sync failed: {exc}")

    def _rebuild_backend(self):
        existing = self._backend
        if existing is not None and hasattr(existing, "close") and existing is not self._custom_backend:
            try:
                existing.close()
            except Exception:
                pass
        self._backend = self._build_backend()
        self._sync_hardware()

    def update_hardware_config(
        self,
        user_strip_pin: int | None = None,
        state_strip_pin: int | None = None,
        user_strip_led_count: int | None = None,
        state_strip_led_count: int | None = None,
    ):
        if user_strip_pin is not None:
            self.user_strip_pin = max(0, int(user_strip_pin))
        if state_strip_pin is not None:
            self.state_strip_pin = max(0, int(state_strip_pin))
        if user_strip_led_count is not None:
            self.user_strip_led_count = max(1, int(user_strip_led_count))
        if state_strip_led_count is not None:
            self.state_strip_led_count = max(1, int(state_strip_led_count))

        print(
            "[LED][Hardware] "
            f"user(pin={self.user_strip_pin}, count={self.user_strip_led_count}) | "
            f"state(pin={self.state_strip_pin}, count={self.state_strip_led_count})"
        )
        self._rebuild_backend()

    def hardware_status(self) -> str:
        backend_line = ""
        if self._backend is not None and hasattr(self._backend, "status_line"):
            try:
                backend_line = str(self._backend.status_line() or "").strip()
            except Exception:
                backend_line = ""
        status = (
            "LED config -> "
            f"user strip: pin {self.user_strip_pin}, count {self.user_strip_led_count}; "
            f"state strip: pin {self.state_strip_pin}, count {self.state_strip_led_count}."
        )
        if backend_line:
            return f"{status} Backend: {backend_line}"
        return status

    def hardware_ready(self) -> bool:
        if self._backend is None or not hasattr(self._backend, "is_available"):
            return False
        try:
            return bool(self._backend.is_available())
        except Exception:
            return False

    def close(self):
        if self._backend is None or not hasattr(self._backend, "close"):
            return
        try:
            self._backend.close()
        except Exception:
            return

    def _set_color(self, rgb, label: str):
        r, g, b = [max(0, min(255, int(c))) for c in rgb]
        self.color = (r, g, b)
        print(f"[LED] {label} -> {self.color} @ {int(self.brightness * 100)}%")
        self._sync_hardware()

    def _set_user_strip_color(self, rgb, label: str):
        r, g, b = [max(0, min(255, int(c))) for c in rgb]
        self.user_strip_color = (r, g, b)
        print(
            "[LED][UserStrip] "
            f"{label} -> {self.user_strip_color} @ {int(self.user_strip_brightness * 100)}% "
            f"animation={self.user_strip_animation}"
        )
        self._sync_hardware()

    def set_color_name(self, name: str):
        color = self.NAMED_COLORS.get(name.strip().lower())
        if color is None:
            print(f"[LED] Unknown named color: {name}")
            return
        self._set_user_strip_color(color, f"named color '{name}'")

    def set_color_hex(self, hex_value: str):
        value = hex_value.strip().lstrip("#")
        if len(value) != 6:
            print(f"[LED] Invalid hex color: {hex_value}")
            return
        try:
            rgb = tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            print(f"[LED] Invalid hex color: {hex_value}")
            return
        self._set_user_strip_color(rgb, f"hex color '#{value}'")

    def set_color_rgb(self, r: int, g: int, b: int):
        self._set_user_strip_color((r, g, b), "rgb color")

    def set_color_value(self, value: str):
        text = value.strip()

        if text.startswith("#"):
            self.set_color_hex(text)
            return

        if text.lower().startswith("rgb(") and text.endswith(")"):
            body = text[4:-1]
            try:
                r, g, b = [int(part.strip()) for part in body.split(",")]
                self.set_color_rgb(r, g, b)
                return
            except (ValueError, TypeError):
                print(f"[LED] Invalid rgb format: {value}")
                return

        if text.lower() in self.NAMED_COLORS:
            self.set_color_name(text.lower())
            return

        normalized = " ".join(
            part for part in "".join(ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in text).split() if part
        )
        for name in self.NAMED_COLORS:
            if f" {name} " in f" {normalized} ":
                self.set_color_name(name)
                return

        print(
            "[LED] Unsupported color format. Use name, #RRGGBB, or rgb(r,g,b)."
        )

    def set_state(self, state: str):
        key = state.strip().lower()
        self._last_state = key
        color = self.state_colors.get(key)
        if color is None:
            print(f"[LED] Unknown state: {state}")
            return
        if (
            self.music_reactive_enabled
            and self.music_reactive_active
            and self.music_reactive_target == "both"
            and key in {"standby", "listening", "sleep"}
        ):
            color = self._music_state_color()
        self.state_strip_color = color
        self._set_color(color, f"state '{key}'")
        self._sync_hardware()

    def _music_state_color(self):
        return (255, 90, 20) if self.music_reactive_energy == "energetic" else (57, 255, 220)

    def _music_animation_name(self):
        mapping = {
            "pulse": "pulse",
            "wave": "wave",
            "spectrum": "rainbow",
        }
        return mapping.get(self.music_reactive_mode, "pulse")

    def configure_music_reactive(
        self,
        enabled: bool | None = None,
        active: bool | None = None,
        mode: str | None = None,
        energy: str | None = None,
        target: str | None = None,
        brightness: float | None = None,
    ):
        if enabled is not None:
            self.music_reactive_enabled = bool(enabled)
        if mode is not None:
            candidate = mode.strip().lower()
            if candidate in {"pulse", "wave", "spectrum"}:
                self.music_reactive_mode = candidate
        if energy is not None:
            candidate = energy.strip().lower()
            if candidate in {"calm", "energetic"}:
                self.music_reactive_energy = candidate
        if target is not None:
            candidate = target.strip().lower()
            if candidate in {"both", "user_only"}:
                self.music_reactive_target = candidate
        if brightness is not None:
            self.music_reactive_brightness = max(0.05, min(1.0, float(brightness)))
        if active is not None:
            self.music_reactive_active = bool(active)

        if self.music_reactive_enabled and self.music_reactive_active:
            self.set_user_animation(self._music_animation_name())
            self.set_user_brightness(self.music_reactive_brightness)
            if self.music_reactive_target == "both":
                self.state_strip_color = self._music_state_color()
                self._set_color(self.state_strip_color, "music reactive")
        else:
            self._sync_hardware()

    def music_reactive_status(self) -> str:
        return (
            "Music lights -> "
            f"enabled={self.music_reactive_enabled}, active={self.music_reactive_active}, "
            f"mode={self.music_reactive_mode}, energy={self.music_reactive_energy}, "
            f"target={self.music_reactive_target}, brightness={int(self.music_reactive_brightness * 100)}%."
        )

    def set_user_animation(self, animation: str):
        allowed = {"solid", "breathing", "pulse", "rainbow", "wave", "strobe"}
        name = animation.strip().lower()
        if name not in allowed:
            print(f"[LED][UserStrip] Unknown animation: {animation}")
            return
        if self.user_strip_animation == name:
            return
        self.user_strip_animation = name
        print(f"[LED][UserStrip] animation -> {self.user_strip_animation}")
        self._sync_hardware()

    def set_user_brightness(self, value: float, log: bool = True):
        old_percent = int(self.user_strip_brightness * 100)
        self.user_strip_brightness = max(0.0, min(1.0, float(value)))
        new_percent = int(self.user_strip_brightness * 100)
        if log and new_percent != old_percent:
            print(f"[LED][UserStrip] Brightness -> {new_percent}%")
        self._sync_hardware()

    def brightness_up(self):
        self.brightness = min(1.0, self.brightness + 0.2)
        print(f"[LED] Brightness -> {int(self.brightness * 100)}%")
        self._sync_hardware()

    def brightness_down(self):
        self.brightness = max(0.1, self.brightness - 0.2)
        print(f"[LED] Brightness -> {int(self.brightness * 100)}%")
        self._sync_hardware()
