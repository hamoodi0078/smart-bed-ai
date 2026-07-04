"""Google Calendar v3 API client.

Wraps ``google-api-python-client`` to fetch events from a user's primary
Google Calendar using OAuth2 access + refresh tokens obtained during mobile
login (the user already signed in with Google via the app).

Public API
----------
GoogleCalendarClient(client_id, client_secret)
    .fetch_events(access_token, refresh_token, *, days_ahead, max_results)
        -> list[dict]   — normalized event dicts compatible with CalendarSync

Normalized event dict keys:
    title, start_time, end_time, all_day, location, is_travel, google_event_id
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("integrations.google_calendar_client")

try:
    from googleapiclient.discovery import build as _build
    from googleapiclient.errors import HttpError as _HttpError

    _GOOGLE_API_AVAILABLE = True
except ImportError:
    _build = None  # type: ignore[assignment]
    _HttpError = Exception
    _GOOGLE_API_AVAILABLE = False

try:
    from google.oauth2.credentials import Credentials as _Credentials

    _GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    _Credentials = None  # type: ignore[assignment]
    _GOOGLE_AUTH_AVAILABLE = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GoogleCalendarClient:
    """Fetch events from Google Calendar v3 API."""

    CALENDAR_ID = "primary"

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        token_uri: str = "https://oauth2.googleapis.com/token",
    ):
        self._client_id = str(client_id or "").strip()
        self._client_secret = str(client_secret or "").strip()
        self._token_uri = str(token_uri or "https://oauth2.googleapis.com/token").strip()

    @property
    def available(self) -> bool:
        return _GOOGLE_API_AVAILABLE and _GOOGLE_AUTH_AVAILABLE

    def _build_service(self, access_token: str, refresh_token: str):
        """Build an authorized Google Calendar service object."""
        if not self.available:
            raise RuntimeError("google-api-python-client or google-auth not installed")

        creds = _Credentials(
            token=access_token,
            refresh_token=refresh_token or None,
            token_uri=self._token_uri,
            client_id=self._client_id or None,
            client_secret=self._client_secret or None,
        )
        return _build("calendar", "v3", credentials=creds, cache_discovery=False)

    def fetch_events(
        self,
        access_token: str,
        refresh_token: str = "",
        *,
        days_ahead: int = 7,
        max_results: int = 50,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return normalized calendar events for the next *days_ahead* days.

        Args:
            access_token:  User's Google OAuth2 access token.
            refresh_token: Optional refresh token for automatic renewal.
            days_ahead:    How many days into the future to fetch (default 7).
            max_results:   Maximum number of events to return (default 50).
            now:           Override current UTC time (for testing).

        Returns:
            List of normalized event dicts; empty list on error.
        """
        if not access_token:
            logger.warning("Google Calendar fetch skipped: no access token")
            return []

        base = now or _utcnow()
        time_min = base.isoformat()
        time_max = (base + timedelta(days=max(1, int(days_ahead)))).isoformat()

        try:
            service = self._build_service(access_token, refresh_token)
            result = (
                service.events()
                .list(
                    calendarId=self.CALENDAR_ID,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=min(250, max(1, int(max_results))),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            items: list[dict] = result.get("items", [])
            logger.info("Google Calendar: fetched %d events", len(items))
            return [self._normalize(item) for item in items]

        except _HttpError as exc:
            logger.warning("Google Calendar HTTP error: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Google Calendar fetch failed: %s", exc)
            return []

    @staticmethod
    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        """Convert a Google Calendar API event object to a CalendarSync-compatible dict."""
        start = item.get("start", {})
        end = item.get("end", {})

        all_day = "date" in start and "dateTime" not in start
        start_time = start.get("dateTime") or start.get("date", "")
        end_time = end.get("dateTime") or end.get("date", "")

        location = str(item.get("location", "") or "").strip()
        title = str(item.get("summary", "") or "").strip()

        # Heuristic: mark as travel if the event has a non-local location
        is_travel = bool(location) and any(
            kw in location.lower()
            for kw in ("airport", "flight", "hotel", "terminal", "مطار", "فندق", "رحلة")
        )

        return {
            "title": title[:200],
            "start_time": start_time,
            "end_time": end_time,
            "all_day": all_day,
            "location": location[:200],
            "is_travel": is_travel,
            "google_event_id": str(item.get("id", "") or ""),
            "html_link": str(item.get("htmlLink", "") or ""),
            "status": str(item.get("status", "confirmed") or "confirmed"),
        }


def build_client_from_settings() -> GoogleCalendarClient:
    """Construct a GoogleCalendarClient from the project settings."""
    from config.settings import settings

    return GoogleCalendarClient(
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        token_uri=settings.google_calendar_token_uri,
    )
