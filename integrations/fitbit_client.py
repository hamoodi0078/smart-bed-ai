"""Fitbit Web API client.

Wraps the ``fitbit`` (python-fitbit) library to pull daily health metrics
using a user's OAuth2 access + refresh tokens obtained via the Fitbit OAuth2
consent flow initiated by the mobile app.

Public API
----------
FitbitClient(client_id, client_secret, access_token, refresh_token)
    .fetch_daily(date)        -> dict   — all metrics merged
    .fetch_sleep(date)        -> dict
    .fetch_heart_rate(date)   -> dict
    .fetch_activity(date)     -> dict
    .fetch_spo2(date)         -> dict
    .fetch_hrv(date)          -> dict

auth helpers (no client instance needed):
    build_auth_url(client_id, redirect_uri, scopes) -> str
    exchange_code(client_id, client_secret, code, redirect_uri) -> dict

Normalized output is compatible with FitnessTrackerAPI.ingest_biometric_data().
"""

from __future__ import annotations

import base64
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger("integrations.fitbit_client")

_REFRESH_BEFORE_EXPIRY_SECONDS = 300  # refresh if token expires within 5 minutes

try:
    import fitbit as _fitbit_lib
    _FITBIT_AVAILABLE = True
except ImportError:
    _fitbit_lib = None  # type: ignore[assignment]
    _FITBIT_AVAILABLE = False

_FITBIT_SCOPES = [
    "activity", "heartrate", "sleep", "oxygen_saturation",
    "respiratory_rate", "profile", "settings",
]
_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
_AUTH_URL = "https://www.fitbit.com/oauth2/authorize"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _date_str(d: date | str | None) -> str:
    if d is None:
        return _today()
    if isinstance(d, str):
        return d
    return d.isoformat()


def build_auth_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str] | None = None,
) -> str:
    """Return the Fitbit OAuth2 authorization URL to redirect the user to."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": " ".join(scopes or _FITBIT_SCOPES),
        "redirect_uri": redirect_uri,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange an OAuth2 authorization code for access + refresh tokens.

    Returns dict with keys: access_token, refresh_token, expires_in, user_id.
    """
    try:
        import requests as _requests
        import base64 as _base64

        credentials = _base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        resp = _requests.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": client_id,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Fitbit token exchange failed: %s", exc)
        return {"error": str(exc)}


