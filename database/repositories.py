from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select

from time_utils import ensure_utc, from_iso, to_iso, utcnow

from .connection import DatabaseConnection
from .models import (
    BetaCohortMember,
    BetaMetricsSnapshot,
    Event,
    FirstThreeNightsProgress,
    MobileCommandFeedback,
    MobileCommandRecord,
    NightlySummaryFeedbackProgress,
    SleepSession,
    User,
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

            duplicate_vote = (
                bool(summary_marker)
                and str(row.last_summary_generated_at_utc or "").strip() == summary_marker
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
                row.last_summary_generated_at_utc = summary_marker
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
