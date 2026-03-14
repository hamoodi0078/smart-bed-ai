from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from time_utils import utcnow


def _uuid_str() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Kuwait")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    trial_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Bed(Base):
    __tablename__ = "beds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    device_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    primary_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    partner_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    device_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SceneRecord(Base):
    __tablename__ = "scene_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_system_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    bed_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("beds.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SleepSession(Base):
    __tablename__ = "sleep_sessions"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_sleep_sessions_user_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    bedtime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wake_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_sleep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    restlessness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scenes_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    automations_fired: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winddowns_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MobileCommandRecord(Base):
    __tablename__ = "mobile_command_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    command_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    event_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    command_created_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    command_updated_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    command_completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class MobileCommandFeedback(Base):
    __tablename__ = "mobile_command_feedback"
    __table_args__ = (UniqueConstraint("user_id", "command_id", name="uq_mobile_command_feedback_user_command"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    command_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    vote: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class FirstThreeNightsProgress(Base):
    __tablename__ = "first_three_nights_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), unique=True, nullable=False, index=True)
    signup_completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_scene_preview_completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_automation_completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_winddown_completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeline_review_completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class NightlySummaryFeedbackProgress(Base):
    __tablename__ = "nightly_summary_feedback_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), unique=True, nullable=False, index=True)
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_vote: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_vote_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_summary_generated_at_utc: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class BetaMetricsSnapshot(Base):
    __tablename__ = "beta_metrics_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), unique=True, nullable=False, index=True)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    activation_progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_3_nights_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_3_nights_total: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    command_total_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    command_completion_rate_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wind_down_sessions_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nightly_feedback_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nightly_feedback_helpful_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cohort_status_line: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quality_gate_line: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class BetaCohortMember(Base):
    __tablename__ = "beta_cohort_members"
    __table_args__ = (UniqueConstraint("cohort_key", "user_id", name="uq_beta_cohort_members_cohort_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    cohort_key: Mapped[str] = mapped_column(String(80), nullable=False, default="kuwait_beta", index=True)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False, default="KW")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="admin_manual")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = [
    "Base",
    "User",
    "Bed",
    "SceneRecord",
    "Event",
    "SleepSession",
    "MobileCommandRecord",
    "MobileCommandFeedback",
    "FirstThreeNightsProgress",
    "NightlySummaryFeedbackProgress",
    "BetaMetricsSnapshot",
    "BetaCohortMember",
]
