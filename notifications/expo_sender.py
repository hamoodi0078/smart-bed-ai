from __future__ import annotations

import datetime
import json
import os

import requests

from notifications.notification_types import NOTIFICATION_TEMPLATES, NotificationType


class ExpoPushSender:
    EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

    def __init__(self):
        base_dir = os.path.dirname(__file__)
        self.tokens_path = os.path.join(base_dir, "device_tokens.json")
        self.log_path = os.path.join(base_dir, "notification_log.json")

    def _read_json(self, file_path: str, default):
        if not os.path.exists(file_path):
            return default
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return default
        return payload

    def _write_json(self, file_path: str, payload) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def _now(self) -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")

    def send_push(self, expo_token: str, title: str, body: str, data: dict = None) -> dict:
        payload = {
            "to": expo_token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
        }
        try:
            response = requests.post(self.EXPO_PUSH_URL, json=payload, timeout=20)
            if response.ok:
                return {"sent": True}
            return {"sent": False, "error": f"Expo API error {response.status_code}: {response.text}"}
        except Exception as exc:
            return {"sent": False, "error": str(exc)}

    def register_token(self, user_id: str, expo_token: str, platform: str = "android") -> dict:
        tokens = self._read_json(self.tokens_path, {})
        if not isinstance(tokens, dict):
            tokens = {}
        tokens[str(user_id)] = {
            "expo_token": str(expo_token),
            "platform": str(platform),
            "registered_at": self._now(),
        }
        self._write_json(self.tokens_path, tokens)
        return {"registered": True, "user_id": str(user_id), "platform": str(platform)}

    def get_token(self, user_id: str) -> str | None:
        tokens = self._read_json(self.tokens_path, {})
        if not isinstance(tokens, dict):
            return None
        user_payload = tokens.get(str(user_id), {})
        if not isinstance(user_payload, dict):
            return None
        token = str(user_payload.get("expo_token", "")).strip()
        return token or None

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
        log = self._read_json(self.log_path, [])
        if not isinstance(log, list):
            log = []
        log.append(entry)
        self._write_json(self.log_path, log)

    def get_user_log(self, user_id: str) -> list[dict]:
        log = self._read_json(self.log_path, [])
        if not isinstance(log, list):
            return []
        return [item for item in log if isinstance(item, dict) and str(item.get("user_id")) == str(user_id)]

    def send_to_user(self, user_id: str, notification_type, template_vars: dict = None) -> dict:
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

        expo_token = self.get_token(user_id)
        if not expo_token:
            result = {"sent": False, "error": f"No Expo token for user_id={user_id}"}
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
        result = self.send_push(expo_token=expo_token, title=title, body=body, data=data)

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
