"""Firebase Cloud Messaging sender — complement to ExpoPushSender for native FCM tokens.

Token storage strategy
----------------------
Preferred: PostgreSQL ``fcm_device_tokens`` table — survives restarts, safe for
           multiple Gunicorn workers / containers.
Fallback:  Local JSON file — used when no DATABASE_URL is configured (dev/test).
"""

from __future__ import annotations

import datetime
import json
import os
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger as _log

from notifications.notification_types import NOTIFICATION_TEMPLATES, NotificationType

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    _FCM_AVAILABLE = True
except ImportError:
    _FCM_AVAILABLE = False

_firebase_app: Any = None  # singleton firebase_admin.App


def initialize_firebase(credentials_path: str = "", credentials_json: str = "") -> bool:
    """Initialize Firebase Admin SDK.  Call once at app startup.

    Priority: credentials_json (inline JSON string) > credentials_path (file path).
    Returns True if initialization succeeded.
    """
    global _firebase_app
    if not _FCM_AVAILABLE:
        _log.warning("firebase-admin not installed — FCM disabled")
        return False
    if _firebase_app is not None:
        return True

    try:
        if credentials_json.strip():
            cred_dict = json.loads(credentials_json)
            cred = credentials.Certificate(cred_dict)
        elif credentials_path.strip() and os.path.isfile(credentials_path):
            cred = credentials.Certificate(credentials_path)
        else:
            _log.warning("No Firebase credentials configured — FCM disabled")
            return False

        _firebase_app = firebase_admin.initialize_app(cred)
        _log.info("Firebase Admin SDK initialized")
        return True
    except Exception as exc:
        _log.warning("Firebase Admin SDK init failed (non-fatal): {}", exc)
        return False


def _is_initialized() -> bool:
    return _firebase_app is not None and _FCM_AVAILABLE


# ── Token storage backends ────────────────────────────────────────────────────


class _TokenStore(ABC):
    @abstractmethod
    def register(self, user_id: str, fcm_token: str, platform: str) -> None: ...

    @abstractmethod
    def get(self, user_id: str) -> str | None: ...


