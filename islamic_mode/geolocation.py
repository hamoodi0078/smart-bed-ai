"""Geolocation service to automatically detect user's location for prayer times."""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests


logger = logging.getLogger(__name__)


class GeolocationService:
    """Service to detect user's location using IP-based geolocation APIs."""

    # Free IP geolocation APIs (no key required)
    IP_API_URL = "http://ip-api.com/json/"
    IPAPI_URL = "https://ipapi.co/json/"

    def __init__(self, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds

    def get_location_from_ip(self) -> Optional[dict]:
        """
        Automatically detect location from IP address.

        Returns dict with keys: city, country, latitude, longitude, timezone
        Returns None if detection fails.
        """
        # Try primary API first
        location = self._try_ip_api()
        if location:
            return location

        # Fallback to secondary API
        location = self._try_ipapi()
        if location:
            return location

        logger.warning("All geolocation services failed to detect location")
        return None

    def _try_ip_api(self) -> Optional[dict]:
        """Try ip-api.com service."""
        try:
            response = requests.get(
                self.IP_API_URL,
                timeout=self.timeout_seconds,
                params={"fields": "status,country,city,lat,lon,timezone"},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.debug("ip-api.com returned non-success status")
                return None

            return {
                "city": str(data.get("city", "") or ""),
                "country": str(data.get("country", "") or ""),
                "latitude": float(data.get("lat", 0.0)),
                "longitude": float(data.get("lon", 0.0)),
                "timezone": str(data.get("timezone", "") or ""),
                "source": "ip-api.com",
            }
        except Exception as e:
            logger.debug(f"ip-api.com geolocation failed: {e}")
            return None

    def _try_ipapi(self) -> Optional[dict]:
        """Try ipapi.co service as fallback."""
        try:
            response = requests.get(
                self.IPAPI_URL,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "DanahSmartBed/1.0"},
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                logger.debug(f"ipapi.co returned error: {data.get('reason', '')}")
                return None

            return {
                "city": str(data.get("city", "") or ""),
                "country": str(data.get("country_name", "") or ""),
                "latitude": float(data.get("latitude", 0.0)),
                "longitude": float(data.get("longitude", 0.0)),
                "timezone": str(data.get("timezone", "") or ""),
                "source": "ipapi.co",
            }
        except Exception as e:
            logger.debug(f"ipapi.co geolocation failed: {e}")
            return None

    def get_location_with_fallback(
        self,
        default_city: str = "Kuwait City",
        default_country: str = "Kuwait",
        default_latitude: Optional[float] = None,
        default_longitude: Optional[float] = None,
    ) -> dict:
        """
        Get location with fallback to defaults if auto-detection fails.

        Returns dict with: city, country, latitude, longitude, timezone, auto_detected
        """
        location = self.get_location_from_ip()

        if location:
            return {**location, "auto_detected": True}

        # Return defaults if auto-detection failed
        return {
            "city": default_city,
            "country": default_country,
            "latitude": default_latitude,
            "longitude": default_longitude,
            "timezone": "",
            "source": "config_defaults",
            "auto_detected": False,
        }
