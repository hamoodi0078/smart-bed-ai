from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Return a UTC-aware datetime.

    Policy for naive datetimes: assume the value is already in UTC and attach
    timezone.utc.
    """
    if not isinstance(dt, datetime):
        raise TypeError("ensure_utc expects a datetime instance")
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime) -> str:
    """Serialize datetime to ISO 8601 using a UTC 'Z' suffix."""
    return ensure_utc(dt).isoformat().replace("+00:00", "Z")


def from_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp into a UTC-aware datetime."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("ISO datetime string is empty")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    return ensure_utc(parsed)
