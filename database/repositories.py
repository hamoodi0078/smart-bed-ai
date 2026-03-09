from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select

from time_utils import utcnow

from .connection import DatabaseConnection
from .models import Event, SleepSession, User


def _clean_user_id(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _coerce_date(value: date_type | str) -> date_type:
    if isinstance(value, date_type):
        return value
    return date_type.fromisoformat(str(value))


class UserRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    def create_user(self, email: str, password_hash: str, full_name: str | None = None) -> User:
        with self.db.get_session() as session:
            user = User(
                email=str(email or "").strip().lower(),
                password_hash=str(password_hash or "").strip(),
                full_name=str(full_name or "").strip() or None,
            )
            session.add(user)
            session.flush()
            session.refresh(user)
            return user

    def get_user_by_id(self, user_id: str) -> User | None:
        with self.db.get_session() as session:
            key = _clean_user_id(user_id)
            if not key:
                return None
            return session.get(User, key)

    def get_user_by_email(self, email: str) -> User | None:
        with self.db.get_session() as session:
            normalized = str(email or "").strip().lower()
            if not normalized:
                return None
            statement = select(User).where(User.email == normalized).limit(1)
            return session.execute(statement).scalar_one_or_none()

    def list_all(self, limit: int = 1000) -> list[User]:
        with self.db.get_session() as session:
            safe_limit = max(1, min(int(limit or 1000), 5000))
            statement = select(User).order_by(User.created_at.desc()).limit(safe_limit)
            return list(session.execute(statement).scalars().all())

    def update_subscription(
        self,
        user_id: str,
        status: str,
        trial_start: datetime | None = None,
        trial_end: datetime | None = None,
    ) -> User:
        with self.db.get_session() as session:
            user = session.get(User, str(user_id or "").strip())
            if user is None:
                raise ValueError("User not found")

            user.subscription_status = str(status or "free").strip().lower() or "free"
            user.trial_start_date = trial_start
            user.trial_end_date = trial_end
            user.updated_at = utcnow()

            session.add(user)
            session.flush()
            session.refresh(user)
            return user

    def update_user(self, user_id: str, **kwargs: Any) -> User:
        with self.db.get_session() as session:
            user = session.get(User, str(user_id or "").strip())
            if user is None:
                raise ValueError("User not found")

            blocked = {"id", "created_at"}
            for key, value in kwargs.items():
                if key in blocked:
                    continue
                if hasattr(user, key):
                    setattr(user, key, value)

            user.updated_at = utcnow()
            session.add(user)
            session.flush()
            session.refresh(user)
            return user


class EventRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    def log_event(
        self,
        user_id: str | None,
        event_type: str,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Event:
        with self.db.get_session() as session:
            row = Event(
                user_id=_clean_user_id(user_id),
                event_type=str(event_type or "").strip(),
                metadata_json=dict(metadata or {}) if isinstance(metadata, dict) else None,
                trace_id=str(trace_id or "").strip() or None,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return row

    def get_events_by_user(self, user_id: str, limit: int = 50, since: datetime | None = None) -> list[Event]:
        with self.db.get_session() as session:
            user_key = _clean_user_id(user_id)
            if not user_key:
                return []
            safe_limit = max(1, min(int(limit or 50), 500))
            statement = select(Event).where(Event.user_id == user_key)
            if since is not None:
                statement = statement.where(Event.timestamp >= since)
            statement = statement.order_by(Event.timestamp.desc()).limit(safe_limit)
            return list(session.execute(statement).scalars().all())

    def get_events_for_date(self, user_id: str, for_date: date_type) -> list[Event]:
        with self.db.get_session() as session:
            user_key = _clean_user_id(user_id)
            if not user_key:
                return []
            target_date = _coerce_date(for_date)
            statement = (
                select(Event)
                .where(Event.user_id == user_key, func.date(Event.timestamp) == target_date.isoformat())
                .order_by(Event.timestamp.desc())
            )
            return list(session.execute(statement).scalars().all())

    def cleanup_old_events(self, days: int = 90) -> int:
        with self.db.get_session() as session:
            age_days = max(1, int(days or 90))
            cutoff = utcnow() - timedelta(days=age_days)
            statement = delete(Event).where(Event.timestamp < cutoff)
            result = session.execute(statement)
            return int(result.rowcount or 0)


class SleepSessionRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    def create_or_update_session(self, user_id: str, date: date_type | str, **kwargs: Any) -> SleepSession:
        with self.db.get_session() as session:
            user_key = _clean_user_id(user_id)
            target_date = _coerce_date(date)
            statement = select(SleepSession).where(SleepSession.user_id == user_key, SleepSession.date == target_date).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                row = SleepSession(user_id=user_key, date=target_date)

            allowed = {
                "bedtime",
                "wake_time",
                "total_sleep_minutes",
                "restlessness_score",
                "scenes_used",
                "automations_fired",
                "winddowns_completed",
            }
            for key, value in kwargs.items():
                if key in allowed:
                    setattr(row, key, value)

            session.add(row)
            session.flush()
            session.refresh(row)
            return row

    def get_session_by_date(self, user_id: str, date: date_type | str) -> SleepSession | None:
        with self.db.get_session() as session:
            user_key = _clean_user_id(user_id)
            if not user_key:
                return None
            target_date = _coerce_date(date)
            statement = select(SleepSession).where(SleepSession.user_id == user_key, SleepSession.date == target_date).limit(1)
            return session.execute(statement).scalar_one_or_none()

    def get_recent_sessions(self, user_id: str, limit: int = 7) -> list[SleepSession]:
        with self.db.get_session() as session:
            user_key = _clean_user_id(user_id)
            if not user_key:
                return []
            safe_limit = max(1, min(int(limit or 7), 90))
            statement = (
                select(SleepSession)
                .where(SleepSession.user_id == user_key)
                .order_by(SleepSession.date.desc())
                .limit(safe_limit)
            )
            return list(session.execute(statement).scalars().all())

    def get_sessions_for_month(self, user_id: str, year: int, month: int, limit: int = 40) -> list[SleepSession]:
        with self.db.get_session() as session:
            user_key = _clean_user_id(user_id)
            if not user_key:
                return []

            safe_year = int(year)
            safe_month = int(month)
            try:
                month_start = date_type(safe_year, safe_month, 1)
            except ValueError:
                return []
            month_end = date_type(safe_year + 1, 1, 1) if safe_month == 12 else date_type(safe_year, safe_month + 1, 1)
            safe_limit = max(1, min(int(limit or 40), 200))

            statement = (
                select(SleepSession)
                .where(SleepSession.user_id == user_key, SleepSession.date >= month_start, SleepSession.date < month_end)
                .order_by(SleepSession.date.desc())
                .limit(safe_limit)
            )
            return list(session.execute(statement).scalars().all())
