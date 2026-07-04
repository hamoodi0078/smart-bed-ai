import calendar
from datetime import datetime, timedelta
from difflib import get_close_matches
import re
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from time_utils import utcnow


COUNTRY_TIMEZONE_ALIASES = {
    "pakistan": "Asia/Karachi",
    "kuwait": "Asia/Kuwait",
    "india": "Asia/Kolkata",
    "saudi": "Asia/Riyadh",
    "saudi arabia": "Asia/Riyadh",
    "uae": "Asia/Dubai",
    "united arab emirates": "Asia/Dubai",
    "uk": "Europe/London",
    "united kingdom": "Europe/London",
    "usa": "America/New_York",
    "united states": "America/New_York",
    "canada": "America/Toronto",
    "qatar": "Asia/Qatar",
    "oman": "Asia/Muscat",
    "bahrain": "Asia/Bahrain",
    "egypt": "Africa/Cairo",
    "turkey": "Europe/Istanbul",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris",
    "italy": "Europe/Rome",
    "spain": "Europe/Madrid",
    "australia": "Australia/Sydney",
    "japan": "Asia/Tokyo",
    "china": "Asia/Shanghai",
    "russia": "Europe/Moscow",
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "dubai": "Asia/Dubai",
    "lahore": "Asia/Karachi",
    "karachi": "Asia/Karachi",
    "london": "Europe/London",
    "berlin": "Europe/Berlin",
    "tokyo": "Asia/Tokyo",
    "germenay": "Europe/Berlin",
}


def _has_word(text: str, word: str) -> bool:
    return bool(re.search(rf"\b{re.escape(word)}\b", text))


def _is_eid_al_adha_query(lower: str) -> bool:
    adha_markers = (
        "eid ul adha",
        "eid al adha",
        "eid al-adha",
        "eid ul-adha",
        "bakra eid",
        "bakrid",
        "bakra",
        "qurbani",
        "qurban",
        "adha",
    )
    return any(marker in lower for marker in adha_markers)


def _is_ramadan_day_query(lower: str) -> bool:
    markers = (
        "what day of ramadan",
        "which day of ramadan",
        "day of ramadan",
        "ramadan day",
        "how many days of ramadan",
        "كم يوم من رمضان",
        "اي يوم من رمضان",
        "أي يوم من رمضان",
    )
    return any(marker in lower for marker in markers)


def _extract_requested_year(lower: str, now_year: int) -> Optional[int]:
    year_match = re.search(r"\b(19\d{2}|20\d{2}|21\d{2})\b", lower)
    if year_match:
        return int(year_match.group(1))

    years_ago_match = re.search(r"\b(\d{1,2})\s+years?\s+ago\b", lower)
    if years_ago_match:
        year_offset = int(years_ago_match.group(1))
        if year_offset >= 0:
            return now_year - year_offset

    relative_year_match = re.search(
        r"\b(?:in\s+|after\s+)?(\d{1,2})\s+years?(?:\s+from\s+now)?\b",
        lower,
    )
    if relative_year_match:
        year_offset = int(relative_year_match.group(1))
        if year_offset >= 0:
            return now_year + year_offset

    if "next year" in lower or "coming year" in lower:
        return now_year + 1

    if "last year" in lower or "previous year" in lower or "past year" in lower:
        return now_year - 1

    if "this year" in lower or "current year" in lower:
        return now_year

    return None


