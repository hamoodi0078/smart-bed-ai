from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any

TRACE_ID_FALLBACK = "trace_unavailable"
EVENT_TYPE_FALLBACK = "event"

_SENSITIVE_EXACT_KEYS = {
    "access_token",
    "refresh_token",
    "password",
    "password_hash",
    "secret",
    "api_key",
    "authorization",
    "cookie",
    "set-cookie",
    "email",
    "transcript",
    "user_text",
    "raw_text",
    "prompt",
    "response_text",
    "reply",
    "message",
    "user_id",
    "actor_user_id",
    "admin_id",
}
_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "transcript",
    "prompt",
    "reply",
    "message",
    "email",
    "cookie",
    "authorization",
    "api_key",
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_user_id(user_id: Any) -> str:
    text = str(user_id or "").strip().lower()
    if not text:
        return ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"user_{digest[:16]}"


def _is_sensitive_key(key: Any) -> bool:
    text = str(key or "").strip().lower()
    if not text:
        return False
    if text in _SENSITIVE_EXACT_KEYS:
        return True
    return any(part in text for part in _SENSITIVE_KEY_PARTS)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_metadata(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in list(value)[:20]]
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    if isinstance(value, str):
        return value.strip()[:200]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    raw = metadata if isinstance(metadata, dict) else {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if _is_sensitive_key(key):
            continue
        key_text = str(key or "").strip()
        if not key_text:
            continue
        out[key_text] = _sanitize_value(value)
    return out


def build_log_record(
    *,
    level: str,
    event_type: str,
    trace_id: str = "",
    user_id: Any = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "timestamp": _utc_timestamp(),
        "level": str(level or "info").upper(),
        "trace_id": str(trace_id or TRACE_ID_FALLBACK),
        "event_type": str(event_type or EVENT_TYPE_FALLBACK),
        "metadata": sanitize_metadata(metadata),
    }
    user_hash = hash_user_id(user_id)
    if user_hash:
        record["user_id"] = user_hash
    return record


def emit_json_log(
    logger: logging.Logger,
    *,
    level: str,
    event_type: str,
    trace_id: str = "",
    user_id: Any = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = build_log_record(
        level=level,
        event_type=event_type,
        trace_id=trace_id,
        user_id=user_id,
        metadata=metadata,
    )
    payload = json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    level_key = str(level or "info").lower()
    if level_key in {"warning", "warn"}:
        logger.warning(payload)
    elif level_key in {"error", "exception"}:
        logger.error(payload)
    else:
        logger.info(payload)
    return record
