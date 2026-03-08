from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from database import User, UserRepository
from time_utils import utcnow


class SubscriptionGate:
    FREE_SCENE_LIMIT = 3
    FREE_SCENE_NAMES = ["Cozy Night", "Ocean Waves", "Morning Light"]

    def __init__(self, user_repo: UserRepository | None = None):
        self.user_repo = user_repo or UserRepository()

    @staticmethod
    def _normalize_status(user: User | None) -> str:
        if user is None:
            return "free"
        status = str(user.subscription_status or "free").strip().lower()
        return status if status in {"free", "trial", "premium"} else "free"

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        if dt.tzinfo is None or dt.utcoffset() is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def check_scene_access(self, user_id: str, scene_name: str, scene_is_premium: bool) -> dict:
        if not bool(scene_is_premium):
            return {
                "allowed": True,
                "reason": "free_tier",
                "subscription_status": "free",
                "trial_days_remaining": None,
            }

        user = self.user_repo.get_user_by_id(str(user_id or "").strip())
        if user is None:
            return {
                "allowed": True,
                "reason": "free_tier",
                "subscription_status": "free",
                "trial_days_remaining": None,
            }

        subscription_status = self._normalize_status(user)
        if subscription_status == "premium":
            return {
                "allowed": True,
                "reason": "premium",
                "subscription_status": "premium",
                "trial_days_remaining": None,
            }

        if subscription_status == "trial":
            if self.is_trial_active(user):
                return {
                    "allowed": True,
                    "reason": "trial_active",
                    "subscription_status": "trial",
                    "trial_days_remaining": self.get_trial_days_remaining(user),
                }
            return {
                "allowed": False,
                "reason": "premium_required",
                "subscription_status": "trial",
                "trial_days_remaining": 0,
            }

        return {
            "allowed": False,
            "reason": "premium_required",
            "subscription_status": "free",
            "trial_days_remaining": None,
        }

    def is_trial_active(self, user: User) -> bool:
        end = user.trial_end_date
        if end is None:
            return False
        trial_window_end = self._ensure_aware(end) + timedelta(days=2)
        return utcnow() <= trial_window_end

    def get_trial_days_remaining(self, user: User) -> int:
        end = user.trial_end_date
        if end is None:
            return 0
        trial_window_end = self._ensure_aware(end) + timedelta(days=2)
        remaining_seconds = (trial_window_end - utcnow()).total_seconds()
        if remaining_seconds <= 0:
            return 0
        return max(0, int(math.ceil(remaining_seconds / 86400.0)))
