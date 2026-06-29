from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from secrets import token_urlsafe

from auth.jwt_handler import JWTError, create_access_token, decode_access_token, is_jwt
from typing import Any

from sqlalchemy import delete, func, select

from time_utils import ensure_utc, from_iso, to_iso, utcnow

from .connection import AsyncDatabaseConnection, DatabaseConnection
from .models import (
    Alarm,
    AppVersion,
    BetaCohortMember,
    BetaMetricsSnapshot,
    Event,
    FeatureFlag,
    FirmwareVersion,
    FirstThreeNightsProgress,
    MobileCommandFeedback,
    MobileCommandRecord,
    MobileAuthSession,
    NightlySummaryFeedbackProgress,
    OtpRequest,
    SleepSession,
    SpotifyToken,
    User,
    UserFeatureOverride,
    UserProfilePrefs,
    UserRoutine,
)


def _clean_user_id(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _coerce_date(value: date_type | str) -> date_type:
    if isinstance(value, date_type):
        return value
    return date_type.fromisoformat(str(value))


def _to_iso_optional(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        return ""
    return to_iso(ensure_utc(value))


def _parse_optional_iso_datetime(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return ensure_utc(from_iso(raw))
    except Exception:
        return None


_FIRST_3_NIGHTS_STEP_FIELD_MAP = {
    "signup": "signup_completed_at_utc",
    "first_scene_preview": "first_scene_preview_completed_at_utc",
    "first_automation": "first_automation_completed_at_utc",
    "first_winddown": "first_winddown_completed_at_utc",
    "timeline_review": "timeline_review_completed_at_utc",
}


class UserRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    def create_user(
        self,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        user_id: str | None = None,
    ) -> User:
        with self.db.get_session() as session:
            user = User(
                id=str(user_id or "").strip() or None,
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

    def delete_user(self, user_id: str) -> bool:
        with self.db.get_session() as session:
            key = _clean_user_id(user_id)
            if not key:
                return False
            user = session.get(User, key)
            if user is None:
                return False
            session.delete(user)
            return True

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
                .limit(500)
            )
            return list(session.execute(statement).scalars().all())

    def cleanup_old_events(self, days: int = 90) -> int:
        with self.db.get_session() as session:
            age_days = max(1, int(days or 90))
            cutoff = utcnow() - timedelta(days=age_days)
            statement = delete(Event).where(Event.timestamp < cutoff)
            result = session.execute(statement)
            rowcount = getattr(result, "rowcount", 0)
            return int(rowcount or 0)

    def replace_mobile_timeline_events(
        self,
        user_id: str,
        items: list[dict[str, Any]] | None,
        *,
        trace_id: str = "",
        now_utc: datetime | None = None,
    ) -> int:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return 0

        rows = items if isinstance(items, list) else []
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        normalized_trace = str(trace_id or "").strip() or None

        with self.db.get_session() as session:
            clear_statement = delete(Event).where(
                Event.user_id == user_key,
                Event.event_type == "mobile_timeline_item",
            )
            session.execute(clear_statement)

            count = 0
            for idx, raw in enumerate(rows):
                if not isinstance(raw, dict):
                    continue
                payload = {
                    "time": str(raw.get("time", "Now") or "Now"),
                    "event": str(raw.get("event", "Timeline event") or "Timeline event"),
                    "status": str(raw.get("status", "active") or "active"),
                    "command_id": str(raw.get("command_id", "") or ""),
                    "priority": int(raw.get("priority", 0) or 0),
                    "captured_at_utc": _to_iso_optional(now - timedelta(milliseconds=idx)),
                }
                row = Event(
                    user_id=user_key,
                    event_type="mobile_timeline_item",
                    metadata_json=payload,
                    trace_id=normalized_trace,
                    timestamp=now - timedelta(milliseconds=idx),
                )
                session.add(row)
                count += 1
            session.flush()
            return int(count)


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


class MobileCommandRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    @staticmethod
    def _payload_from_row(row: MobileCommandRecord | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "user_id": str(row.user_id or ""),
            "command_id": str(row.command_id or ""),
            "action": str(row.action or ""),
            "status": str(row.status or "queued"),
            "event": str(row.event_summary or ""),
            "message": str(row.message or ""),
            "trace_id": str(row.trace_id or ""),
            "created_at": _to_iso_optional(row.command_created_at_utc),
            "updated_at": _to_iso_optional(row.command_updated_at_utc),
            "completed_at": _to_iso_optional(row.command_completed_at_utc),
        }

    def upsert_command(self, user_id: str, command: dict[str, Any] | None, now_utc: datetime | None = None) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        payload = command if isinstance(command, dict) else {}
        command_id = str(payload.get("id", "") or payload.get("command_id", "")).strip()
        if not user_key or not command_id:
            return {}

        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        action = str(payload.get("action", "") or "").strip().lower()
        status = str(payload.get("status", "queued") or "queued").strip().lower() or "queued"
        event_summary = str(payload.get("event", "") or "").strip()
        message = str(payload.get("message", "") or "").strip()
        trace_id = str(payload.get("trace_id", "") or "").strip() or None
        created_at = _parse_optional_iso_datetime(str(payload.get("created_at", "") or ""))
        updated_at = _parse_optional_iso_datetime(str(payload.get("updated_at", "") or ""))
        completed_at = _parse_optional_iso_datetime(str(payload.get("completed_at", "") or ""))

        with self.db.get_session() as session:
            statement = select(MobileCommandRecord).where(MobileCommandRecord.command_id == command_id).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                row = MobileCommandRecord(
                    user_id=user_key,
                    command_id=command_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()

            row.user_id = user_key
            row.action = action
            row.status = status
            row.event_summary = event_summary
            row.message = message
            row.trace_id = trace_id
            if created_at is not None:
                row.command_created_at_utc = created_at
            elif row.command_created_at_utc is None:
                row.command_created_at_utc = now
            if updated_at is not None:
                row.command_updated_at_utc = updated_at
            else:
                row.command_updated_at_utc = now
            if completed_at is not None:
                row.command_completed_at_utc = completed_at
            elif status == "completed" and row.command_completed_at_utc is None:
                row.command_completed_at_utc = row.command_updated_at_utc or now
            row.updated_at = now

            session.add(row)
            session.flush()
            session.refresh(row)
            return self._payload_from_row(row)

    def get_recent_commands(
        self,
        user_id: str,
        limit: int = 200,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return []
        safe_limit = max(1, min(int(limit or 200), 1000))
        with self.db.get_session() as session:
            order_col = func.coalesce(
                MobileCommandRecord.command_updated_at_utc,
                MobileCommandRecord.command_created_at_utc,
                MobileCommandRecord.created_at,
            )
            statement = select(MobileCommandRecord).where(MobileCommandRecord.user_id == user_key)
            if since is not None:
                statement = statement.where(order_col >= ensure_utc(since))
            statement = statement.order_by(order_col.desc()).limit(safe_limit)
            rows = session.execute(statement).scalars().all()
            return [self._payload_from_row(row) for row in rows]

    def command_metrics_window(
        self,
        user_id: str,
        *,
        now_utc: datetime | None = None,
        window_days: int = 7,
    ) -> dict[str, int]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return {"total": 0, "completed": 0, "completion_rate_pct": 0}
        days = max(1, min(int(window_days or 7), 31))
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        since = now - timedelta(days=days)
        rows = self.get_recent_commands(user_key, since=since, limit=1000)
        total = len(rows)
        completed = sum(
            1
            for row in rows
            if str(row.get("status", "queued") or "queued").strip().lower() == "completed"
        )
        completion_rate_pct = int(round((completed / total) * 100.0)) if total > 0 else 0
        return {
            "total": int(total),
            "completed": int(completed),
            "completion_rate_pct": int(completion_rate_pct),
        }

    @staticmethod
    def _command_feedback_summary_from_rows(rows: list[MobileCommandFeedback] | None) -> dict[str, Any]:
        feedback_rows = rows if isinstance(rows, list) else []
        helpful_count = 0
        not_helpful_count = 0
        last_vote = ""
        last_vote_at_utc = ""
        last_command_id = ""
        last_command_action = ""
        latest_ts = float("-inf")

        for row in feedback_rows:
            vote = str(getattr(row, "vote", "") or "").strip().lower()
            if vote == "helpful":
                helpful_count += 1
            elif vote == "not_helpful":
                not_helpful_count += 1
            else:
                continue

            ts_candidate = getattr(row, "voted_at_utc", None) or getattr(row, "updated_at", None)
            if isinstance(ts_candidate, datetime):
                ts_value = ensure_utc(ts_candidate).timestamp()
            else:
                ts_value = float("-inf")
            if ts_value >= latest_ts:
                latest_ts = ts_value
                last_vote = vote
                last_vote_at_utc = _to_iso_optional(ts_candidate if isinstance(ts_candidate, datetime) else None)
                last_command_id = str(getattr(row, "command_id", "") or "").strip()
                last_command_action = str(getattr(row, "action", "") or "").strip().lower()

        total_votes = helpful_count + not_helpful_count
        helpful_pct = int(round((helpful_count / total_votes) * 100.0)) if total_votes > 0 else 0
        return {
            "helpful_count": int(helpful_count),
            "not_helpful_count": int(not_helpful_count),
            "total_votes": int(total_votes),
            "helpful_pct": int(helpful_pct),
            "last_vote": last_vote,
            "last_vote_at_utc": last_vote_at_utc,
            "last_command_id": last_command_id,
            "last_command_action": last_command_action,
        }

    def command_feedback_summary_window(
        self,
        user_id: str,
        *,
        now_utc: datetime | None = None,
        window_days: int = 30,
    ) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return self._command_feedback_summary_from_rows([])

        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        days = max(1, min(int(window_days or 30), 90))
        since = now - timedelta(days=days)
        with self.db.get_session() as session:
            order_col = func.coalesce(
                MobileCommandFeedback.voted_at_utc,
                MobileCommandFeedback.updated_at,
                MobileCommandFeedback.created_at,
            )
            statement = (
                select(MobileCommandFeedback)
                .where(MobileCommandFeedback.user_id == user_key, order_col >= since)
                .order_by(order_col.desc())
                .limit(2000)
            )
            rows = list(session.execute(statement).scalars().all())
            return self._command_feedback_summary_from_rows(rows)

    def record_command_feedback(
        self,
        user_id: str,
        *,
        command_id: str,
        vote: str,
        command_action: str = "",
        note: str = "",
        trace_id: str = "",
        now_utc: datetime | None = None,
        window_days: int = 30,
    ) -> tuple[dict[str, Any], bool]:
        user_key = _clean_user_id(user_id)
        command_key = str(command_id or "").strip()
        normalized_vote = str(vote or "").strip().lower()
        if (not user_key) or (not command_key) or (normalized_vote not in {"helpful", "not_helpful"}):
            return self.command_feedback_summary_window(user_id, now_utc=now_utc, window_days=window_days), False

        normalized_action = str(command_action or "").strip().lower()
        normalized_note = str(note or "").strip()
        if len(normalized_note) > 240:
            normalized_note = normalized_note[:240]
        normalized_trace = str(trace_id or "").strip() or None
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        changed = False

        with self.db.get_session() as session:
            command_statement = (
                select(MobileCommandRecord)
                .where(MobileCommandRecord.user_id == user_key, MobileCommandRecord.command_id == command_key)
                .limit(1)
            )
            command_row = session.execute(command_statement).scalar_one_or_none()
            if command_row is not None:
                normalized_action = str(getattr(command_row, "action", "") or "").strip().lower() or normalized_action

            statement = (
                select(MobileCommandFeedback)
                .where(MobileCommandFeedback.user_id == user_key, MobileCommandFeedback.command_id == command_key)
                .limit(1)
            )
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                row = MobileCommandFeedback(
                    user_id=user_key,
                    command_id=command_key,
                    action=normalized_action,
                    vote=normalized_vote,
                    note=normalized_note,
                    trace_id=normalized_trace,
                    voted_at_utc=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                changed = True
            else:
                previous_vote = str(row.vote or "").strip().lower()
                previous_note = str(row.note or "").strip()
                previous_action = str(row.action or "").strip().lower()
                if (
                    previous_vote != normalized_vote
                    or previous_note != normalized_note
                    or previous_action != normalized_action
                ):
                    changed = True
                row.vote = normalized_vote
                row.note = normalized_note
                row.action = normalized_action
                row.trace_id = normalized_trace
                row.voted_at_utc = now
                row.updated_at = now
                session.add(row)

            session.flush()

        summary = self.command_feedback_summary_window(
            user_key,
            now_utc=now,
            window_days=window_days,
        )
        return summary, changed

    def replace_user_commands(
        self,
        user_id: str,
        commands: list[dict[str, Any]] | None,
        *,
        now_utc: datetime | None = None,
    ) -> int:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return 0

        rows = commands if isinstance(commands, list) else []
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())

        with self.db.get_session() as session:
            session.execute(
                delete(MobileCommandRecord).where(MobileCommandRecord.user_id == user_key)
            )
            session.execute(
                delete(MobileCommandFeedback).where(MobileCommandFeedback.user_id == user_key)
            )

            count = 0
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                command_id = str(raw.get("id", "") or raw.get("command_id", "")).strip()
                if not command_id:
                    continue

                action = str(raw.get("action", "") or "").strip().lower()
                status = str(raw.get("status", "queued") or "queued").strip().lower() or "queued"
                event_summary = str(raw.get("event", "") or "").strip()
                message = str(raw.get("message", "") or "").strip()
                trace_id = str(raw.get("trace_id", "") or "").strip() or None
                created_at = _parse_optional_iso_datetime(str(raw.get("created_at", "") or "")) or now
                updated_at = _parse_optional_iso_datetime(str(raw.get("updated_at", "") or "")) or now
                completed_at = _parse_optional_iso_datetime(str(raw.get("completed_at", "") or ""))
                if completed_at is None and status == "completed":
                    completed_at = updated_at

                row = MobileCommandRecord(
                    user_id=user_key,
                    command_id=command_id,
                    action=action,
                    status=status,
                    event_summary=event_summary,
                    message=message,
                    trace_id=trace_id,
                    command_created_at_utc=created_at,
                    command_updated_at_utc=updated_at,
                    command_completed_at_utc=completed_at,
                    created_at=created_at,
                    updated_at=updated_at,
                )
                session.add(row)
                count += 1
            session.flush()
            return int(count)


class MobileAuthRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    @staticmethod
    def _tokens_payload_from_row(row: MobileAuthSession | None) -> dict[str, Any]:
        if row is None:
            return {}
        issued_at = ensure_utc(row.issued_at_utc)
        access_exp = ensure_utc(row.access_expires_at_utc)
        refresh_exp = ensure_utc(row.refresh_expires_at_utc)
        expires_in = max(0, int((access_exp - issued_at).total_seconds()))
        return {
            "access_token": str(row.access_token or ""),
            "token_type": "Bearer",
            "expires_at": _to_iso_optional(access_exp),
            "expires_in": expires_in,
            "refresh_token": str(row.refresh_token or ""),
            "refresh_expires_at": _to_iso_optional(refresh_exp),
            "client_name": str(row.client_name or ""),
        }

    @staticmethod
    def _session_payload_from_row(row: MobileAuthSession | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "user_id": str(row.user_id or ""),
            "client_name": str(row.client_name or ""),
            "session_id": str(row.id or ""),
        }

    def issue_tokens(
        self,
        user_id: str,
        *,
        client_name: str = "",
        access_minutes: int = 60,
        refresh_days: int = 30,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return {}

        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        access_window_minutes = max(1, int(access_minutes or 60))
        refresh_window_days = max(1, int(refresh_days or 30))
        access_exp = now + timedelta(minutes=access_window_minutes)
        refresh_exp = now + timedelta(days=refresh_window_days)
        label = str(client_name or "").strip() or "flutter_app"

        jti = token_urlsafe(32)  # opaque revocation key stored in DB (fits String(255))

        with self.db.get_session() as session:
            row = MobileAuthSession(
                user_id=user_key,
                client_name=label,
                access_token=jti,           # DB stores only the JTI, not the full JWT
                refresh_token=token_urlsafe(48),
                issued_at_utc=now,
                access_expires_at_utc=access_exp,
                refresh_expires_at_utc=refresh_exp,
                revoked=False,
                revoked_at_utc=None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            payload = self._tokens_payload_from_row(row)

        # Replace the raw JTI with a signed JWT for the client
        signed_jwt = create_access_token(
            user_id=user_key,
            jti=jti,
            exp=access_exp,
            client_name=label,
        )
        payload["access_token"] = signed_jwt
        return payload

    def validate_access_token(self, access_token: str, *, now_utc: datetime | None = None) -> dict[str, Any]:
        token = str(access_token or "").strip()
        if not token:
            return {}
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())

        # JWT fast-path: decode claims first, then single DB revocation check by JTI
        db_key = token  # for legacy opaque tokens
        if is_jwt(token):
            try:
                claims = decode_access_token(token)
                db_key = str(claims.get("jti", "") or "").strip()
                if not db_key:
                    return {}
            except JWTError:
                return {}

        with self.db.get_session() as session:
            statement = select(MobileAuthSession).where(
                MobileAuthSession.access_token == db_key,
                MobileAuthSession.revoked.is_(False),
            ).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                return {}
            if ensure_utc(row.access_expires_at_utc) < now:
                return {}
            return self._session_payload_from_row(row)

    def refresh_tokens(
        self,
        refresh_token: str,
        *,
        access_minutes: int = 60,
        refresh_days: int = 30,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        token = str(refresh_token or "").strip()
        if not token:
            return {}
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        with self.db.get_session() as session:
            statement = select(MobileAuthSession).where(
                MobileAuthSession.refresh_token == token,
                MobileAuthSession.revoked.is_(False),
            ).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                return {}
            if ensure_utc(row.refresh_expires_at_utc) < now:
                return {}

            user_id = str(row.user_id or "")
            client_name = str(row.client_name or "")
            row.revoked = True
            row.revoked_at_utc = now
            row.updated_at = now
            session.add(row)
            session.flush()

        return self.issue_tokens(
            user_id,
            client_name=client_name,
            access_minutes=access_minutes,
            refresh_days=refresh_days,
            now_utc=now,
        )

    def revoke_all_tokens_for_user(self, user_id: str, now_utc: datetime | None = None) -> int:
        """Revoke all active mobile sessions for a user (e.g. on password reset)."""
        uid = str(user_id or "").strip()
        if not uid:
            return 0
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        revoked_count = 0
        with self.db.get_session() as session:
            statement = (
                select(MobileAuthSession)
                .where(MobileAuthSession.user_id == uid, MobileAuthSession.revoked.is_(False))
                .limit(200)
            )
            for row in session.execute(statement).scalars().all():
                row.revoked = True
                row.revoked_at_utc = now
                row.updated_at = now
                session.add(row)
                revoked_count += 1
            if revoked_count:
                session.flush()
        return revoked_count

    def revoke_tokens(
        self,
        *,
        access_token: str = "",
        refresh_token: str = "",
        now_utc: datetime | None = None,
    ) -> bool:
        access_key = str(access_token or "").strip()
        refresh_key = str(refresh_token or "").strip()
        if not access_key and not refresh_key:
            return False
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        revoked_any = False

        db_key = access_key
        if access_key and is_jwt(access_key):
            try:
                claims = decode_access_token(access_key)
                db_key = str(claims.get("jti", "") or "").strip()
            except JWTError:
                pass

        with self.db.get_session() as session:
            if db_key:
                statement = select(MobileAuthSession).where(
                    MobileAuthSession.access_token == db_key,
                    MobileAuthSession.revoked.is_(False),
                )
                for row in session.execute(statement).scalars().all():
                    row.revoked = True
                    row.revoked_at_utc = now
                    row.updated_at = now
                    session.add(row)
                    revoked_any = True

            if refresh_key:
                statement = select(MobileAuthSession).where(
                    MobileAuthSession.refresh_token == refresh_key,
                    MobileAuthSession.revoked.is_(False),
                )
                for row in session.execute(statement).scalars().all():
                    row.revoked = True
                    row.revoked_at_utc = now
                    row.updated_at = now
                    session.add(row)
                    revoked_any = True

            if revoked_any:
                session.flush()

        return revoked_any


class BetaProgressRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    @staticmethod
    def _first_three_nights_state_from_row(row: FirstThreeNightsProgress | None) -> dict[str, str]:
        if row is None:
            return {
                "signup_completed_at_utc": "",
                "first_scene_preview_completed_at_utc": "",
                "first_automation_completed_at_utc": "",
                "first_winddown_completed_at_utc": "",
                "timeline_review_completed_at_utc": "",
                "created_at_utc": "",
                "updated_at_utc": "",
            }
        return {
            "signup_completed_at_utc": _to_iso_optional(row.signup_completed_at_utc),
            "first_scene_preview_completed_at_utc": _to_iso_optional(row.first_scene_preview_completed_at_utc),
            "first_automation_completed_at_utc": _to_iso_optional(row.first_automation_completed_at_utc),
            "first_winddown_completed_at_utc": _to_iso_optional(row.first_winddown_completed_at_utc),
            "timeline_review_completed_at_utc": _to_iso_optional(row.timeline_review_completed_at_utc),
            "created_at_utc": _to_iso_optional(row.created_at),
            "updated_at_utc": _to_iso_optional(row.updated_at),
        }

    @staticmethod
    def _feedback_payload_from_row(row: NightlySummaryFeedbackProgress | None) -> dict[str, Any]:
        if row is None:
            return {
                "helpful_count": 0,
                "not_helpful_count": 0,
                "last_vote": "",
                "last_vote_at_utc": "",
                "last_summary_generated_at_utc": "",
            }
        last_vote = str(row.last_vote or "").strip().lower()
        if last_vote not in {"helpful", "not_helpful"}:
            last_vote = ""
        return {
            "helpful_count": max(0, int(row.helpful_count or 0)),
            "not_helpful_count": max(0, int(row.not_helpful_count or 0)),
            "last_vote": last_vote,
            "last_vote_at_utc": _to_iso_optional(row.last_vote_at_utc),
            "last_summary_generated_at_utc": str(row.last_summary_generated_at_utc or "").strip(),
        }

    @staticmethod
    def _int_metric(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _normalize_cohort_key(value: str | None) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "kuwait_beta"
        compact = "_".join(part for part in raw.replace("-", "_").split("_") if part)
        return compact or "kuwait_beta"

    @staticmethod
    def _cohort_member_payload_from_row(row: BetaCohortMember | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "cohort_key": str(row.cohort_key or "").strip().lower() or "kuwait_beta",
            "user_id": str(row.user_id or "").strip(),
            "country_code": str(row.country_code or "").strip().upper() or "KW",
            "status": str(row.status or "").strip().lower() or "active",
            "source": str(row.source or "").strip().lower() or "admin_manual",
            "notes": str(row.notes or ""),
            "created_at_utc": _to_iso_optional(row.created_at),
            "updated_at_utc": _to_iso_optional(row.updated_at),
        }

    @staticmethod
    def _metrics_payload_from_row(row: BetaMetricsSnapshot | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "window_days": int(row.window_days or 7),
            "activation_progress_pct": int(row.activation_progress_pct or 0),
            "first_3_nights_completed": int(row.first_3_nights_completed or 0),
            "first_3_nights_total": int(row.first_3_nights_total or 5),
            "command_total_7d": int(row.command_total_7d or 0),
            "command_completion_rate_pct": int(row.command_completion_rate_pct or 0),
            "wind_down_sessions_7d": int(row.wind_down_sessions_7d or 0),
            "nightly_feedback_total": int(row.nightly_feedback_total or 0),
            "nightly_feedback_helpful_pct": int(row.nightly_feedback_helpful_pct or 0),
            "cohort_status_line": str(row.cohort_status_line or ""),
            "quality_gate_line": str(row.quality_gate_line or ""),
            "generated_at_utc": _to_iso_optional(row.generated_at_utc),
        }

    def get_first_three_nights_state(self, user_id: str) -> dict[str, str]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return self._first_three_nights_state_from_row(None)
        with self.db.get_session() as session:
            statement = select(FirstThreeNightsProgress).where(FirstThreeNightsProgress.user_id == user_key).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            return self._first_three_nights_state_from_row(row)

    def sync_first_three_nights_steps(
        self,
        user_id: str,
        step_keys: list[str] | tuple[str, ...],
        now_utc: datetime | None = None,
    ) -> tuple[dict[str, str], bool]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return self._first_three_nights_state_from_row(None), False

        normalized_steps = []
        for raw_step in step_keys:
            step = str(raw_step or "").strip().lower()
            if step in _FIRST_3_NIGHTS_STEP_FIELD_MAP and step not in normalized_steps:
                normalized_steps.append(step)

        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        changed = False
        with self.db.get_session() as session:
            statement = select(FirstThreeNightsProgress).where(FirstThreeNightsProgress.user_id == user_key).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                row = FirstThreeNightsProgress(user_id=user_key, created_at=now, updated_at=now)
                session.add(row)
                session.flush()

            for step in normalized_steps:
                field = _FIRST_3_NIGHTS_STEP_FIELD_MAP.get(step, "")
                if not field:
                    continue
                if getattr(row, field) is None:
                    setattr(row, field, now)
                    changed = True

            if changed:
                row.updated_at = now
            session.add(row)
            session.flush()
            session.refresh(row)
            return self._first_three_nights_state_from_row(row), changed

    def mark_first_three_nights_step(
        self,
        user_id: str,
        step_key: str,
        now_utc: datetime | None = None,
    ) -> tuple[dict[str, str], bool]:
        return self.sync_first_three_nights_steps(
            user_id=user_id,
            step_keys=[step_key],
            now_utc=now_utc,
        )

    def get_nightly_summary_feedback(self, user_id: str) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return self._feedback_payload_from_row(None)
        with self.db.get_session() as session:
            statement = select(NightlySummaryFeedbackProgress).where(NightlySummaryFeedbackProgress.user_id == user_key).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            return self._feedback_payload_from_row(row)

    def record_nightly_summary_feedback(
        self,
        user_id: str,
        *,
        vote: str,
        summary_generated_at_utc: str = "",
        now_utc: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        user_key = _clean_user_id(user_id)
        normalized_vote = str(vote or "").strip().lower()
        if (not user_key) or (normalized_vote not in {"helpful", "not_helpful"}):
            return self._feedback_payload_from_row(None), False

        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        summary_marker = str(summary_generated_at_utc or "").strip()
        changed = False
        with self.db.get_session() as session:
            statement = select(NightlySummaryFeedbackProgress).where(NightlySummaryFeedbackProgress.user_id == user_key).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                row = NightlySummaryFeedbackProgress(
                    user_id=user_key,
                    helpful_count=0,
                    not_helpful_count=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()

            row_marker_dt = row.last_summary_generated_at_utc
            try:
                marker_dt = from_iso(summary_marker) if summary_marker else None
            except Exception:
                marker_dt = None

            duplicate_vote = (
                marker_dt is not None
                and row_marker_dt is not None
                and ensure_utc(row_marker_dt) == ensure_utc(marker_dt)
                and str(row.last_vote or "").strip().lower() == normalized_vote
            )

            if not duplicate_vote:
                if normalized_vote == "helpful":
                    row.helpful_count = max(0, int(row.helpful_count or 0)) + 1
                else:
                    row.not_helpful_count = max(0, int(row.not_helpful_count or 0)) + 1
                changed = True

            row.last_vote = normalized_vote
            row.last_vote_at_utc = now
            if summary_marker:
                row.last_summary_generated_at_utc = from_iso(summary_marker)
            row.updated_at = now
            session.add(row)
            session.flush()
            session.refresh(row)
            return self._feedback_payload_from_row(row), (changed or bool(summary_marker))

    def upsert_beta_metrics_snapshot(
        self,
        user_id: str,
        metrics: dict[str, Any],
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return {}

        source = metrics if isinstance(metrics, dict) else {}
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())
        generated_at = _parse_optional_iso_datetime(str(source.get("generated_at_utc", "") or "")) or now
        with self.db.get_session() as session:
            statement = select(BetaMetricsSnapshot).where(BetaMetricsSnapshot.user_id == user_key).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                row = BetaMetricsSnapshot(user_id=user_key, created_at=now, updated_at=now)
                session.add(row)
                session.flush()

            row.window_days = max(1, self._int_metric(source.get("window_days", 7), default=7))
            row.activation_progress_pct = max(0, min(100, self._int_metric(source.get("activation_progress_pct", 0))))
            row.first_3_nights_completed = max(0, self._int_metric(source.get("first_3_nights_completed", 0)))
            row.first_3_nights_total = max(1, self._int_metric(source.get("first_3_nights_total", 5), default=5))
            row.command_total_7d = max(0, self._int_metric(source.get("command_total_7d", 0)))
            row.command_completion_rate_pct = max(
                0,
                min(100, self._int_metric(source.get("command_completion_rate_pct", 0))),
            )
            row.wind_down_sessions_7d = max(0, self._int_metric(source.get("wind_down_sessions_7d", 0)))
            row.nightly_feedback_total = max(0, self._int_metric(source.get("nightly_feedback_total", 0)))
            row.nightly_feedback_helpful_pct = max(
                0,
                min(100, self._int_metric(source.get("nightly_feedback_helpful_pct", 0))),
            )
            row.cohort_status_line = str(source.get("cohort_status_line", "") or "")
            row.quality_gate_line = str(source.get("quality_gate_line", "") or "")
            row.generated_at_utc = generated_at
            row.updated_at = now

            session.add(row)
            session.flush()
            session.refresh(row)
            return self._metrics_payload_from_row(row)

    def get_beta_metrics_snapshot(self, user_id: str) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return {}
        with self.db.get_session() as session:
            statement = select(BetaMetricsSnapshot).where(BetaMetricsSnapshot.user_id == user_key).limit(1)
            row = session.execute(statement).scalar_one_or_none()
            return self._metrics_payload_from_row(row)

    def upsert_cohort_member(
        self,
        *,
        user_id: str,
        cohort_key: str = "kuwait_beta",
        country_code: str = "KW",
        status: str = "active",
        source: str = "admin_manual",
        notes: str = "",
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return {}

        normalized_cohort = self._normalize_cohort_key(cohort_key)
        normalized_country = str(country_code or "").strip().upper() or "KW"
        normalized_status = str(status or "").strip().lower() or "active"
        if normalized_status not in {"candidate", "invited", "active", "paused", "graduated", "inactive"}:
            normalized_status = "active"
        normalized_source = str(source or "").strip().lower() or "admin_manual"
        normalized_notes = str(notes or "").strip()
        now = ensure_utc(now_utc if isinstance(now_utc, datetime) else utcnow())

        with self.db.get_session() as session:
            statement = (
                select(BetaCohortMember)
                .where(
                    BetaCohortMember.user_id == user_key,
                    BetaCohortMember.cohort_key == normalized_cohort,
                )
                .limit(1)
            )
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                row = BetaCohortMember(
                    user_id=user_key,
                    cohort_key=normalized_cohort,
                    country_code=normalized_country,
                    status=normalized_status,
                    source=normalized_source,
                    notes=normalized_notes,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
            else:
                row.country_code = normalized_country
                row.status = normalized_status
                row.source = normalized_source
                row.notes = normalized_notes
                row.updated_at = now
                session.add(row)
                session.flush()
            session.refresh(row)
            return self._cohort_member_payload_from_row(row)

    def get_cohort_member(
        self,
        user_id: str,
        cohort_key: str = "kuwait_beta",
    ) -> dict[str, Any]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return {}
        normalized_cohort = self._normalize_cohort_key(cohort_key)
        with self.db.get_session() as session:
            statement = (
                select(BetaCohortMember)
                .where(
                    BetaCohortMember.user_id == user_key,
                    BetaCohortMember.cohort_key == normalized_cohort,
                )
                .limit(1)
            )
            row = session.execute(statement).scalar_one_or_none()
            return self._cohort_member_payload_from_row(row)

    def list_cohort_members(
        self,
        *,
        cohort_key: str = "kuwait_beta",
        status: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        normalized_cohort = self._normalize_cohort_key(cohort_key)
        normalized_status = str(status or "").strip().lower()
        safe_limit = max(1, min(int(limit or 100), 1000))
        with self.db.get_session() as session:
            statement = select(BetaCohortMember).where(BetaCohortMember.cohort_key == normalized_cohort)
            if normalized_status:
                statement = statement.where(BetaCohortMember.status == normalized_status)
            statement = statement.order_by(BetaCohortMember.updated_at.desc()).limit(safe_limit)
            rows = list(session.execute(statement).scalars().all())
            return [self._cohort_member_payload_from_row(row) for row in rows]


class UpdateRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    # ── App Versions ──────────────────────────────────────────────────────────

    def create_app_version(self, *, platform: str, version_string: str, build_number: int,
                           changelog: list, is_required: bool, rollout_percent: int,
                           min_supported_version: str | None = None,
                           store_url_ios: str | None = None,
                           store_url_android: str | None = None,
                           published_by: str | None = None) -> dict[str, Any]:
        safe_platform = str(platform or "all").strip().lower()
        with self.db.get_session() as session:
            prev = list(session.execute(
                select(AppVersion).where(AppVersion.platform == safe_platform, AppVersion.is_active == True)
            ).scalars().all())
            for v in prev:
                v.is_active = False
            new_v = AppVersion(
                platform=safe_platform,
                version_string=str(version_string or "").strip(),
                build_number=max(0, int(build_number or 0)),
                changelog=changelog if isinstance(changelog, list) else [],
                is_required=bool(is_required),
                rollout_percent=max(0, min(100, int(rollout_percent or 100))),
                is_active=True,
                min_supported_version=str(min_supported_version or "").strip() or None,
                store_url_ios=str(store_url_ios or "").strip() or None,
                store_url_android=str(store_url_android or "").strip() or None,
                published_by=str(published_by or "").strip() or None,
            )
            session.add(new_v)
            session.flush()
            return self._app_version_dict(new_v)

    def list_app_versions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.get_session() as session:
            rows = list(session.execute(
                select(AppVersion).order_by(AppVersion.created_at.desc()).limit(max(1, min(limit, 200)))
            ).scalars().all())
            return [self._app_version_dict(r) for r in rows]

    def update_app_version(self, version_id: str, **fields: Any) -> dict[str, Any] | None:
        with self.db.get_session() as session:
            row = session.execute(select(AppVersion).where(AppVersion.id == version_id)).scalar_one_or_none()
            if row is None:
                return None
            for key, val in fields.items():
                if hasattr(row, key):
                    setattr(row, key, val)
            return self._app_version_dict(row)

    def get_active_app_version(self, platform: str) -> dict[str, Any] | None:
        safe_platform = str(platform or "all").strip().lower()
        with self.db.get_session() as session:
            row = session.execute(
                select(AppVersion).where(
                    AppVersion.is_active == True,
                    AppVersion.platform.in_([safe_platform, "all"]),
                ).order_by(AppVersion.created_at.desc())
            ).scalars().first()
            return self._app_version_dict(row) if row else None

    def _app_version_dict(self, row: AppVersion) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "platform": str(row.platform or ""),
            "version_string": str(row.version_string or ""),
            "build_number": int(row.build_number or 0),
            "changelog": row.changelog if isinstance(row.changelog, list) else [],
            "is_required": bool(row.is_required),
            "rollout_percent": int(row.rollout_percent or 0),
            "is_active": bool(row.is_active),
            "min_supported_version": str(row.min_supported_version or "") or None,
            "store_url_ios": str(row.store_url_ios or "") or None,
            "store_url_android": str(row.store_url_android or "") or None,
            "published_by": str(row.published_by or "") or None,
            "created_at": to_iso(ensure_utc(row.created_at)) if row.created_at else "",
        }

    # ── Firmware Versions ─────────────────────────────────────────────────────

    def create_firmware_version(self, *, version_string: str, changelog: list, download_url: str,
                                is_required: bool, rollout_percent: int, target_device_ids: list,
                                published_by: str | None = None) -> dict[str, Any]:
        with self.db.get_session() as session:
            prev = list(session.execute(
                select(FirmwareVersion).where(FirmwareVersion.is_active == True)
            ).scalars().all())
            for v in prev:
                v.is_active = False
            new_v = FirmwareVersion(
                version_string=str(version_string or "").strip(),
                changelog=changelog if isinstance(changelog, list) else [],
                download_url=str(download_url or "").strip(),
                is_required=bool(is_required),
                rollout_percent=max(0, min(100, int(rollout_percent or 100))),
                is_active=True,
                target_device_ids=target_device_ids if isinstance(target_device_ids, list) else [],
                published_by=str(published_by or "").strip() or None,
            )
            session.add(new_v)
            session.flush()
            return self._firmware_dict(new_v)

    def list_firmware_versions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.get_session() as session:
            rows = list(session.execute(
                select(FirmwareVersion).order_by(FirmwareVersion.created_at.desc()).limit(max(1, min(limit, 200)))
            ).scalars().all())
            return [self._firmware_dict(r) for r in rows]

    def update_firmware_version(self, version_id: str, **fields: Any) -> dict[str, Any] | None:
        with self.db.get_session() as session:
            row = session.execute(select(FirmwareVersion).where(FirmwareVersion.id == version_id)).scalar_one_or_none()
            if row is None:
                return None
            for key, val in fields.items():
                if hasattr(row, key):
                    setattr(row, key, val)
            return self._firmware_dict(row)

    def get_active_firmware_version(self, device_id: str = "") -> dict[str, Any] | None:
        with self.db.get_session() as session:
            row = session.execute(
                select(FirmwareVersion).where(FirmwareVersion.is_active == True)
                .order_by(FirmwareVersion.created_at.desc())
            ).scalars().first()
            if row is None:
                return None
            targets = row.target_device_ids if isinstance(row.target_device_ids, list) else []
            if targets and device_id and device_id not in targets:
                return None
            return self._firmware_dict(row)

    def _firmware_dict(self, row: FirmwareVersion) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "version_string": str(row.version_string or ""),
            "changelog": row.changelog if isinstance(row.changelog, list) else [],
            "download_url": str(row.download_url or ""),
            "is_required": bool(row.is_required),
            "rollout_percent": int(row.rollout_percent or 0),
            "is_active": bool(row.is_active),
            "target_device_ids": row.target_device_ids if isinstance(row.target_device_ids, list) else [],
            "published_by": str(row.published_by or "") or None,
            "created_at": to_iso(ensure_utc(row.created_at)) if row.created_at else "",
        }


class FeatureFlagRepository:
    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()
        self.db.create_tables()

    def upsert_flag(self, *, flag_key: str, display_name: str = "", description: str = "",
                    enabled_globally: bool = False, enabled_for_plans: list | None = None,
                    rollout_percent: int = 0, updated_by: str | None = None) -> dict[str, Any]:
        import hashlib as _hashlib
        key = str(flag_key or "").strip().lower()
        with self.db.get_session() as session:
            row = session.execute(select(FeatureFlag).where(FeatureFlag.flag_key == key)).scalar_one_or_none()
            if row is None:
                row = FeatureFlag(flag_key=key)
                session.add(row)
            if display_name:
                row.display_name = str(display_name).strip()
            if description:
                row.description = str(description).strip()
            row.enabled_globally = bool(enabled_globally)
            row.enabled_for_plans = enabled_for_plans if isinstance(enabled_for_plans, list) else []
            row.rollout_percent = max(0, min(100, int(rollout_percent or 0)))
            if updated_by:
                row.updated_by = str(updated_by).strip()
            session.flush()
            return self._flag_dict(row)

    def list_flags(self) -> list[dict[str, Any]]:
        with self.db.get_session() as session:
            rows = list(session.execute(select(FeatureFlag).order_by(FeatureFlag.flag_key)).scalars().all())
            return [self._flag_dict(r) for r in rows]

    def get_flag(self, flag_key: str) -> dict[str, Any] | None:
        key = str(flag_key or "").strip().lower()
        with self.db.get_session() as session:
            row = session.execute(select(FeatureFlag).where(FeatureFlag.flag_key == key)).scalar_one_or_none()
            return self._flag_dict(row) if row else None

    def set_user_override(self, *, user_id: str, flag_key: str, override_value: bool,
                          reason: str = "", set_by: str | None = None) -> dict[str, Any]:
        uid = str(user_id or "").strip()
        key = str(flag_key or "").strip().lower()
        with self.db.get_session() as session:
            row = session.execute(
                select(UserFeatureOverride).where(
                    UserFeatureOverride.user_id == uid, UserFeatureOverride.flag_key == key
                )
            ).scalar_one_or_none()
            if row is None:
                row = UserFeatureOverride(user_id=uid, flag_key=key)
                session.add(row)
            row.override_value = bool(override_value)
            row.reason = str(reason or "").strip()
            row.set_by = str(set_by or "").strip() or None
            row.set_at = utcnow()
            session.flush()
            return self._override_dict(row)

    def delete_user_override(self, *, user_id: str, flag_key: str) -> bool:
        uid = str(user_id or "").strip()
        key = str(flag_key or "").strip().lower()
        with self.db.get_session() as session:
            result = session.execute(
                delete(UserFeatureOverride).where(
                    UserFeatureOverride.user_id == uid, UserFeatureOverride.flag_key == key
                )
            )
            rowcount = getattr(result, "rowcount", 0)
            return int(rowcount or 0) > 0

    def list_user_overrides(self, user_id: str) -> list[dict[str, Any]]:
        uid = str(user_id or "").strip()
        with self.db.get_session() as session:
            rows = list(session.execute(
                select(UserFeatureOverride).where(UserFeatureOverride.user_id == uid)
            ).scalars().all())
            return [self._override_dict(r) for r in rows]

    def resolve_feature(self, flag_key: str, user_id: str, subscription_status: str) -> bool:
        import hashlib as _hashlib
        key = str(flag_key or "").strip().lower()
        uid = str(user_id or "").strip()
        plan = str(subscription_status or "free").strip().lower()
        with self.db.get_session() as session:
            override = session.execute(
                select(UserFeatureOverride).where(
                    UserFeatureOverride.user_id == uid, UserFeatureOverride.flag_key == key
                )
            ).scalar_one_or_none()
            if override is not None:
                return bool(override.override_value)
            flag = session.execute(select(FeatureFlag).where(FeatureFlag.flag_key == key)).scalar_one_or_none()
            if flag is None:
                return False
            plans = flag.enabled_for_plans if isinstance(flag.enabled_for_plans, list) else []
            if plans and plan in plans:
                return True
            if flag.rollout_percent > 0:
                bucket = int(_hashlib.md5(f"{uid}{key}".encode()).hexdigest(), 16) % 100
                if bucket < flag.rollout_percent:
                    return True
            return bool(flag.enabled_globally)

    def _flag_dict(self, row: FeatureFlag) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "flag_key": str(row.flag_key or ""),
            "display_name": str(row.display_name or ""),
            "description": str(row.description or ""),
            "enabled_globally": bool(row.enabled_globally),
            "enabled_for_plans": row.enabled_for_plans if isinstance(row.enabled_for_plans, list) else [],
            "rollout_percent": int(row.rollout_percent or 0),
            "updated_by": str(row.updated_by or "") or None,
            "created_at": to_iso(ensure_utc(row.created_at)) if row.created_at else "",
            "updated_at": to_iso(ensure_utc(row.updated_at)) if row.updated_at else "",
        }

    def _override_dict(self, row: UserFeatureOverride) -> dict[str, Any]:
        return {
            "user_id": str(row.user_id or ""),
            "flag_key": str(row.flag_key or ""),
            "override_value": bool(row.override_value),
            "reason": str(row.reason or ""),
            "set_by": str(row.set_by or "") or None,
            "set_at": to_iso(ensure_utc(row.set_at)) if row.set_at else "",
        }


# ---------------------------------------------------------------------------
# Async repositories — backed by AsyncDatabaseConnection (asyncpg + SQLAlchemy asyncio)
# ---------------------------------------------------------------------------

class AsyncUserRepository:
    """Async counterpart of UserRepository.

    Uses SQLAlchemy AsyncSession (asyncpg driver) for all queries so the
    ORM models stay consistent with the sync layer.
    """

    def __init__(self, db: AsyncDatabaseConnection) -> None:
        self._db = db

    async def get_by_id(self, user_id: str) -> User | None:
        key = _clean_user_id(user_id)
        if not key:
            return None
        async with self._db.get_session() as session:
            return await session.get(User, key)

    async def get_by_email(self, email: str) -> User | None:
        normalized = str(email or "").strip().lower()
        if not normalized:
            return None
        async with self._db.get_session() as session:
            result = await session.execute(
                select(User).where(User.email == normalized).limit(1)
            )
            return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        user_id: str | None = None,
    ) -> User:
        async with self._db.get_session() as session:
            user = User(
                id=str(user_id or "").strip() or None,
                email=str(email or "").strip().lower(),
                password_hash=str(password_hash or "").strip(),
                full_name=str(full_name or "").strip() or None,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def update_subscription(
        self,
        user_id: str,
        status: str,
        trial_start: datetime | None = None,
        trial_end: datetime | None = None,
    ) -> User:
        async with self._db.get_session() as session:
            user = await session.get(User, str(user_id or "").strip())
            if user is None:
                raise ValueError("User not found")
            user.subscription_status = str(status or "free").strip().lower() or "free"
            user.trial_start_date = trial_start
            user.trial_end_date = trial_end
            user.updated_at = utcnow()
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def update(self, user_id: str, **kwargs: Any) -> User:
        async with self._db.get_session() as session:
            user = await session.get(User, str(user_id or "").strip())
            if user is None:
                raise ValueError("User not found")
            blocked = {"id", "created_at"}
            for key, value in kwargs.items():
                if key not in blocked and hasattr(user, key):
                    setattr(user, key, value)
            user.updated_at = utcnow()
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def delete(self, user_id: str) -> bool:
        key = _clean_user_id(user_id)
        if not key:
            return False
        async with self._db.get_session() as session:
            user = await session.get(User, key)
            if user is None:
                return False
            await session.delete(user)
            return True

    async def list_all(self, limit: int = 1000) -> list[User]:
        safe_limit = max(1, min(int(limit or 1000), 5000))
        async with self._db.get_session() as session:
            result = await session.execute(
                select(User).order_by(User.created_at.desc()).limit(safe_limit)
            )
            return list(result.scalars().all())


class AsyncSleepSessionRepository:
    """Async counterpart of SleepSessionRepository."""

    def __init__(self, db: AsyncDatabaseConnection) -> None:
        self._db = db

    async def get_session_by_date(
        self, user_id: str, date: date_type | str
    ) -> SleepSession | None:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return None
        target_date = _coerce_date(date)
        async with self._db.get_session() as session:
            result = await session.execute(
                select(SleepSession)
                .where(
                    SleepSession.user_id == user_key,
                    SleepSession.date == target_date,
                )
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_recent_sessions(
        self, user_id: str, limit: int = 7
    ) -> list[SleepSession]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return []
        safe_limit = max(1, min(int(limit or 7), 90))
        async with self._db.get_session() as session:
            result = await session.execute(
                select(SleepSession)
                .where(SleepSession.user_id == user_key)
                .order_by(SleepSession.date.desc())
                .limit(safe_limit)
            )
            return list(result.scalars().all())

    async def get_sessions_for_month(
        self, user_id: str, year: int, month: int, limit: int = 40
    ) -> list[SleepSession]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return []
        try:
            month_start = date_type(int(year), int(month), 1)
        except ValueError:
            return []
        month_end = (
            date_type(int(year) + 1, 1, 1)
            if int(month) == 12
            else date_type(int(year), int(month) + 1, 1)
        )
        safe_limit = max(1, min(int(limit or 40), 200))
        async with self._db.get_session() as session:
            result = await session.execute(
                select(SleepSession)
                .where(
                    SleepSession.user_id == user_key,
                    SleepSession.date >= month_start,
                    SleepSession.date < month_end,
                )
                .order_by(SleepSession.date.desc())
                .limit(safe_limit)
            )
            return list(result.scalars().all())

    async def create_or_update_session(
        self, user_id: str, date: date_type | str, **kwargs: Any
    ) -> SleepSession:
        user_key = _clean_user_id(user_id)
        target_date = _coerce_date(date)
        allowed = {
            "bedtime", "wake_time", "total_sleep_minutes",
            "restlessness_score", "scenes_used",
            "automations_fired", "winddowns_completed",
        }
        async with self._db.get_session() as session:
            result = await session.execute(
                select(SleepSession)
                .where(
                    SleepSession.user_id == user_key,
                    SleepSession.date == target_date,
                )
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = SleepSession(user_id=user_key, date=target_date)
            for key, value in kwargs.items():
                if key in allowed:
                    setattr(row, key, value)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return row


class AsyncEventRepository:
    """Async counterpart of EventRepository.

    ``log_event`` also exposes a fast-path via the raw asyncpg pool
    (``log_event_raw``) for high-volume sensor / telemetry writes that
    don't need ORM overhead.
    """

    def __init__(self, db: AsyncDatabaseConnection) -> None:
        self._db = db

    async def log_event(
        self,
        user_id: str | None,
        event_type: str,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Event:
        async with self._db.get_session() as session:
            import json as _json
            row = Event(
                user_id=_clean_user_id(user_id),
                event_type=str(event_type or "").strip(),
                metadata_json=dict(metadata or {}) if isinstance(metadata, dict) else None,
                trace_id=str(trace_id or "").strip() or None,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return row

    async def log_event_raw(
        self,
        user_id: str | None,
        event_type: str,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> str:
        """Insert an event using the raw asyncpg pool — no ORM overhead.

        Returns the new row's ``id`` string. Use for high-throughput telemetry
        writes (sensor readings, automation fires) where ORM overhead matters.
        """
        import json as _json
        from uuid import uuid4
        new_id = str(uuid4())
        now = utcnow()
        meta_json = _json.dumps(metadata) if isinstance(metadata, dict) else None
        async with self._db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO events (id, user_id, event_type, metadata, trace_id, timestamp)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                """,
                new_id,
                _clean_user_id(user_id),
                str(event_type or "").strip(),
                meta_json,
                str(trace_id or "").strip() or None,
                now,
            )
        return new_id

    async def get_events_by_user(
        self,
        user_id: str,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[Event]:
        user_key = _clean_user_id(user_id)
        if not user_key:
            return []
        safe_limit = max(1, min(int(limit or 50), 500))
        async with self._db.get_session() as session:
            stmt = select(Event).where(Event.user_id == user_key)
            if since is not None:
                stmt = stmt.where(Event.timestamp >= since)
            stmt = stmt.order_by(Event.timestamp.desc()).limit(safe_limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def cleanup_old_events(self, days: int = 90) -> int:
        cutoff = utcnow() - timedelta(days=max(1, int(days or 90)))
        async with self._db.get_session() as session:
            result = await session.execute(
                delete(Event).where(Event.timestamp < cutoff)
            )
            rowcount = getattr(result, "rowcount", 0)
            return int(rowcount or 0)


class AlarmRepository:
    """CRUD for the alarms table (sync SQLAlchemy)."""

    _MAX_ALARMS_PER_USER = 20

    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()

    def list_alarms(self, user_id: str) -> list[Alarm]:
        with self.db.get_session() as session:
            result = session.execute(
                select(Alarm)
                .where(Alarm.user_id == user_id)
                .order_by(Alarm.created_at)
                .limit(self._MAX_ALARMS_PER_USER)
            )
            return list(result.scalars().all())

    def get_alarm(self, alarm_id: str, user_id: str) -> Alarm | None:
        with self.db.get_session() as session:
            return session.execute(
                select(Alarm).where(Alarm.id == alarm_id, Alarm.user_id == user_id)
            ).scalar_one_or_none()

    def create_alarm(
        self,
        user_id: str,
        time: str,
        label: str = "",
        enabled: bool = True,
        days_of_week: list[int] | None = None,
        wake_style: str = "gentle_light",
        smart_window_minutes: int = 0,
    ) -> Alarm:
        with self.db.get_session() as session:
            count = session.execute(
                select(func.count()).where(Alarm.user_id == user_id)
            ).scalar_one()
            if count >= self._MAX_ALARMS_PER_USER:
                raise ValueError(f"Alarm limit reached ({self._MAX_ALARMS_PER_USER})")
            alarm = Alarm(
                user_id=user_id,
                time=time,
                label=label,
                enabled=enabled,
                days_of_week=days_of_week or [],
                wake_style=wake_style,
                smart_window_minutes=smart_window_minutes,
            )
            session.add(alarm)
            session.flush()
            session.refresh(alarm)
            return alarm

    def update_alarm(
        self,
        alarm_id: str,
        user_id: str,
        **fields: Any,
    ) -> Alarm | None:
        with self.db.get_session() as session:
            alarm = session.execute(
                select(Alarm).where(Alarm.id == alarm_id, Alarm.user_id == user_id)
            ).scalar_one_or_none()
            if alarm is None:
                return None
            allowed = {"time", "label", "enabled", "days_of_week", "wake_style", "smart_window_minutes"}
            for key, val in fields.items():
                if key in allowed:
                    setattr(alarm, key, val)
            session.flush()
            session.refresh(alarm)
            return alarm

    def delete_alarm(self, alarm_id: str, user_id: str) -> bool:
        with self.db.get_session() as session:
            result = session.execute(
                delete(Alarm).where(Alarm.id == alarm_id, Alarm.user_id == user_id)
            )
            rowcount = getattr(result, "rowcount", 0)
            return int(rowcount or 0) > 0


# ---------------------------------------------------------------------------
# Profile repository — DB-backed replacement for profile JSON helpers
# ---------------------------------------------------------------------------

_DEFAULT_SETTINGS: dict[str, Any] = {
    "response_style": "balanced",
    "engagement_level": "high",
    "wind_down_minutes": 45,
    "partner_mode_enabled": False,
    "bedtime_drift_automation_enabled": True,
    "quiet_hours_override_limit_minutes": 120,
    "weekly_insight_enabled": True,
}

_DEFAULT_PREFS: dict[str, Any] = {
    "display_name": "",
    "timezone": "Asia/Kuwait",
    "push_enabled": True,
    "email_enabled": False,
    "location_mode": "auto",
    "country_code": "KW",
    "city": "",
    "latitude": None,
    "longitude": None,
    "theme_mode": "system",
}


class ProfileRepository:
    """CRUD for UserProfilePrefs and UserRoutine (sync SQLAlchemy).

    Provides the DB-backed replacement for `_safe_profile()` / `_save_profile()`
    for the profile and settings API routes.
    """

    def __init__(self, db: DatabaseConnection | None = None) -> None:
        self.db = db or DatabaseConnection()

    # ── Profile prefs ─────────────────────────────────────────────────────────

    def get_profile_prefs(self, user_id: str) -> dict[str, Any]:
        """Return profile prefs dict; creates a default row if absent."""
        uid = _clean_user_id(user_id)
        if not uid:
            return dict(_DEFAULT_PREFS)
        with self.db.get_session() as session:
            row = session.execute(
                select(UserProfilePrefs).where(UserProfilePrefs.user_id == uid).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return dict(_DEFAULT_PREFS)
            return self._prefs_to_dict(row)

    def upsert_profile_prefs(self, user_id: str, **fields: Any) -> dict[str, Any]:
        """Create or update the UserProfilePrefs row for user_id."""
        uid = _clean_user_id(user_id)
        if not uid:
            raise ValueError("user_id is required")
        allowed = {
            "display_name", "timezone", "push_enabled", "email_enabled",
            "location_mode", "country_code", "city", "latitude", "longitude", "theme_mode",
        }
        with self.db.get_session() as session:
            row = session.execute(
                select(UserProfilePrefs).where(UserProfilePrefs.user_id == uid).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = UserProfilePrefs(user_id=uid)
                session.add(row)
            for key, val in fields.items():
                if key in allowed and hasattr(row, key):
                    setattr(row, key, val)
            row.updated_at = utcnow()
            session.flush()
            session.refresh(row)
            return self._prefs_to_dict(row)

    # ── Bed settings ──────────────────────────────────────────────────────────

    def get_settings(self, user_id: str) -> dict[str, Any]:
        """Return bed-behaviour settings dict; falls back to defaults."""
        uid = _clean_user_id(user_id)
        if not uid:
            return dict(_DEFAULT_SETTINGS)
        with self.db.get_session() as session:
            row = session.execute(
                select(UserProfilePrefs).where(UserProfilePrefs.user_id == uid).limit(1)
            ).scalar_one_or_none()
            if row is None or not isinstance(row.settings_json, dict):
                return dict(_DEFAULT_SETTINGS)
            return {**_DEFAULT_SETTINGS, **row.settings_json}

    def upsert_settings(self, user_id: str, **fields: Any) -> dict[str, Any]:
        """Merge provided fields into the settings_json for user_id."""
        uid = _clean_user_id(user_id)
        if not uid:
            raise ValueError("user_id is required")
        allowed = set(_DEFAULT_SETTINGS.keys())
        with self.db.get_session() as session:
            row = session.execute(
                select(UserProfilePrefs).where(UserProfilePrefs.user_id == uid).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = UserProfilePrefs(user_id=uid)
                session.add(row)
            current = row.settings_json if isinstance(row.settings_json, dict) else {}
            updated = {**_DEFAULT_SETTINGS, **current, **{k: v for k, v in fields.items() if k in allowed}}
            row.settings_json = updated
            row.updated_at = utcnow()
            session.flush()
            return dict(updated)

    # ── Routine ───────────────────────────────────────────────────────────────

    def get_routine(self, user_id: str) -> dict[str, Any]:
        uid = _clean_user_id(user_id)
        if not uid:
            return {"bedtime": "22:30", "wake": "07:00", "weekends_different": False}
        with self.db.get_session() as session:
            row = session.execute(
                select(UserRoutine).where(UserRoutine.user_id == uid).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return {"bedtime": "22:30", "wake": "07:00", "weekends_different": False}
            return {
                "bedtime": row.bedtime,
                "wake": row.wake,
                "weekends_different": row.weekends_different,
                "weekend_bedtime": row.weekend_bedtime,
                "weekend_wake": row.weekend_wake,
            }

    def upsert_routine(self, user_id: str, **fields: Any) -> dict[str, Any]:
        uid = _clean_user_id(user_id)
        if not uid:
            raise ValueError("user_id is required")
        allowed = {"bedtime", "wake", "weekends_different", "weekend_bedtime", "weekend_wake"}
        with self.db.get_session() as session:
            row = session.execute(
                select(UserRoutine).where(UserRoutine.user_id == uid).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = UserRoutine(user_id=uid)
                session.add(row)
            for key, val in fields.items():
                if key in allowed and hasattr(row, key):
                    setattr(row, key, val)
            row.updated_at = utcnow()
            session.flush()
            session.refresh(row)
            return self.get_routine(uid)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _prefs_to_dict(row: UserProfilePrefs) -> dict[str, Any]:
        return {
            "display_name": row.display_name or "",
            "timezone": row.timezone or "Asia/Kuwait",
            "push_enabled": bool(row.push_enabled),
            "email_enabled": bool(row.email_enabled),
            "location_mode": row.location_mode or "auto",
            "country_code": row.country_code or "",
            "city": row.city or "",
            "latitude": row.latitude,
            "longitude": row.longitude,
            "theme_mode": row.theme_mode or "system",
        }


class OtpRepository:
    """DB-backed OTP storage — replaces the profile JSON 'mobile_phone_otp_requests' section."""

    def __init__(self, db: DatabaseConnection | None = None) -> None:
        from config.settings import settings
        self._db = db or DatabaseConnection(database_url=settings.database_url)

    def create(
        self,
        *,
        request_id: str,
        phone_number: str,
        otp_digest: str,
        expires_at: datetime,
        client_name: str = "",
        delivery_provider: str = "",
        delivery_status: str = "",
        delivery_message_id: str = "",
    ) -> None:
        with self._db.get_session() as session:
            session.add(OtpRequest(
                request_id=request_id,
                phone_number=phone_number,
                otp_digest=otp_digest,
                expires_at=expires_at,
                client_name=client_name,
                delivery_provider=delivery_provider,
                delivery_status=delivery_status,
                delivery_message_id=delivery_message_id,
            ))

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._db.get_session() as session:
            row = session.get(OtpRequest, request_id)
            if row is None:
                return None
            return {
                "request_id": row.request_id,
                "phone_number": row.phone_number,
                "otp_digest": row.otp_digest,
                "attempts": row.attempts,
                "client_name": row.client_name,
                "delivery_provider": row.delivery_provider,
                "delivery_status": row.delivery_status,
                "delivery_message_id": row.delivery_message_id,
                "expires_at": row.expires_at,
                "created_at": row.created_at,
            }

    def increment_attempts(self, request_id: str) -> int:
        """Increment attempt counter; return new count."""
        with self._db.get_session() as session:
            row = session.get(OtpRequest, request_id)
            if row is None:
                return 0
            row.attempts += 1
            session.flush()
            return row.attempts

    def delete(self, request_id: str) -> None:
        with self._db.get_session() as session:
            row = session.get(OtpRequest, request_id)
            if row is not None:
                session.delete(row)

    def cleanup_expired(self) -> int:
        """Delete all expired OTP rows; return count deleted."""
        with self._db.get_session() as session:
            result = session.execute(
                delete(OtpRequest).where(OtpRequest.expires_at < utcnow())
            )
            rowcount = getattr(result, "rowcount", 0)
            return rowcount or 0


class SpotifyTokenRepository:
    """DB-backed Spotify token storage — replaces profile JSON 'spotify_tokens' section."""

    def __init__(self, db: DatabaseConnection | None = None) -> None:
        from config.settings import settings
        self._db = db or DatabaseConnection(database_url=settings.database_url)

    def get(self, user_key: str) -> dict[str, Any] | None:
        with self._db.get_session() as session:
            row = session.scalars(
                select(SpotifyToken).where(SpotifyToken.user_key == user_key)
            ).first()
            if row is None:
                return None
            return self._to_dict(row)

    def upsert(
        self,
        user_key: str,
        *,
        access_token: str,
        refresh_token: str = "",
        scope: str = "",
        spotify_user_id: str = "",
        display_name: str = "",
        spotify_email: str = "",
        expires_at: str = "",
    ) -> dict[str, Any]:
        with self._db.get_session() as session:
            row = session.scalars(
                select(SpotifyToken).where(SpotifyToken.user_key == user_key)
            ).first()
            if row is None:
                row = SpotifyToken(user_key=user_key)
                session.add(row)
            row.access_token = access_token
            if refresh_token:
                row.refresh_token = refresh_token
            row.scope = scope
            row.spotify_user_id = spotify_user_id
            row.display_name = display_name
            row.spotify_email = spotify_email
            row.expires_at = expires_at
            session.flush()
            return self._to_dict(row)

    def update_access_token(
        self,
        user_key: str,
        *,
        access_token: str,
        expires_at: str,
    ) -> None:
        with self._db.get_session() as session:
            row = session.scalars(
                select(SpotifyToken).where(SpotifyToken.user_key == user_key)
            ).first()
            if row is not None:
                row.access_token = access_token
                row.expires_at = expires_at

    def delete(self, user_key: str) -> None:
        with self._db.get_session() as session:
            row = session.scalars(
                select(SpotifyToken).where(SpotifyToken.user_key == user_key)
            ).first()
            if row is not None:
                session.delete(row)

    @staticmethod
    def _to_dict(row: SpotifyToken) -> dict[str, Any]:
        return {
            "access_token": row.access_token or "",
            "refresh_token": row.refresh_token or "",
            "scope": row.scope or "",
            "spotify_user_id": row.spotify_user_id or "",
            "display_name": row.display_name or "",
            "spotify_email": row.spotify_email or "",
            "expires_at": row.expires_at or "",
        }