class _JsonTokenStore(_TokenStore):
    """File-backed store — single-process only, used as fallback."""

    def __init__(self, file_path: str) -> None:
        self._path = file_path

    def _read(self) -> dict:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def register(self, user_id: str, fcm_token: str, platform: str) -> None:
        tokens = self._read()
        tokens[str(user_id)] = {
            "fcm_token": str(fcm_token),
            "platform": str(platform),
            "registered_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self._write(tokens)

    def get(self, user_id: str) -> str | None:
        tokens = self._read()
        entry = tokens.get(str(user_id), {})
        if not isinstance(entry, dict):
            return None
        token = str(entry.get("fcm_token", "")).strip()
        return token or None


_DDL = """
CREATE TABLE IF NOT EXISTS fcm_device_tokens (
    user_id     TEXT        PRIMARY KEY,
    fcm_token   TEXT        NOT NULL,
    platform    TEXT        NOT NULL DEFAULT 'android',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_UPSERT = """
INSERT INTO fcm_device_tokens (user_id, fcm_token, platform, registered_at, updated_at)
VALUES (%s, %s, %s, NOW(), NOW())
ON CONFLICT (user_id) DO UPDATE
    SET fcm_token = EXCLUDED.fcm_token,
        platform  = EXCLUDED.platform,
        updated_at = NOW();
"""

_SELECT = "SELECT fcm_token FROM fcm_device_tokens WHERE user_id = %s;"


class _PgTokenStore(_TokenStore):
    """PostgreSQL-backed store — safe for multiple workers."""

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._conn: Any = None
        self._ready = False
        self._ensure_table()

    def _get_conn(self):
        try:
            import psycopg2

            if self._conn is None or self._conn.closed:
                self._conn = psycopg2.connect(self._url)
                self._conn.autocommit = True
            return self._conn
        except Exception as exc:
            _log.warning("FCM PgTokenStore: DB connection failed: {}", exc)
            raise

    def _ensure_table(self) -> None:
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(_DDL)
            self._ready = True
        except Exception as exc:
            _log.warning("FCM PgTokenStore: could not create table: {}", exc)
            self._ready = False

    def register(self, user_id: str, fcm_token: str, platform: str) -> None:
        if not self._ready:
            self._ensure_table()
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(_UPSERT, (str(user_id), str(fcm_token), str(platform)))
        except Exception as exc:
            _log.warning("FCM PgTokenStore.register failed: {}", exc)
            raise

    def get(self, user_id: str) -> str | None:
        if not self._ready:
            self._ensure_table()
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(_SELECT, (str(user_id),))
                row = cur.fetchone()
            return str(row[0]).strip() if row else None
        except Exception as exc:
            _log.warning("FCM PgTokenStore.get failed: {}", exc)
            return None


def _build_token_store(fallback_path: str) -> _TokenStore:
    """Try PostgreSQL first; fall back to JSON file."""
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url and not db_url.lower().startswith("sqlite"):
        try:
            store = _PgTokenStore(db_url)
            if store._ready:
                _log.info("FCM: using PostgreSQL token store")
                return store
        except Exception as exc:
            _log.warning("FCM: PostgreSQL token store unavailable ({}), using JSON fallback", exc)
    _log.info("FCM: using JSON token store ({})", fallback_path)
    return _JsonTokenStore(fallback_path)


# ── FcmSender ─────────────────────────────────────────────────────────────────


class FcmSender:
    """FCM push notification sender with the same interface as ExpoPushSender."""

    def __init__(self):
        base_dir = os.path.dirname(__file__)
        self._fallback_tokens_path = os.path.join(base_dir, "fcm_device_tokens.json")
        self._log_path = os.path.join(base_dir, "fcm_notification_log.json")
        self._token_store: _TokenStore | None = None

    def _get_token_store(self) -> _TokenStore:
        if self._token_store is None:
            self._token_store = _build_token_store(self._fallback_tokens_path)
        return self._token_store

    # Public token management

    def register_token(self, user_id: str, fcm_token: str, platform: str = "android") -> dict:
        try:
            self._get_token_store().register(str(user_id), str(fcm_token), str(platform))
            return {"registered": True, "user_id": str(user_id), "platform": str(platform)}
        except Exception as exc:
            _log.warning("FCM register_token failed for user {}: {}", user_id, exc)
            return {"registered": False, "error": str(exc)}

    def get_token(self, user_id: str) -> str | None:
        return self._get_token_store().get(str(user_id))

    # Sending

    def send(self, fcm_token: str, title: str, body: str, data: dict | None = None) -> dict:
        if not _is_initialized():
            return {"sent": False, "error": "Firebase not initialized"}
        try:
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=fcm_token,
                android=messaging.AndroidConfig(priority="high"),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(aps=messaging.Aps(sound="default"))
                ),
            )
            message_id = messaging.send(msg)
            return {"sent": True, "message_id": message_id}
        except Exception as exc:
            return {"sent": False, "error": str(exc)}

    def send_multicast(
        self, fcm_tokens: list[str], title: str, body: str, data: dict | None = None
    ) -> dict:
        if not _is_initialized():
            return {"sent": False, "error": "Firebase not initialized"}
        if not fcm_tokens:
            return {"sent": False, "error": "No tokens provided"}
        try:
            msg = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                tokens=fcm_tokens,
                android=messaging.AndroidConfig(priority="high"),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(aps=messaging.Aps(sound="default"))
                ),
            )
            response = messaging.send_each_for_multicast(msg)
            return {
                "sent": True,
                "success_count": response.success_count,
                "failure_count": response.failure_count,
            }
        except Exception as exc:
            return {"sent": False, "error": str(exc)}

    # Helpers

    def _now(self) -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")

    def _read_json(self, file_path: str, default):
        if not os.path.exists(file_path):
            return default
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return default

    def _write_json(self, file_path: str, payload) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def _resolve_notification_type(self, notification_type) -> NotificationType | None:
        if isinstance(notification_type, NotificationType):
            return notification_type
        try:
            return NotificationType(str(notification_type).strip().lower())
        except ValueError:
            return None

    def _safe_format(self, text: str, vars_map: dict) -> str:
        safe_vars = {
            "user_name": vars_map.get("user_name", "Guest"),
            "prayer_name": vars_map.get("prayer_name", "Prayer"),
            "minutes": vars_map.get("minutes", 0),
            "hours": vars_map.get("hours", 0),
            "streak": vars_map.get("streak", 0),
            "days": vars_map.get("days", 0),
        }
        return str(text).format(**safe_vars)

    def _append_log(self, entry: dict) -> None:
        log = self._read_json(self._log_path, [])
        if not isinstance(log, list):
            log = []
        log.append(entry)
        self._write_json(self._log_path, log)

    def send_to_user(
        self, user_id: str, notification_type, template_vars: dict | None = None
    ) -> dict:
        template_vars = template_vars or {}
        resolved = self._resolve_notification_type(notification_type)
        if resolved is None:
            result = {"sent": False, "error": "Invalid notification type."}
            self._append_log(
                {
                    "user_id": str(user_id),
                    "notification_type": str(notification_type),
                    "timestamp": self._now(),
                    "result": result,
                }
            )
            return result

        fcm_token = self.get_token(user_id)
        if not fcm_token:
            result = {"sent": False, "error": f"No FCM token for user_id={user_id}"}
            self._append_log(
                {
                    "user_id": str(user_id),
                    "notification_type": resolved.value,
                    "timestamp": self._now(),
                    "result": result,
                }
            )
            return result

        template = NOTIFICATION_TEMPLATES.get(resolved, {})
        title = self._safe_format(template.get("title", "Notification"), template_vars)
        body = self._safe_format(template.get("body", ""), template_vars)
        data = {"type": resolved.value, **template_vars}
        result = self.send(fcm_token=fcm_token, title=title, body=body, data=data)

        self._append_log(
            {
                "user_id": str(user_id),
                "notification_type": resolved.value,
                "title": title,
                "body": body,
                "timestamp": self._now(),
                "result": result,
            }
        )
        return result
