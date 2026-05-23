"""Fitness tracker integration preparation for Smart Bed AI.

Provides a unified interface for future smartwatch/fitness tracker integration
(Apple Watch, Samsung Galaxy Watch, Fitbit, Oura Ring, Whoop).
Defines data models and hooks for biometric data ingestion.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("integrations.fitness_tracker_api")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


SUPPORTED_DEVICES = {
    "garmin": {"name": "Garmin", "metrics": ["heart_rate", "hrv", "spo2", "steps", "calories", "sleep_score", "body_battery", "stress_level"]},
    "apple_watch": {"name": "Apple Watch", "metrics": ["heart_rate", "hrv", "spo2", "steps", "calories"]},
    "samsung_watch": {"name": "Samsung Galaxy Watch", "metrics": ["heart_rate", "spo2", "steps", "stress"]},
    "fitbit": {"name": "Fitbit", "metrics": ["heart_rate", "spo2", "steps", "sleep_stages"]},
    "oura_ring": {"name": "Oura Ring", "metrics": ["heart_rate", "hrv", "temperature", "sleep_stages"]},
    "whoop": {"name": "Whoop", "metrics": ["heart_rate", "hrv", "strain", "recovery"]},
    "generic": {"name": "Generic Tracker", "metrics": ["heart_rate", "steps"]},
}


class FitnessTrackerAPI:
    """Unified interface for fitness tracker biometric data integration."""

    def __init__(self):
        self._connected_device: str = ""
        self._last_sync: datetime | None = None

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("fitness_tracker", {})
        ft = profile["fitness_tracker"]
        ft.setdefault("connected_device", "")
        ft.setdefault("enabled", False)
        ft.setdefault("last_sync_at", "")
        ft.setdefault("biometric_history", [])
        ft.setdefault("daily_summary", {})
        ft.setdefault("health_alerts", [])

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def connect_device(self, profile: dict, device_type: str) -> dict[str, Any]:
        """Connect a fitness tracker device."""
        self.ensure_shape(profile)
        device_type = str(device_type).strip().lower()

        if device_type not in SUPPORTED_DEVICES:
            return {
                "connected": False,
                "reason": f"Unsupported device. Supported: {', '.join(SUPPORTED_DEVICES.keys())}",
            }

        device_info = SUPPORTED_DEVICES[device_type]
        profile["fitness_tracker"]["connected_device"] = device_type
        profile["fitness_tracker"]["enabled"] = True
        self._connected_device = device_type

        logger.info("Fitness tracker connected: %s", device_info["name"])
        return {
            "connected": True,
            "device": device_info["name"],
            "available_metrics": device_info["metrics"],
            "message": f"{device_info['name']} connected. Biometric data will enhance your sleep insights.",
        }

    def disconnect_device(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        profile["fitness_tracker"]["connected_device"] = ""
        profile["fitness_tracker"]["enabled"] = False
        self._connected_device = ""
        return {"disconnected": True}

    def get_supported_devices(self) -> list[dict[str, Any]]:
        return [
            {"id": k, "name": v["name"], "metrics": v["metrics"]}
            for k, v in SUPPORTED_DEVICES.items()
        ]

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def ingest_biometric_data(
        self, profile: dict, data: dict[str, Any], now: datetime | None = None
    ) -> dict[str, Any]:
        """Receive biometric data from connected device."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        ft = profile["fitness_tracker"]

        if not ft.get("enabled", False):
            return {"ingested": False, "reason": "No device connected."}

        entry = {
            "timestamp": now.isoformat(),
            "heart_rate": self._safe_float(data.get("heart_rate")),
            "hrv": self._safe_float(data.get("hrv")),
            "spo2": self._safe_float(data.get("spo2")),
            "temperature": self._safe_float(data.get("temperature")),
            "steps": self._safe_int(data.get("steps")),
            "calories": self._safe_int(data.get("calories")),
            "strain": self._safe_float(data.get("strain")),
            "recovery": self._safe_float(data.get("recovery")),
            "stress_level": self._safe_float(data.get("stress_level")),
        }

        ft["biometric_history"].append(entry)
        ft["biometric_history"] = ft["biometric_history"][-2000:]
        ft["last_sync_at"] = now.isoformat()
        self._last_sync = now

        alerts = self._check_health_alerts(entry, profile)
        if alerts:
            ft["health_alerts"].extend(alerts)
            ft["health_alerts"] = ft["health_alerts"][-50:]

        return {
            "ingested": True,
            "entry": entry,
            "alerts": alerts,
        }

    # ------------------------------------------------------------------
    # Health alerts
    # ------------------------------------------------------------------

    def _check_health_alerts(self, entry: dict, profile: dict) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []

        hr = entry.get("heart_rate")
        if hr is not None and hr > 0:
            if hr > 100:
                alerts.append({
                    "type": "elevated_heart_rate",
                    "value": hr,
                    "message": f"Elevated resting heart rate: {hr} bpm. Consider relaxation.",
                    "priority": "medium",
                })
            elif hr < 45:
                alerts.append({
                    "type": "low_heart_rate",
                    "value": hr,
                    "message": f"Low heart rate: {hr} bpm. Monitor if unusual for you.",
                    "priority": "high",
                })

        spo2 = entry.get("spo2")
        if spo2 is not None and spo2 > 0:
            if spo2 < 92:
                alerts.append({
                    "type": "low_blood_oxygen",
                    "value": spo2,
                    "message": f"Low blood oxygen: {spo2}%. Seek medical attention if persistent.",
                    "priority": "high",
                })

        hrv = entry.get("hrv")
        if hrv is not None and hrv > 0:
            if hrv < 20:
                alerts.append({
                    "type": "low_hrv",
                    "value": hrv,
                    "message": f"Low HRV ({hrv}ms). Prioritize sleep and recovery tonight.",
                    "priority": "medium",
                })

        temp = entry.get("temperature")
        if temp is not None and temp > 0:
            if temp > 38.0:
                alerts.append({
                    "type": "elevated_temperature",
                    "value": temp,
                    "message": f"Elevated body temperature: {temp}°C. Monitor for fever.",
                    "priority": "high",
                })

        return alerts

    # ------------------------------------------------------------------
    # Enhanced sleep intelligence
    # ------------------------------------------------------------------

    def get_sleep_enhancement(self, profile: dict) -> dict[str, Any]:
        """Get enhanced sleep insights from biometric data."""
        self.ensure_shape(profile)
        ft = profile.get("fitness_tracker", {})
        history = ft.get("biometric_history", [])

        if len(history) < 10:
            return {"available": False, "message": "Not enough biometric data yet."}

        recent = history[-50:]
        hr_values = [e.get("heart_rate", 0) for e in recent if e.get("heart_rate", 0) > 0]
        hrv_values = [e.get("hrv", 0) for e in recent if e.get("hrv", 0) > 0]
        spo2_values = [e.get("spo2", 0) for e in recent if e.get("spo2", 0) > 0]

        insights: list[str] = []

        if hrv_values:
            avg_hrv = sum(hrv_values) / len(hrv_values)
            if avg_hrv < 30:
                insights.append("Low HRV suggests high stress. Prioritize sleep tonight.")
            elif avg_hrv > 60:
                insights.append("High HRV indicates good recovery. Great job!")

        if hr_values:
            avg_hr = sum(hr_values) / len(hr_values)
            if avg_hr > 75:
                insights.append("Elevated resting heart rate. Extra sleep may help recovery.")

        if spo2_values:
            avg_spo2 = sum(spo2_values) / len(spo2_values)
            if avg_spo2 < 95:
                insights.append("Blood oxygen slightly low. Consider sleep position and room ventilation.")

        recovery_score = 0
        if hrv_values and hr_values:
            avg_hrv = sum(hrv_values) / len(hrv_values)
            avg_hr = sum(hr_values) / len(hr_values)
            recovery_score = min(100, max(0, int(avg_hrv * 1.2 - (avg_hr - 60) * 0.5)))

        return {
            "available": True,
            "avg_heart_rate": round(sum(hr_values) / len(hr_values), 1) if hr_values else None,
            "avg_hrv": round(sum(hrv_values) / len(hrv_values), 1) if hrv_values else None,
            "avg_spo2": round(sum(spo2_values) / len(spo2_values), 1) if spo2_values else None,
            "recovery_score": recovery_score,
            "insights": insights,
            "data_points": len(recent),
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        ft = profile.get("fitness_tracker", {})
        device = ft.get("connected_device", "")
        return {
            "enabled": ft.get("enabled", False),
            "connected_device": SUPPORTED_DEVICES.get(device, {}).get("name", "") if device else "",
            "device_type": device,
            "last_sync": ft.get("last_sync_at", ""),
            "data_points": len(ft.get("biometric_history", [])),
            "active_alerts": len(ft.get("health_alerts", [])),
        }

    # ------------------------------------------------------------------
    # Garmin Connect direct pull
    # ------------------------------------------------------------------

    def fetch_from_fitbit(
        self,
        profile: dict,
        access_token: str,
        refresh_token: str = "",
        target_date: "date | str | None" = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Pull today's (or *target_date*'s) health data from Fitbit and ingest
        it into *profile*.

        *access_token* and *refresh_token* are the user's OAuth2 tokens
        obtained from the Fitbit consent flow. Client credentials are read
        from ``config.settings`` (FITBIT_CLIENT_ID / FITBIT_CLIENT_SECRET).

        Returns the same shape as ``ingest_biometric_data()``.
        """
        token = str(access_token or "").strip()
        if not token:
            return {"ingested": False, "reason": "No Fitbit access token provided"}

        try:
            from integrations.fitbit_client import build_client_from_settings, _FITBIT_AVAILABLE
            if not _FITBIT_AVAILABLE:
                return {"ingested": False, "reason": "fitbit library not installed"}
            client = build_client_from_settings(token, refresh_token)
        except Exception as exc:
            logger.warning("Fitbit client init failed: %s", exc)
            return {"ingested": False, "reason": str(exc)}

        daily = client.fetch_daily(target_date)
        if not daily.get("available", False):
            return {"ingested": False, "reason": daily.get("reason", "No data returned"), "raw": daily}

        self.ensure_shape(profile)
        if not profile["fitness_tracker"].get("connected_device"):
            self.connect_device(profile, "fitbit")

        result = self.ingest_biometric_data(profile, daily, now)
        result["source"] = "fitbit"
        result["date"] = daily.get("date", "")
        result["fitbit_extras"] = {
            "total_sleep_hours": daily.get("total_sleep_hours"),
            "deep_sleep_hours": daily.get("deep_sleep_hours"),
            "rem_sleep_hours": daily.get("rem_sleep_hours"),
            "sleep_efficiency_pct": daily.get("sleep_efficiency_pct"),
            "active_minutes": daily.get("active_minutes"),
            "distance_km": daily.get("distance_km"),
            "hrv_deep_rmssd": daily.get("hrv_deep_rmssd"),
            "spo2_min": daily.get("spo2_min"),
            "spo2_max": daily.get("spo2_max"),
        }
        return result

    def fetch_from_garmin(
        self,
        profile: dict,
        target_date: "date | str | None" = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Pull today's (or *target_date*'s) health data from Garmin Connect
        and ingest it into *profile*.

        Uses credentials from ``config.settings`` (GARMIN_EMAIL / GARMIN_PASSWORD).
        Falls back gracefully when garminconnect is not installed or unconfigured.

        Returns the same shape as ``ingest_biometric_data()``.
        """
        try:
            from integrations.garmin_client import build_client_from_settings
            client = build_client_from_settings()
            if not client.available:
                return {"ingested": False, "reason": "garminconnect not installed"}
            if not client._email:
                return {"ingested": False, "reason": "GARMIN_EMAIL not configured"}
        except Exception as exc:
            logger.warning("Garmin client init failed: %s", exc)
            return {"ingested": False, "reason": str(exc)}

        daily = client.fetch_daily(target_date)
        if not daily.get("available", False):
            return {"ingested": False, "reason": daily.get("reason", "No data returned"), "raw": daily}

        # Auto-connect device if not already set
        self.ensure_shape(profile)
        if not profile["fitness_tracker"].get("connected_device"):
            self.connect_device(profile, "garmin")

        result = self.ingest_biometric_data(profile, daily, now)
        result["source"] = "garmin"
        result["date"] = daily.get("date", "")
        result["garmin_extras"] = {
            "sleep_score": daily.get("sleep_score"),
            "total_sleep_hours": daily.get("total_sleep_hours"),
            "deep_sleep_hours": daily.get("deep_sleep_hours"),
            "rem_sleep_hours": daily.get("rem_sleep_hours"),
            "body_battery": daily.get("body_battery"),
            "hrv_status": daily.get("hrv_status"),
            "hrv_feedback": daily.get("hrv_feedback"),
            "active_minutes": daily.get("active_minutes"),
        }
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
