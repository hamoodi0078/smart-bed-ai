import re
from typing import Optional

import requests


TIMEZONE_MAP = {
    "pakistan": "Asia/Karachi",
    "karachi": "Asia/Karachi",
    "kuwait": "Asia/Kuwait",
    "uae": "Asia/Dubai",
    "dubai": "Asia/Dubai",
    "india": "Asia/Kolkata",
    "london": "Europe/London",
    "uk": "Europe/London",
    "new york": "America/New_York",
    "usa": "America/New_York",
}

REALTIME_KEYWORDS = (
    "current",
    "latest",
    "today",
    "now",
    "live",
    "time",
    "weather",
    "temperature",
    "news",
    "price",
)


def is_realtime_query(text: str) -> bool:
    t = text.lower()
    return any(keyword in t for keyword in REALTIME_KEYWORDS)


def fetch_realtime_context(query: str, timeout_seconds: int = 10) -> str:
    chunks = []
    t = query.lower().strip()

    time_chunk = _fetch_time_context(t, timeout_seconds)
    if time_chunk:
        chunks.append(time_chunk)

    weather_chunk = _fetch_weather_context(t, timeout_seconds)
    if weather_chunk:
        chunks.append(weather_chunk)

    web_chunk = _fetch_web_summary(query, timeout_seconds)
    if web_chunk:
        chunks.append(web_chunk)

    return "\n".join(chunks).strip()


def _fetch_time_context(lower_query: str, timeout_seconds: int) -> Optional[str]:
    if "time" not in lower_query:
        return None

    timezone = None
    for key, tz in TIMEZONE_MAP.items():
        if key in lower_query:
            timezone = tz
            break

    if timezone is None:
        timezone = "Asia/Kuwait"

    try:
        response = requests.get(
            f"https://worldtimeapi.org/api/timezone/{timezone}", timeout=timeout_seconds
        )
        response.raise_for_status()
        body = response.json()
        dt = body.get("datetime", "")
        if dt:
            dt = dt.replace("T", " ")[:19]
        return f"REALTIME_TIME: Timezone={timezone}, datetime={dt}"
    except Exception:
        return None


def _fetch_weather_context(lower_query: str, timeout_seconds: int) -> Optional[str]:
    if "weather" not in lower_query and "temperature" not in lower_query:
        return None

    city = _extract_city(lower_query)
    if not city:
        city = "Kuwait City"

    try:
        response = requests.get(
            f"https://wttr.in/{city}?format=j1", timeout=timeout_seconds
        )
        response.raise_for_status()
        body = response.json()
        current = body.get("current_condition", [{}])[0]
        temp_c = current.get("temp_C", "?")
        description = ""
        weather_desc = current.get("weatherDesc", [])
        if weather_desc:
            description = weather_desc[0].get("value", "")
        return (
            f"REALTIME_WEATHER: city={city.title()}, temp_c={temp_c}, "
            f"description={description}"
        )
    except Exception:
        return None


def _fetch_web_summary(query: str, timeout_seconds: int) -> Optional[str]:
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()

        abstract = (body.get("AbstractText") or "").strip()
        heading = (body.get("Heading") or "").strip()
        if abstract:
            if heading:
                return f"WEB_SUMMARY: {heading} - {abstract}"
            return f"WEB_SUMMARY: {abstract}"

        related = body.get("RelatedTopics", [])
        for item in related:
            text = item.get("Text") if isinstance(item, dict) else None
            if text:
                return f"WEB_SUMMARY: {text}"
    except Exception:
        return None

    return None


def _extract_city(lower_query: str) -> str:
    match = re.search(r"(?:in|at)\s+([a-z\s]+)", lower_query)
    if not match:
        return ""
    city = match.group(1).strip()
    city = city.replace("the", "").strip()
    return city