class FitbitClient:
    """Authenticated Fitbit Web API client."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str = "",
        *,
        expires_at: datetime | None = None,
        expires_in: int | None = None,
        on_token_refresh: "Any | None" = None,
    ):
        self._client_id = str(client_id or "").strip()
        self._client_secret = str(client_secret or "").strip()
        self._access_token = str(access_token or "").strip()
        self._refresh_token = str(refresh_token or "").strip()
        self._on_token_refresh = on_token_refresh
        self._client: Any = None

        # Expiry tracking — prefer explicit datetime, then compute from expires_in
        if expires_at is not None:
            self._expires_at: datetime | None = expires_at
        elif expires_in is not None:
            self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        else:
            self._expires_at = None  # unknown — will refresh on first 401

    @property
    def available(self) -> bool:
        return _FITBIT_AVAILABLE

    def _expires_soon(self) -> bool:
        """Return True if the access token is expired or expires within the buffer window."""
        if self._expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self._expires_at - timedelta(seconds=_REFRESH_BEFORE_EXPIRY_SECONDS)

    def refresh_tokens(self) -> bool:
        """Explicitly refresh the access token using the refresh token.

        Updates internal state and calls on_token_refresh if provided.
        Returns True on success, False on failure.
        """
        if not self._refresh_token:
            logger.warning("Fitbit: cannot refresh — no refresh token stored")
            return False
        if not (self._client_id and self._client_secret):
            logger.warning("Fitbit: cannot refresh — missing client_id/client_secret")
            return False

        try:
            import requests as _requests
            credentials = base64.b64encode(
                f"{self._client_id}:{self._client_secret}".encode()
            ).decode()
            resp = _requests.post(
                _TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            self._access_token = str(data.get("access_token", "") or "")
            new_refresh = str(data.get("refresh_token", "") or "")
            if new_refresh:
                self._refresh_token = new_refresh
            expires_in = int(data.get("expires_in", 3600) or 3600)
            self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Invalidate the cached client so it gets rebuilt with the new token
            self._client = None

            if callable(self._on_token_refresh):
                try:
                    self._on_token_refresh(data)
                except Exception as cb_exc:
                    logger.warning("Fitbit on_token_refresh callback error: %s", cb_exc)

            logger.info("Fitbit token refreshed successfully; expires at %s", self._expires_at)
            return True

        except Exception as exc:
            logger.warning("Fitbit token refresh failed: %s", exc)
            return False

    def _get_client(self):
        if not _FITBIT_AVAILABLE:
            raise RuntimeError("fitbit library not installed")
        if not self._access_token:
            raise RuntimeError("No Fitbit access token provided")

        # Proactively refresh before the token expires to avoid mid-request failures
        if self._expires_soon():
            logger.debug("Fitbit access token expiring soon — refreshing proactively")
            self.refresh_tokens()

        if self._client is None:
            self._client = _fitbit_lib.Fitbit(
                self._client_id,
                self._client_secret,
                access_token=self._access_token,
                refresh_token=self._refresh_token or None,
                refresh_cb=self._on_token_refresh,
            )
        return self._client

    # ------------------------------------------------------------------
    # Fetch methods
    # ------------------------------------------------------------------

    def fetch_activity(self, target_date: "date | str | None" = None) -> dict[str, Any]:
        """Steps, calories, active minutes, distance."""
        ds = _date_str(target_date)
        try:
            client = self._get_client()
            raw = client.activities(date=ds)
            summary = raw.get("summary", {})
            return {
                "available": True,
                "date": ds,
                "steps": int(summary.get("steps", 0) or 0),
                "calories": int(summary.get("caloriesOut", 0) or 0),
                "active_minutes": int(summary.get("fairlyActiveMinutes", 0) or 0)
                                 + int(summary.get("veryActiveMinutes", 0) or 0),
                "distance_km": float(
                    next(
                        (d["distance"] for d in summary.get("distances", []) if d.get("activity") == "total"),
                        0,
                    )
                ),
                "floors_climbed": int(summary.get("floors", 0) or 0),
                "resting_heart_rate": int(summary.get("restingHeartRate", 0) or 0),
            }
        except Exception as exc:
            logger.warning("Fitbit fetch_activity failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_heart_rate(self, target_date: "date | str | None" = None) -> dict[str, Any]:
        """Resting heart rate and zone data."""
        ds = _date_str(target_date)
        try:
            client = self._get_client()
            raw = client.intraday_time_series(
                "activities/heart",
                base_date=ds,
                detail_level="1min",
            )
            dataset = raw.get("activities-heart-intraday", {}).get("dataset", [])
            values = [int(p["value"]) for p in dataset if p.get("value") is not None]

            activities_heart = raw.get("activities-heart", [])
            resting_hr = 0
            if activities_heart:
                resting_hr = int(activities_heart[0].get("value", {}).get("restingHeartRate", 0) or 0)

            return {
                "available": True,
                "date": ds,
                "resting_heart_rate": resting_hr,
                "avg_heart_rate": round(sum(values) / len(values), 1) if values else None,
                "min_heart_rate": min(values) if values else None,
                "max_heart_rate": max(values) if values else None,
                "samples": len(values),
            }
        except Exception as exc:
            logger.warning("Fitbit fetch_heart_rate failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_sleep(self, target_date: "date | str | None" = None) -> dict[str, Any]:
        """Sleep stages, duration, efficiency, and score."""
        ds = _date_str(target_date)
        try:
            client = self._get_client()
            raw = client.sleep(date=ds)
            summary = raw.get("summary", {})
            stages = summary.get("stages", {})
            sleep_records = raw.get("sleep", [])
            main_sleep = next((s for s in sleep_records if s.get("isMainSleep")), {})

            total_min = int(summary.get("totalMinutesAsleep", 0) or 0)
            time_in_bed = int(summary.get("totalTimeInBed", 0) or 0)
            efficiency = int(main_sleep.get("efficiency", 0) or 0)

            return {
                "available": True,
                "date": ds,
                "total_sleep_hours": round(total_min / 60, 2),
                "time_in_bed_hours": round(time_in_bed / 60, 2),
                "sleep_efficiency_pct": efficiency,
                "deep_sleep_hours": round(int(stages.get("deep", 0) or 0) / 60, 2),
                "light_sleep_hours": round(int(stages.get("light", 0) or 0) / 60, 2),
                "rem_sleep_hours": round(int(stages.get("rem", 0) or 0) / 60, 2),
                "awake_hours": round(int(stages.get("wake", 0) or 0) / 60, 2),
                "sleep_start": str(main_sleep.get("startTime", "") or ""),
                "sleep_end": str(main_sleep.get("endTime", "") or ""),
                "awakenings": int(main_sleep.get("minutesAwake", 0) or 0),
            }
        except Exception as exc:
            logger.warning("Fitbit fetch_sleep failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_spo2(self, target_date: "date | str | None" = None) -> dict[str, Any]:
        """Blood oxygen saturation (SpO2) — daily average."""
        ds = _date_str(target_date)
        try:
            client = self._get_client()
            raw = client.make_request(f"https://api.fitbit.com/1/user/-/spo2/date/{ds}.json")
            avg = float(raw.get("value", {}).get("avg", 0) or 0)
            return {
                "available": avg > 0,
                "date": ds,
                "spo2_avg": avg,
                "spo2_min": float(raw.get("value", {}).get("min", 0) or 0),
                "spo2_max": float(raw.get("value", {}).get("max", 0) or 0),
            }
        except Exception as exc:
            logger.warning("Fitbit fetch_spo2 failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_hrv(self, target_date: "date | str | None" = None) -> dict[str, Any]:
        """Heart Rate Variability (HRV) daily summary."""
        ds = _date_str(target_date)
        try:
            client = self._get_client()
            raw = client.make_request(f"https://api.fitbit.com/1/user/-/hrv/date/{ds}.json")
            hrv_data = raw.get("hrv", [])
            if not hrv_data:
                return {"available": False, "date": ds, "reason": "No HRV data"}
            daily = hrv_data[0].get("value", {}) if hrv_data else {}
            return {
                "available": True,
                "date": ds,
                "hrv_daily_rmssd": float(daily.get("dailyRmssd", 0) or 0),
                "hrv_deep_rmssd": float(daily.get("deepRmssd", 0) or 0),
            }
        except Exception as exc:
            logger.warning("Fitbit fetch_hrv failed (%s): %s", ds, exc)
            return {"available": False, "reason": str(exc)}

    def fetch_daily(self, target_date: "date | str | None" = None) -> dict[str, Any]:
        """Fetch and merge all daily metrics into one dict.

        Compatible with FitnessTrackerAPI.ingest_biometric_data().
        """
        ds = _date_str(target_date)
        activity = self.fetch_activity(ds)
        hr = self.fetch_heart_rate(ds)
        sleep = self.fetch_sleep(ds)
        spo2 = self.fetch_spo2(ds)
        hrv = self.fetch_hrv(ds)

        return {
            "date": ds,
            "source": "fitbit",
            "available": any(
                d.get("available", False)
                for d in [activity, hr, sleep, spo2, hrv]
            ),
            # FitnessTrackerAPI-compatible keys
            "heart_rate": hr.get("resting_heart_rate") or activity.get("resting_heart_rate"),
            "hrv": hrv.get("hrv_daily_rmssd"),
            "spo2": spo2.get("spo2_avg"),
            "steps": activity.get("steps"),
            "calories": activity.get("calories"),
            # Fitbit-specific extras
            "total_sleep_hours": sleep.get("total_sleep_hours"),
            "deep_sleep_hours": sleep.get("deep_sleep_hours"),
            "rem_sleep_hours": sleep.get("rem_sleep_hours"),
            "sleep_efficiency_pct": sleep.get("sleep_efficiency_pct"),
            "active_minutes": activity.get("active_minutes"),
            "distance_km": activity.get("distance_km"),
            "hrv_deep_rmssd": hrv.get("hrv_deep_rmssd"),
            "spo2_min": spo2.get("spo2_min"),
            "spo2_max": spo2.get("spo2_max"),
        }


def build_client_from_settings(
    access_token: str,
    refresh_token: str = "",
    expires_at: datetime | None = None,
    expires_in: int | None = None,
    on_token_refresh: Any | None = None,
) -> FitbitClient:
    """Construct a FitbitClient from project settings + user tokens."""
    from config.settings import settings
    return FitbitClient(
        client_id=settings.fitbit_client_id,
        client_secret=settings.fitbit_client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        expires_in=expires_in,
        on_token_refresh=on_token_refresh,
    )