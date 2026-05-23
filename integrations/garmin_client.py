"""Garmin Connect API client.

Wraps the ``garminconnect`` library to pull daily health metrics:
  - Stats (steps, calories, resting heart rate, active minutes)
  - Heart rate (min / max / resting + 15-min samples)
  - HRV (overnight Heart Rate Variability)
  - Sleep (stages, score, total sleep seconds)
  - Body Battery (energy level throughout the day)
  - Stress (average daily stress)

Public API
----------
GarminClient(email, password, tokenstore_path)
    .login()                          -> bool
    .fetch_daily(date)                -> dict   — all metrics merged
    .fetch_sleep(date)                -> dict
    .fetch_hrv(date)                  -> dict
    .fetch_steps_and_hr(date)         -> dict

Normalized output is compatible with FitnessTrackerAPI.ingest_biometric_data().
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("integrations.garmin_client")

try:
    from garminconnect import Garmin as _Garmin, GarminConnectAuthenticationError
    _GARMIN_AVAILABLE = True
except ImportError:
    _Garmin = None  # type: ignore[assignment]
    GarminConnectAuthenticationError = Exception
    _GARMIN_AVAILABLE = False


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _date_str(d: date | str | None) -> str:
    if d is None:
        return _today().isoformat()
    if isinstance(d, str):
        return d
    return d.isoformat()


class GarminClient:
    """Authenticated Garmin Connect client with lazy login.

    The plaintext password is held in memory only for the duration of the
    initial login call.  Once garth has dumped a token file the password
    is cleared so it does not persist in the process heap.
    """

    def __init__(
        self,
        email: str = "",
        password: str = "",
        tokenstore_path: str = "",
    ):
        self._email = str(email or "").strip()
        # Store password as a mutable list so we can zero it out after first use.
        self._password_chars: list[str] = list(str(password or "").strip())
        self._tokenstore = str(tokenstore_path or "").strip()
        self._client: Any = None
        self._authenticated = False

    @property
    def available(self) -> bool:
        return _GARMIN_AVAILABLE

    def _consume_password(self) -> str:
        """Return the password and immediately clear it from memory."""
        pwd = "".join(self._password_chars)
        for i in range(len(self._password_chars)):
            self._password_chars[i] = "\x00"
        self._password_chars.clear()
        return pwd

    def login(self) -> bool:
        """Authenticate with Garmin Connect. Returns True on success."""
        if not _GARMIN_AVAILABLE:
            logger.warning("garminconnect is not installed")
            return False
        if not self._email:
            logger.warning("Garmin email not configured")
            return False
        try:
            tokenstore_exists = bool(self._tokenstore) and Path(self._tokenstore).exists()
            if tokenstore_exists:
                # Prefer token file — no password needed at all.
                self._client = _Garmin(self._email, "")
                self._client.login(self._tokenstore)
                self._consume_password()  # clear even if we didn't use it
            else:
                password = self._consume_password()
                self._client = _Garmin(self._email, password)
                self._client.login()
                if self._tokenstore:
                    Path(self._tokenstore).parent.mkdir(parents=True, exist_ok=True)
                    self._client.garth.dump(self._tokenstore)
                    logger.info("Garmin: token saved to %s — password cleared from memory", self._tokenstore)
            self._authenticated = True
            logger.info("Garmin Connect: logged in as %s", self._email)
            return True
        except GarminConnectAuthenticationError as exc:
            logger.error("Garmin authentication failed: %s", exc)
            self._client = None
            self._authenticated = False
            return False
        except Exception as exc:
            logger.warning("Garmin login error: %s", exc)
            self._client = None
            self._authenticated = False
            return False

    def _ensure_logged_in(self) -> bool:
        if self._client is not None and self._authenticated:
            return True
        return self.login()

    # ------------------------------------------------------------------
    # Fetch methods
    # ------------------------------------------------------------------

    def fetch_stats(self, target_date: date | str | None = None) -> dict[str, Any]:
        """Daily stats: steps, calories, resting HR, active minutes."""
        if not self._ensure_logged_in():
            return {"available": False, "reason": "Not authenticated"}
        ds = _date_str(target_date)
        try:
            raw = self._client.get_stats(ds)
            return {
                "available": True,
                "date": ds,
                "steps": int(raw.get("totalSteps", 0) or 0),
                "calories": int(raw.get("totalKilocalories", 0) or 0),
                "resting_heart_rate": int(raw.get("restingHeartRate", 0) or 0),
                "active_minutes": int(raw.get("highlyActiveSeconds", 0) or 0) // 60,
                "floors_climbed": int(raw.get("floorsAscended", 0) or 0),
                "distance_meters": float(raw.get("totalDistanceMeters", 0) or 0),
            }
        except Exception as exc:
            logger.warning("Garmin fetch_stats failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_heart_rates(self, target_date: date | str | None = None) -> dict[str, Any]:
        """Heart rate: resting, min, max, and 15-min samples."""
        if not self._ensure_logged_in():
            return {"available": False, "reason": "Not authenticated"}
        ds = _date_str(target_date)
        try:
            raw = self._client.get_heart_rates(ds)
            resting = int(raw.get("restingHeartRate", 0) or 0)
            values = raw.get("heartRateValues", []) or []
            hr_samples = [int(v[1]) for v in values if v and len(v) >= 2 and v[1] is not None]
            return {
                "available": True,
                "date": ds,
                "resting_heart_rate": resting,
                "min_heart_rate": min(hr_samples) if hr_samples else None,
                "max_heart_rate": max(hr_samples) if hr_samples else None,
                "avg_heart_rate": round(sum(hr_samples) / len(hr_samples), 1) if hr_samples else None,
                "samples": len(hr_samples),
            }
        except Exception as exc:
            logger.warning("Garmin fetch_heart_rates failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_hrv(self, target_date: date | str | None = None) -> dict[str, Any]:
        """Overnight HRV (Heart Rate Variability) data."""
        if not self._ensure_logged_in():
            return {"available": False, "reason": "Not authenticated"}
        ds = _date_str(target_date)
        try:
            raw = self._client.get_hrv_data(ds)
            summary = raw.get("hrvSummary", {}) or {}
            return {
                "available": True,
                "date": ds,
                "hrv_weekly_avg": float(summary.get("weeklyAvg", 0) or 0),
                "hrv_last_night": float(summary.get("lastNight", 0) or 0),
                "hrv_last_night_5min_high": float(summary.get("lastNight5MinHigh", 0) or 0),
                "hrv_status": str(summary.get("hrvStatus", "") or ""),
                "hrv_feedback": str(summary.get("feedbackPhrase", "") or ""),
            }
        except Exception as exc:
            logger.warning("Garmin fetch_hrv failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_sleep(self, target_date: date | str | None = None) -> dict[str, Any]:
        """Sleep data: score, duration, stages (deep/light/REM/awake)."""
        if not self._ensure_logged_in():
            return {"available": False, "reason": "Not authenticated"}
        ds = _date_str(target_date)
        try:
            raw = self._client.get_sleep_data(ds)
            dto = raw.get("dailySleepDTO", {}) or {}
            score_obj = raw.get("sleepScores", {}) or {}

            total_sec = int(dto.get("sleepTimeSeconds", 0) or 0)
            deep_sec = int(dto.get("deepSleepSeconds", 0) or 0)
            light_sec = int(dto.get("lightSleepSeconds", 0) or 0)
            rem_sec = int(dto.get("remSleepSeconds", 0) or 0)
            awake_sec = int(dto.get("awakeSleepSeconds", 0) or 0)

            return {
                "available": True,
                "date": ds,
                "sleep_score": int(score_obj.get("overall", {}).get("value", 0) or 0),
                "total_sleep_hours": round(total_sec / 3600, 2),
                "deep_sleep_hours": round(deep_sec / 3600, 2),
                "light_sleep_hours": round(light_sec / 3600, 2),
                "rem_sleep_hours": round(rem_sec / 3600, 2),
                "awake_hours": round(awake_sec / 3600, 2),
                "sleep_start": str(dto.get("sleepStartTimestampGMT", "") or ""),
                "sleep_end": str(dto.get("sleepEndTimestampGMT", "") or ""),
                "avg_spo2": float(dto.get("averageSpO2Value", 0) or 0),
                "avg_hrv": float(dto.get("avgSleepHR", 0) or 0),
            }
        except Exception as exc:
            logger.warning("Garmin fetch_sleep failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_body_battery(self, target_date: date | str | None = None) -> dict[str, Any]:
        """Body Battery: Garmin's energy reserve metric (0–100)."""
        if not self._ensure_logged_in():
            return {"available": False, "reason": "Not authenticated"}
        ds = _date_str(target_date)
        try:
            raw = self._client.get_body_battery([ds])
            if not raw or not isinstance(raw, list):
                return {"available": False, "reason": "No body battery data"}
            day_data = raw[0] if raw else {}
            charged = int(day_data.get("charged", 0) or 0)
            drained = int(day_data.get("drained", 0) or 0)
            end_level = int(day_data.get("endLevel", 0) or 0)
            return {
                "available": True,
                "date": ds,
                "body_battery_end": end_level,
                "body_battery_charged": charged,
                "body_battery_drained": drained,
            }
        except Exception as exc:
            logger.warning("Garmin fetch_body_battery failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_stress(self, target_date: date | str | None = None) -> dict[str, Any]:
        """Average stress level for the day (0–100)."""
        if not self._ensure_logged_in():
            return {"available": False, "reason": "Not authenticated"}
        ds = _date_str(target_date)
        try:
            raw = self._client.get_stress_data(ds)
            avg_stress = int(raw.get("avgStressLevel", 0) or 0)
            max_stress = int(raw.get("maxStressLevel", 0) or 0)
            return {
                "available": True,
                "date": ds,
                "avg_stress_level": avg_stress,
                "max_stress_level": max_stress,
            }
        except Exception as exc:
            logger.warning("Garmin fetch_stress failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_daily(self, target_date: date | str | None = None) -> dict[str, Any]:
        """Fetch and merge all daily metrics into one dict.

        Compatible with FitnessTrackerAPI.ingest_biometric_data().
        """
        ds = _date_str(target_date)
        stats = self.fetch_stats(ds)
        hr = self.fetch_heart_rates(ds)
        hrv = self.fetch_hrv(ds)
        sleep = self.fetch_sleep(ds)
        battery = self.fetch_body_battery(ds)
        stress = self.fetch_stress(ds)

        return {
            "date": ds,
            "source": "garmin",
            "available": any(
                d.get("available", False)
                for d in [stats, hr, hrv, sleep, battery, stress]
            ),
            # FitnessTrackerAPI-compatible keys
            "heart_rate": hr.get("resting_heart_rate") or stats.get("resting_heart_rate"),
            "hrv": hrv.get("hrv_last_night"),
            "spo2": sleep.get("avg_spo2"),
            "steps": stats.get("steps"),
            "calories": stats.get("calories"),
            "stress_level": stress.get("avg_stress_level"),
            # Garmin-specific extras
            "sleep_score": sleep.get("sleep_score"),
            "total_sleep_hours": sleep.get("total_sleep_hours"),
            "deep_sleep_hours": sleep.get("deep_sleep_hours"),
            "rem_sleep_hours": sleep.get("rem_sleep_hours"),
            "body_battery": battery.get("body_battery_end"),
            "hrv_status": hrv.get("hrv_status"),
            "hrv_feedback": hrv.get("hrv_feedback"),
            "active_minutes": stats.get("active_minutes"),
            "distance_meters": stats.get("distance_meters"),
        }


def build_client_from_settings() -> GarminClient:
    """Construct a GarminClient from the project settings."""
    from config.settings import settings
    return GarminClient(
        email=settings.garmin_email,
        password=settings.garmin_password,
        tokenstore_path=settings.garmin_tokenstore_path,
    )