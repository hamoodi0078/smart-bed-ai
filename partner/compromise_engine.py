"""Auto-compromise scene engine for Smart Bed AI partner mode.

Resolves conflicting preferences when both partners are in bed by
computing averaged/zoned lighting, sound levels, and scene parameters.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("partner.compromise_engine")


class CompromiseEngine:
    """Resolves partner preference conflicts with automatic compromise scenes."""

    STRATEGIES = {
        "average": "Average both preferences",
        "quieter": "Use the quieter/dimmer preference",
        "louder": "Use the louder/brighter preference",
        "alternate": "Alternate between preferences",
        "zone": "Zone-based (each side gets own preference)",
    }

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("partner_mode", {})
        pm = profile["partner_mode"]
        pm.setdefault(
            "compromise_settings",
            {
                "brightness_strategy": "average",
                "sound_strategy": "quieter",
                "wake_strategy": "staggered",
                "color_strategy": "average",
            },
        )

    def resolve_scene(self, profile: dict, both_present: bool = True) -> dict[str, Any]:
        """Compute compromise scene settings when both partners in bed."""
        self.ensure_shape(profile)
        pm = profile.get("partner_mode", {})

        if not both_present:
            return {"compromise_needed": False}

        p1 = pm.get("partner1", {}).get("scene_preferences", {})
        p2 = pm.get("partner2", {}).get("scene_preferences", {})
        settings = pm.get("compromise_settings", {})

        brightness = self._resolve_numeric(
            float(p1.get("brightness", 0.3)),
            float(p2.get("brightness", 0.3)),
            str(settings.get("brightness_strategy", "average")),
        )
        volume = self._resolve_numeric(
            float(p1.get("volume", 0.3)),
            float(p2.get("volume", 0.3)),
            str(settings.get("sound_strategy", "quieter")),
        )
        color = self._resolve_color(
            str(p1.get("color", "#FFF8DC")),
            str(p2.get("color", "#FFF8DC")),
            str(settings.get("color_strategy", "average")),
        )

        return {
            "compromise_needed": True,
            "brightness": round(brightness, 3),
            "volume": round(volume, 3),
            "color": color,
            "strategies_used": {
                "brightness": settings.get("brightness_strategy", "average"),
                "sound": settings.get("sound_strategy", "quieter"),
                "color": settings.get("color_strategy", "average"),
            },
            "led_action": {
                "type": "led_scene",
                "action": "partner_compromise",
                "brightness": round(brightness, 3),
                "color": color,
                "animation": "solid",
            },
        }

    def resolve_reading_conflict(self, profile: dict, reading_side: str) -> dict[str, Any]:
        """One partner reading, other sleeping. Zone lighting."""
        self.ensure_shape(profile)
        return {
            "type": "zoned_scene",
            "zones": {
                reading_side: {
                    "brightness": 0.35,
                    "color": "#FFF8DC",
                    "animation": "solid",
                    "purpose": "reading",
                },
                "left" if reading_side == "right" else "right": {
                    "brightness": 0.0,
                    "color": "#000000",
                    "animation": "off",
                    "purpose": "sleeping",
                },
            },
        }

    def resolve_prayer_conflict(self, profile: dict, praying_side: str) -> dict[str, Any]:
        """One partner at prayer time, other sleeping."""
        self.ensure_shape(profile)
        other = "left" if praying_side == "right" else "right"
        return {
            "type": "zoned_scene",
            "zones": {
                praying_side: {
                    "brightness": 0.10,
                    "color": "#FFF5E0",
                    "animation": "gentle_pulse",
                    "purpose": "prayer",
                },
                other: {
                    "brightness": 0.0,
                    "color": "#000000",
                    "animation": "off",
                    "purpose": "sleeping",
                },
            },
            "sound": {"type": "vibration_only", "side": praying_side},
        }

    # ------------------------------------------------------------------
    # Pre-built compromise scenes
    # ------------------------------------------------------------------

    @staticmethod
    def get_prebuilt_scenes() -> list[dict[str, Any]]:
        return [
            {
                "name": "Balanced Default",
                "description": "Average of both preferences",
                "brightness": 0.22,
                "color": "#FFE4C4",
                "volume": 0.2,
            },
            {
                "name": "Partner Quiet",
                "description": "Minimal disturbance mode",
                "brightness": 0.10,
                "color": "#FFD9B3",
                "volume": 0.0,
            },
            {
                "name": "Reading Partner",
                "description": "Focused light on one side only",
                "brightness": 0.35,
                "color": "#FFF8DC",
                "volume": 0.0,
                "zoned": True,
            },
            {
                "name": "Wind Down Together",
                "description": "Synchronized couple wind-down",
                "brightness": 0.15,
                "color": "#FFC87C",
                "volume": 0.15,
                "animation": "breathing",
            },
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_numeric(val1: float, val2: float, strategy: str) -> float:
        if strategy == "quieter":
            return min(val1, val2)
        if strategy == "louder":
            return max(val1, val2)
        return (val1 + val2) / 2.0

    @staticmethod
    def _resolve_color(hex1: str, hex2: str, strategy: str) -> str:
        if strategy == "average":
            try:
                r1 = int(hex1[1:3], 16)
                g1 = int(hex1[3:5], 16)
                b1 = int(hex1[5:7], 16)
                r2 = int(hex2[1:3], 16)
                g2 = int(hex2[3:5], 16)
                b2 = int(hex2[5:7], 16)
                r = (r1 + r2) // 2
                g = (g1 + g2) // 2
                b = (b1 + b2) // 2
                return f"#{r:02X}{g:02X}{b:02X}"
            except Exception:
                return hex1
        return hex1
