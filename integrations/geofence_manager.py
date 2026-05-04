"""Location-based geofence automation for Smart Bed AI.

Manages home proximity detection via mobile app GPS updates,
triggers arriving/departing automations, and controls away mode.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

logger = logging.getLogger("integrations.geofence_manager")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class GeofenceManager:
    """Manages location-based automations using mobile app GPS updates."""

    def __init__(
        self,
        *,
        home_latitude: float = 0.0,
        home_longitude: float = 0.0,
        arrival_radius_meters: float = 500.0,
        departure_radius_meters: float = 1000.0,
        debounce_minutes: float = 5.0,
    ):
        self._home_lat = float(home_latitude)
        self._home_lon = float(home_longitude)
        self._arrival_radius = max(50.0, float(arrival_radius_meters))
        self._departure_radius = max(self._arrival_radius, float(departure_radius_meters))
        self._debounce = max(1.0, float(debounce_minutes))
        self._last_state = "unknown"  # home, away, approaching, unknown
        self._last_transition_at: datetime | None = None
        self._last_location: dict[str, float] | None = None
        self._on_arrive_callbacks: list[Callable[[], None]] = []
        self._on_depart_callbacks: list[Callable[[], None]] = []

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("geofence", {})
        gf = profile["geofence"]
        gf.setdefault("home_lat", self._home_lat)
        gf.setdefault("home_lon", self._home_lon)
        gf.setdefault("enabled", True)
        gf.setdefault("away_mode_active", False)
        gf.setdefault("arrival_scene_enabled", True)
        gf.setdefault("departure_actions_enabled", True)
        gf.setdefault("history", [])

    def on_arrive(self, callback: Callable[[], None]) -> None:
        if callable(callback):
            self._on_arrive_callbacks.append(callback)

    def on_depart(self, callback: Callable[[], None]) -> None:
        if callable(callback):
            self._on_depart_callbacks.append(callback)

    def set_home(self, latitude: float, longitude: float) -> None:
        self._home_lat = float(latitude)
        self._home_lon = float(longitude)

    # ------------------------------------------------------------------
    # Location update (called from mobile app API)
    # ------------------------------------------------------------------

    def update_location(
        self, profile: dict, latitude: float, longitude: float, now: datetime | None = None
    ) -> dict[str, Any]:
        """Process a GPS location update from the mobile app."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        gf = profile.get("geofence", {})

        if not gf.get("enabled", True):
            return {"processed": False, "reason": "Geofencing disabled."}

        if self._home_lat == 0 and self._home_lon == 0:
            home_lat = float(gf.get("home_lat", 0))
            home_lon = float(gf.get("home_lon", 0))
            if home_lat and home_lon:
                self._home_lat = home_lat
                self._home_lon = home_lon
            else:
                return {"processed": False, "reason": "Home location not set."}

        distance = _haversine_meters(latitude, longitude, self._home_lat, self._home_lon)
        self._last_location = {"lat": latitude, "lon": longitude, "distance_m": distance}

        new_state = self._classify_state(distance)
        actions: list[dict[str, Any]] = []

        if new_state != self._last_state and self._can_transition(now):
            old_state = self._last_state

            if old_state in ("away", "unknown") and new_state == "home":
                actions = self._build_arrival_actions(profile, now, distance)
                gf["away_mode_active"] = False
                self._fire_callbacks(self._on_arrive_callbacks)

            elif old_state == "home" and new_state == "away":
                actions = self._build_departure_actions(profile, now)
                gf["away_mode_active"] = True
                self._fire_callbacks(self._on_depart_callbacks)

            self._last_state = new_state
            self._last_transition_at = now
            self._log_transition(profile, old_state, new_state, distance, now)

        return {
            "processed": True,
            "distance_meters": round(distance, 1),
            "state": new_state,
            "previous_state": self._last_state if new_state == self._last_state else None,
            "actions": actions,
            "away_mode": gf.get("away_mode_active", False),
        }

    # ------------------------------------------------------------------
    # Action builders
    # ------------------------------------------------------------------

    def _build_arrival_actions(self, profile: dict, now: datetime, distance: float) -> list[dict[str, Any]]:
        gf = profile.get("geofence", {})
        actions: list[dict[str, Any]] = []

        if gf.get("arrival_scene_enabled", True):
            hour = now.hour
            if 17 <= hour <= 23:
                actions.append({
                    "type": "led_scene", "action": "welcome_home_evening",
                    "color": "#FFD9B3", "brightness": 0.30, "animation": "warm_glow",
                })
            elif 6 <= hour <= 11:
                actions.append({
                    "type": "led_scene", "action": "welcome_home_morning",
                    "color": "#FFF8DC", "brightness": 0.50, "animation": "solid",
                })

        actions.append({
            "type": "system", "action": "disable_away_mode",
            "message": "Welcome home! Away mode deactivated.",
        })

        return actions

    def _build_departure_actions(self, profile: dict, now: datetime) -> list[dict[str, Any]]:
        gf = profile.get("geofence", {})
        actions: list[dict[str, Any]] = []

        if gf.get("departure_actions_enabled", True):
            actions.append({"type": "system", "action": "enable_away_mode"})
            actions.append({"type": "led_scene", "action": "turn_off", "brightness": 0.0})
            actions.append({"type": "system", "action": "pause_automations"})
            actions.append({"type": "system", "action": "reduce_resources"})

        return actions

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_status(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        gf = profile.get("geofence", {})
        return {
            "state": self._last_state,
            "away_mode": gf.get("away_mode_active", False),
            "home_set": self._home_lat != 0 or self._home_lon != 0,
            "last_distance": self._last_location.get("distance_m") if self._last_location else None,
            "enabled": gf.get("enabled", True),
        }

    def is_away(self) -> bool:
        return self._last_state == "away"

    def is_home(self) -> bool:
        return self._last_state == "home"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _classify_state(self, distance: float) -> str:
        if distance <= self._arrival_radius:
            return "home"
        if distance <= self._departure_radius:
            return "approaching"
        return "away"

    def _can_transition(self, now: datetime) -> bool:
        if self._last_transition_at is None:
            return True
        elapsed = (now - self._last_transition_at).total_seconds() / 60.0
        return elapsed >= self._debounce

    def _log_transition(self, profile: dict, old: str, new: str, distance: float, now: datetime) -> None:
        gf = profile.get("geofence", {})
        history = gf.get("history", [])
        history.append({
            "from": old, "to": new,
            "distance_m": round(distance, 1),
            "timestamp": now.isoformat(),
        })
        gf["history"] = history[-50:]

    @staticmethod
    def _fire_callbacks(callbacks: list) -> None:
        for cb in callbacks:
            try:
                cb()
            except Exception as exc:
                logger.error("Geofence callback error: %s", exc)