def _find_hijri_for_gregorian_date(
    target_date: datetime, timeout_seconds: int = 10
) -> tuple[Optional[int], Optional[int]]:
    try:
        response = requests.get(
            f"https://api.aladhan.com/v1/gToHCalendar/{target_date.month}/{target_date.year}",
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("data", []) if isinstance(body, dict) else []
        target_text = target_date.strftime("%d-%m-%Y")
        for item in items:
            gregorian = item.get("gregorian", {}) if isinstance(item, dict) else {}
            if str(gregorian.get("date", "")).strip() != target_text:
                continue
            hijri = item.get("hijri", {}) if isinstance(item, dict) else {}
            month_number = (
                ((hijri.get("month") or {}).get("number")) if isinstance(hijri, dict) else None
            )
            day_text = str(hijri.get("day", "")).strip() if isinstance(hijri, dict) else ""
            try:
                day_number = int(day_text)
            except ValueError:
                day_number = None
            return month_number, day_number
    except Exception:
        pass
    return None, None


FALLBACK_UTC_OFFSETS = {
    "Asia/Karachi": 5,
    "Asia/Kuwait": 3,
    "Asia/Kolkata": 5.5,
    "Asia/Riyadh": 3,
    "Asia/Dubai": 4,
    "Europe/London": 0,
    "America/New_York": -5,
    "America/Toronto": -5,
    "Europe/Berlin": 1,
    "Europe/Paris": 1,
    "Europe/Rome": 1,
    "Europe/Madrid": 1,
    "Europe/Istanbul": 3,
    "Africa/Cairo": 2,
    "Asia/Tokyo": 9,
    "Asia/Shanghai": 8,
    "Europe/Moscow": 3,
    "Australia/Sydney": 10,
}


def _extract_location_from_time_query(lower: str) -> str:
    patterns = [
        r"time\s+in\s+([a-zA-Z\s\-']+)",
        r"time\s+of\s+([a-zA-Z\s\-']+)",
        r"time\s+at\s+([a-zA-Z\s\-']+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            return match.group(1).strip(" ?.,!")
    return ""


def _resolve_timezone_from_location(location: str, timeout_seconds: int = 10) -> Optional[str]:
    key = (location or "").strip().lower()
    if not key:
        return None

    if key in COUNTRY_TIMEZONE_ALIASES:
        return COUNTRY_TIMEZONE_ALIASES[key]

    similar = get_close_matches(key, COUNTRY_TIMEZONE_ALIASES.keys(), n=1, cutoff=0.78)
    if similar:
        return COUNTRY_TIMEZONE_ALIASES[similar[0]]

    try:
        response = requests.get(
            f"https://restcountries.com/v3.1/name/{key}?fields=name,timezones",
            timeout=timeout_seconds,
        )
        if response.status_code < 400:
            body = response.json()
            if isinstance(body, list) and body:
                timezones = body[0].get("timezones", [])
                if timezones:
                    return timezones[0]
    except Exception:
        pass

    # Third fallback: city geocoding with timezone from Open-Meteo
    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": key, "count": 1, "language": "en", "format": "json"},
            timeout=timeout_seconds,
        )
        if response.status_code < 400:
            body = response.json()
            results = body.get("results", [])
            if results:
                timezone = results[0].get("timezone")
                if timezone:
                    return timezone
    except Exception:
        pass

    return None


def _find_hijri_month_day_gregorian(
    hijri_month_number: int,
    hijri_day_number: int,
    year: int,
    timeout_seconds: int = 10,
) -> Optional[datetime]:
    for month in range(1, 13):
        try:
            response = requests.get(
                f"https://api.aladhan.com/v1/gToHCalendar/{month}/{year}",
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            items = body.get("data", []) if isinstance(body, dict) else []
            for item in items:
                hijri = item.get("hijri", {}) if isinstance(item, dict) else {}
                h_month = (
                    ((hijri.get("month") or {}).get("number")) if isinstance(hijri, dict) else None
                )
                h_day = str(hijri.get("day", "")).strip() if isinstance(hijri, dict) else ""
                if h_month == hijri_month_number and h_day == str(hijri_day_number):
                    gregorian = item.get("gregorian", {}) if isinstance(item, dict) else {}
                    date_text = str(gregorian.get("date", "")).strip()  # DD-MM-YYYY
                    if date_text:
                        return datetime.strptime(date_text, "%d-%m-%Y")
        except Exception:
            continue
    return None


def _find_ramadan_start_gregorian(year: int, timeout_seconds: int = 10) -> Optional[datetime]:
    return _find_hijri_month_day_gregorian(9, 1, year, timeout_seconds=timeout_seconds)


def _find_eid_al_fitr_gregorian(year: int, timeout_seconds: int = 10) -> Optional[datetime]:
    # Eid al-Fitr begins on 1 Shawwal (Hijri month 10).
    return _find_hijri_month_day_gregorian(10, 1, year, timeout_seconds=timeout_seconds)


def _find_eid_al_adha_gregorian(year: int, timeout_seconds: int = 10) -> Optional[datetime]:
    # Eid al-Adha begins on 10 Dhu al-Hijjah (Hijri month 12).
    return _find_hijri_month_day_gregorian(12, 10, year, timeout_seconds=timeout_seconds)


def fetch_online_datetime(
    timezone: str = "Asia/Kuwait", timeout_seconds: int = 10
) -> Optional[datetime]:
    # Primary source: worldtimeapi
    try:
        response = requests.get(
            f"https://worldtimeapi.org/api/timezone/{timezone}", timeout=timeout_seconds
        )
        response.raise_for_status()
        body = response.json()
        dt_text = body.get("datetime")
        if dt_text:
            return datetime.fromisoformat(dt_text)
    except Exception:
        pass

    # Secondary source: timeapi.io
    try:
        response = requests.get(
            "https://timeapi.io/api/Time/current/zone",
            params={"timeZone": timezone},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        dt_text = body.get("dateTime") or body.get("date_time")
        if dt_text:
            return datetime.fromisoformat(str(dt_text).replace("Z", "+00:00"))
    except Exception:
        pass

    return None


def get_online_calendar_answer(
    user_text: str,
    timezone: str = "Asia/Kuwait",
    timeout_seconds: int = 10,
) -> Optional[str]:
    lower = user_text.lower().strip()

    has_calendar_intent = (
        _has_word(lower, "calendar")
        or _has_word(lower, "date")
        or _has_word(lower, "time")
        or _has_word(lower, "year")
        or _has_word(lower, "day")
        or _has_word(lower, "tomorrow")
        or _has_word(lower, "tommorow")
        or _has_word(lower, "eid")
        or "bakra" in lower
        or "bakrid" in lower
        or "adha" in lower
        or "qurbani" in lower
        or _has_word(lower, "ramadan")
        or "new year" in lower
    )
    if not has_calendar_intent:
        return None

    timezone_for_query = timezone
    if _has_word(lower, "time"):
        location = _extract_location_from_time_query(lower)
        resolved_timezone = _resolve_timezone_from_location(
            location, timeout_seconds=timeout_seconds
        )
        if resolved_timezone:
            timezone_for_query = resolved_timezone

    online_now = fetch_online_datetime(timezone=timezone_for_query, timeout_seconds=timeout_seconds)
    if online_now:
        now = online_now
    else:
        try:
            now = datetime.now(ZoneInfo(timezone_for_query))
        except Exception:
            offset_hours = FALLBACK_UTC_OFFSETS.get(timezone_for_query)
            if offset_hours is None:
                now = datetime.now()
            else:
                now = utcnow() + timedelta(hours=offset_hours)

    source = "online" if online_now else "local fallback"
    requested_year = _extract_requested_year(lower, now.year)

    reference_date = now.date()
    if requested_year is not None:
        max_day = calendar.monthrange(requested_year, reference_date.month)[1]
        safe_day = min(reference_date.day, max_day)
        reference_date = reference_date.replace(year=requested_year, day=safe_day)

    if _has_word(lower, "year") and (
        _has_word(lower, "current") or "what year" in lower or "which year" in lower
    ):
        return f"The current year is {now.year}."

    if "new year" in lower:
        if requested_year is not None:
            next_new_year = datetime(requested_year, 1, 1)
        else:
            next_new_year = datetime(now.year, 1, 1)
            if now.date() > next_new_year.date():
                next_new_year = datetime(now.year + 1, 1, 1)
        return f"New Year's Day is on {next_new_year.strftime('%A, %B %d, %Y')} ({source})."

    if _has_word(lower, "eid") or _is_eid_al_adha_query(lower):
        current_year = now.year
        is_adha_query = _is_eid_al_adha_query(lower)
        if is_adha_query:
            eid_lookup = _find_eid_al_adha_gregorian
            eid_label = "Eid al-Adha"
        else:
            eid_lookup = _find_eid_al_fitr_gregorian
            eid_label = "Eid al-Fitr"

        if requested_year is not None:
            specific = eid_lookup(requested_year, timeout_seconds=timeout_seconds)
            if specific is not None:
                return (
                    f"{eid_label} is expected to begin on "
                    f"{specific.strftime('%A, %B %d, %Y')} (moon sighting may shift by a day)."
                )
            return f"I could not fetch a reliable {eid_label} date for {requested_year} right now. Please try again in a moment."

        eid_this_year = eid_lookup(current_year, timeout_seconds=timeout_seconds)
        eid_next_year = eid_lookup(current_year + 1, timeout_seconds=timeout_seconds)

        candidates = [d for d in (eid_this_year, eid_next_year) if d is not None]
        upcoming = None
        if candidates:
            upcoming = min((d for d in candidates if d.date() >= now.date()), default=None)
            if upcoming is None:
                upcoming = min(candidates)

        if upcoming is not None:
            return (
                f"{eid_label} is expected to begin on "
                f"{upcoming.strftime('%A, %B %d, %Y')} (moon sighting may shift by a day)."
            )

        return f"I could not fetch a reliable {eid_label} date right now. Please try again in a moment."

    if _has_word(lower, "ramadan"):
        current_year = now.year
        if requested_year is None and _is_ramadan_day_query(lower):
            month_number, day_number = _find_hijri_for_gregorian_date(
                now, timeout_seconds=timeout_seconds
            )
            if month_number == 9 and day_number is not None:
                return (
                    f"Today is Ramadan day {day_number} "
                    "(calendar may vary by moon sighting and local authority announcements)."
                )

            start_this_year = _find_ramadan_start_gregorian(
                current_year, timeout_seconds=timeout_seconds
            )
            start_next_year = _find_ramadan_start_gregorian(
                current_year + 1, timeout_seconds=timeout_seconds
            )
            candidates = [d for d in (start_this_year, start_next_year) if d is not None]
            upcoming = None
            if candidates:
                upcoming = min((d for d in candidates if d.date() >= now.date()), default=None)
                if upcoming is None:
                    upcoming = min(candidates)

            if upcoming is not None:
                return (
                    "Today is not within Ramadan. "
                    "Ramadan is expected to start on "
                    f"{upcoming.strftime('%A, %B %d, %Y')} (moon sighting may shift by a day)."
                )
            return "I could not verify today's Ramadan day right now. Please try again in a moment."

        if requested_year is not None:
            start_specific_year = _find_ramadan_start_gregorian(
                requested_year,
                timeout_seconds=timeout_seconds,
            )
            if start_specific_year is not None:
                return (
                    "Ramadan is expected to start on "
                    f"{start_specific_year.strftime('%A, %B %d, %Y')} (moon sighting may shift by a day)."
                )
            return f"I could not fetch a reliable Ramadan start date for {requested_year} right now. Please try again in a moment."

        start_this_year = _find_ramadan_start_gregorian(
            current_year, timeout_seconds=timeout_seconds
        )
        start_next_year = _find_ramadan_start_gregorian(
            current_year + 1, timeout_seconds=timeout_seconds
        )

        candidates = [d for d in (start_this_year, start_next_year) if d is not None]
        upcoming = None
        if candidates:
            upcoming = min((d for d in candidates if d.date() >= now.date()), default=None)
            if upcoming is None:
                upcoming = min(candidates)

        if upcoming is not None:
            return (
                "Ramadan is expected to start on "
                f"{upcoming.strftime('%A, %B %d, %Y')} (moon sighting may shift by a day)."
            )

        return "I could not fetch a reliable Ramadan start date right now. Please try again in a moment."

    if _has_word(lower, "time"):
        return (
            f"Current time is {now.strftime('%I:%M %p')} on {now.strftime('%Y-%m-%d')} "
            f"({timezone_for_query}, {source})."
        )

    if _has_word(lower, "day") and (_has_word(lower, "tomorrow") or _has_word(lower, "tommorow")):
        tomorrow = datetime.combine(reference_date, datetime.min.time()) + timedelta(days=1)
        return f"Tomorrow is {tomorrow.strftime('%A')}, {tomorrow.strftime('%Y-%m-%d')}."

    if _has_word(lower, "day") and _has_word(lower, "today"):
        if requested_year is not None:
            return f"On this day in {requested_year}, it was {reference_date.strftime('%A')}."
        return f"Today is {reference_date.strftime('%A')}."

    if _has_word(lower, "date") or (
        _has_word(lower, "today")
        and (
            _has_word(lower, "what")
            or _has_word(lower, "day")
            or _has_word(lower, "date")
            or _has_word(lower, "time")
            or _has_word(lower, "calendar")
        )
    ):
        if requested_year is not None:
            return (
                f"On this date in {requested_year}, it was {reference_date.strftime('%Y-%m-%d')}."
            )
        return f"Today's date is {reference_date.strftime('%Y-%m-%d')}."

    if _has_word(lower, "calendar") and (
        _has_word(lower, "month") or "this month" in lower or _has_word(lower, "show")
    ):
        month_view = calendar.TextCalendar(firstweekday=0).formatmonth(now.year, now.month)
        return f"This month's calendar ({source}):\n{month_view}"

    return None
