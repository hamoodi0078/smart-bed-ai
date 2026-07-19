from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
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
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Kuwait")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    trial_start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_tokens_user", "user_id"),
        Index("idx_refresh_tokens_token", "token"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Bed(Base):
    __tablename__ = "beds"
    __table_args__ = (
        Index("idx_beds_primary_user", "primary_user_id"),
        Index("idx_beds_partner_user", "partner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    device_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    primary_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    partner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    device_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    @property
    def is_stale(self) -> bool:
        if self.last_seen is None:
            return True
        delta = (
            datetime.now(timezone.utc) - self.last_seen.astimezone(timezone.utc)
        ).total_seconds()
        return delta > 3600


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_events_user_timestamp", "user_id", "timestamp"),
        Index("idx_events_type_timestamp", "event_type", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    bed_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("beds.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )


class SleepSession(Base):
    __tablename__ = "sleep_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_sleep_sessions_user_date"),
        Index("idx_sleep_sessions_user_date", "user_id", "date"),
    )

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class MobileCommandRecord(Base):
    __tablename__ = "mobile_command_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    event_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    command_created_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    command_updated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    command_completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class MobileCommandFeedback(Base):
    __tablename__ = "mobile_command_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "command_id", name="uq_mobile_command_feedback_user_command"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    vote: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class MobileAuthSession(Base):
    __tablename__ = "mobile_auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_name: Mapped[str] = mapped_column(String(80), nullable=False, default="flutter_app")
    access_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    refresh_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    issued_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    access_expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class FirstThreeNightsProgress(Base):
    __tablename__ = "first_three_nights_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    signup_completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_scene_preview_completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_automation_completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_winddown_completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timeline_review_completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class NightlySummaryFeedbackProgress(Base):
    __tablename__ = "nightly_summary_feedback_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_vote: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_vote_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_summary_generated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class BetaMetricsSnapshot(Base):
    __tablename__ = "beta_metrics_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
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
    generated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class BetaCohortMember(Base):
    __tablename__ = "beta_cohort_members"
    __table_args__ = (
        UniqueConstraint("cohort_key", "user_id", name="uq_beta_cohort_members_cohort_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    cohort_key: Mapped[str] = mapped_column(
        String(80), nullable=False, default="kuwait_beta", index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(191), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    country_code: Mapped[str] = mapped_column(String(8), nullable=False, default="KW")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="admin_manual")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AppVersion(Base):
    __tablename__ = "app_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    platform: Mapped[str] = mapped_column(
        String(20), nullable=False, default="all"
    )  # ios | android | all
    version_string: Mapped[str] = mapped_column(String(30), nullable=False)
    build_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changelog: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_supported_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    store_url_ios: Mapped[str | None] = mapped_column(Text, nullable=True)
    store_url_android: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class FirmwareVersion(Base):
    __tablename__ = "firmware_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    version_string: Mapped[str] = mapped_column(String(30), nullable=False)
    changelog: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    download_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    target_device_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )  # empty = all devices
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    flag_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled_globally: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled_for_plans: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )  # e.g. ["standard","pro"]
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class UserFeatureOverride(Base):
    __tablename__ = "user_feature_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "flag_key", name="uq_user_feature_overrides_user_flag"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    override_value: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class UserMemoryEntry(Base):
    """One conversational turn stored for long-term memory continuity."""

    __tablename__ = "user_memory_entries"
    __table_args__ = (Index("idx_memory_entries_user_ts", "user_id", "ts"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    user_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assistant_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    emotion: Mapped[str] = mapped_column(String(40), nullable=False, default="neutral")
    personality: Mapped[str] = mapped_column(String(40), nullable=False, default="guide")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class UserDailyEvent(Base):
    """External daily-life events injected into Dana's memory context."""

    __tablename__ = "user_daily_events"
    __table_args__ = (Index("idx_daily_events_user_ts", "user_id", "ts"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    summary: Mapped[str] = mapped_column(String(220), nullable=False, default="")
    stress_level: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class UserPushToken(Base):
    """Expo push notification tokens — one active token per user."""

    __tablename__ = "user_push_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    expo_token: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="android")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class SubscriptionRecord(Base):
    """DB mirror of the subscription store — written on every subscription change."""

    __tablename__ = "subscription_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(191),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    interval: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    payment_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="none")
    price_kwd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    provider_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_plan_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_status: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    next_renewal_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    grace_end_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    started_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    last_payment_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    cancelled_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Alarm(Base):
    __tablename__ = "alarms"
    __table_args__ = (Index("idx_alarms_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    days_of_week: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )  # [0..6], empty = one-shot
    wake_style: Mapped[str] = mapped_column(String(30), nullable=False, default="gentle_light")
    smart_window_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 0 = disabled
    sound: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    vibrate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class UserRoutine(Base):
    """Replaces profile JSON 'web_routines' section."""

    __tablename__ = "user_routines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    bedtime: Mapped[str] = mapped_column(String(5), nullable=False, default="22:30")  # "HH:MM"
    wake: Mapped[str] = mapped_column(String(5), nullable=False, default="07:00")  # "HH:MM"
    weekends_different: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weekend_bedtime: Mapped[str | None] = mapped_column(String(5), nullable=True)
    weekend_wake: Mapped[str | None] = mapped_column(String(5), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class UserProfilePrefs(Base):
    """Replaces profile JSON 'web_profile_prefs' section."""

    __tablename__ = "user_profile_prefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kuwait")
    push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="auto"
    )  # "auto" | "manual"
    country_code: Mapped[str] = mapped_column(String(8), nullable=False, default="KW")
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    theme_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="system"
    )  # "system" | "dark" | "light"
    # Bed-behaviour settings stored together with profile prefs to avoid a join.
    settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class UserSocialIdentity(Base):
    """Replaces profile JSON 'mobile_social_identities' section."""

    __tablename__ = "user_social_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_social_provider_uid"),
        Index("idx_social_identities_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "google" | "apple" | "facebook"
    provider_user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, default="")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_method: Mapped[str] = mapped_column(
        String(40), nullable=False, default="token_verified"
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class UserPhoneAuth(Base):
    """Replaces profile JSON 'mobile_phone_users' section."""

    __tablename__ = "user_phone_auth"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class OtpRequest(Base):
    """Short-lived OTP record — replaces profile JSON 'mobile_phone_otp_requests' section."""

    __tablename__ = "otp_requests"
    __table_args__ = (Index("idx_otp_requests_phone", "phone_number"),)

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    otp_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    delivery_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    delivery_message_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class SpotifyToken(Base):
    """Persistent Spotify OAuth token — replaces profile JSON 'spotify_tokens' section."""

    __tablename__ = "spotify_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    spotify_user_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    display_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    spotify_email: Mapped[str] = mapped_column(String(254), nullable=False, default="")
    expires_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")  # ISO string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class CheckoutSessionRecord(Base):
    """Durable checkout session — DB-first storage for the subscription store.

    user_id has no FK on purpose: billing rows may reference legacy-web users
    that never existed in the users table (same semantics as the JSON store).
    ISO timestamps stay strings to mirror the store's dict shape exactly.
    """

    __tablename__ = "checkout_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    interval: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    payment_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="paypal")
    price_kwd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created")
    approve_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    return_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cancel_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider_order_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", index=True
    )
    provider_subscription_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", index=True
    )
    provider_plan_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_capture_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_environment: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    provider_currency: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    provider_status: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    cancelled_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class PaymentEventRecord(Base):
    """Durable billing timeline event (webhooks, captures, renewals)."""

    __tablename__ = "payment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    interval: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    payment_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="paypal")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    amount_value: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_plan_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)


class BillingWebhookReceipt(Base):
    """Webhook idempotency + replay receipts — the double-charge guard."""

    __tablename__ = "billing_webhook_receipts"
    __table_args__ = (
        UniqueConstraint("kind", "receipt_key", name="uq_billing_receipt_kind_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # idempotency | replay
    receipt_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    processed_at: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)


class AdminSessionRecord(Base):
    """Durable admin console session token."""

    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    token: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    expires_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


__all__ = [
    "Base",
    "User",
    "Bed",
    "SceneRecord",
    "Event",
    "SleepSession",
    "MobileCommandRecord",
    "MobileCommandFeedback",
    "MobileAuthSession",
    "FirstThreeNightsProgress",
    "NightlySummaryFeedbackProgress",
    "BetaMetricsSnapshot",
    "BetaCohortMember",
    "AppVersion",
    "FirmwareVersion",
    "FeatureFlag",
    "UserFeatureOverride",
    "UserMemoryEntry",
    "UserDailyEvent",
    "UserPushToken",
    "SubscriptionRecord",
    "Alarm",
    "UserRoutine",
    "UserProfilePrefs",
    "UserSocialIdentity",
    "UserPhoneAuth",
    "OtpRequest",
    "SpotifyToken",
    "CheckoutSessionRecord",
    "PaymentEventRecord",
    "BillingWebhookReceipt",
    "AdminSessionRecord",
]
