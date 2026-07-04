"""User management service.

Thin wrapper over UserRepository that provides a clean interface for
admin user-management operations without importing web_server.py.
"""

from __future__ import annotations

import threading
from typing import Any

from loguru import logger

from database import UserRepository


class UserService:
    """Admin-facing user management operations."""

    def __init__(self, user_repo: UserRepository | None = None) -> None:
        self._users = user_repo or UserRepository()

    def list_users(
        self,
        search: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return a paginated, optionally filtered user list."""
        safe_limit = max(1, min(int(limit or 50), 500))
        safe_offset = max(0, int(offset or 0))

        rows = self._users.list_all(limit=safe_limit + safe_offset)
        rows = rows[safe_offset:]

        search_lower = (search or "").strip().lower()
        if search_lower:
            rows = [
                r
                for r in rows
                if search_lower in (getattr(r, "email", "") or "").lower()
                or search_lower in (getattr(r, "full_name", "") or "").lower()
            ]

        return {
            "ok": True,
            "users": [_row_to_summary(r) for r in rows],
            "total": len(rows),
        }

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Return detailed user info or None if not found."""
        row = self._users.get_user_by_id(user_id)
        if row is None:
            return None
        return _row_to_detail(row)

    def patch_user(self, user_id: str, **fields: Any) -> dict[str, Any]:
        """Update allowed user fields and return the updated record.

        Raises:
            ValueError: if user_id is not found.
        """
        allowed = {"full_name", "role", "subscription_status", "is_active"}
        sanitised = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not sanitised:
            row = self._users.get_user_by_id(user_id)
            if row is None:
                raise ValueError(f"User {user_id!r} not found")
            return _row_to_detail(row)

        row = self._users.update_user(user_id, **sanitised)
        logger.info("admin.patch_user user_id={} fields={}", user_id, list(sanitised))
        return _row_to_detail(row)

    def delete_user(self, user_id: str) -> bool:
        """Hard-delete a user. Returns True if deleted, False if not found."""
        deleted = self._users.delete_user(user_id)
        if deleted:
            logger.info("admin.delete_user user_id={}", user_id)
        return deleted


# ── Serialisers ───────────────────────────────────────────────────────────────


def _row_to_summary(row: Any) -> dict[str, Any]:
    return {
        "user_id": str(getattr(row, "id", "") or ""),
        "email": str(getattr(row, "email", "") or ""),
        "name": str(getattr(row, "full_name", "") or ""),
        "role": str(getattr(row, "role", "user") or "user"),
        "subscription_status": str(getattr(row, "subscription_status", "free") or "free"),
        "created_at": str(getattr(row, "created_at", "") or ""),
    }


def _row_to_detail(row: Any) -> dict[str, Any]:
    summary = _row_to_summary(row)
    summary.update(
        {
            "is_active": bool(getattr(row, "is_active", True)),
            "trial_start_date": str(getattr(row, "trial_start_date", "") or ""),
            "trial_end_date": str(getattr(row, "trial_end_date", "") or ""),
            "updated_at": str(getattr(row, "updated_at", "") or ""),
        }
    )
    return summary


# ── Singleton ─────────────────────────────────────────────────────────────────

_user_service: UserService | None = None
_user_service_lock = threading.Lock()


def get_user_service() -> UserService:
    """Return the process-level UserService singleton."""
    global _user_service
    if _user_service is None:
        with _user_service_lock:
            if _user_service is None:
                _user_service = UserService()
    return _user_service


__all__ = ["UserService", "get_user_service"]
