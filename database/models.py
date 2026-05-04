from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
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

    @property
    def is_stale(self) -> bool:
        if self.last_seen is None:
            return True
        delta = (datetime.utcnow() - self.last_seen.replace(tzinfo=None)).total_seconds()
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


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
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


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


class MobileAuthSession(Base):
    __tablename__ = "mobile_auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    client_name: Mapped[str] = mapped_column(String(80), nullable=False, default="flutter_app")
    access_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    refresh_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    issued_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    access_expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class AppVersion(Base):
    __tablename__ = "app_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="all")  # ios | android | all
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FirmwareVersion(Base):
    __tablename__ = "firmware_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    version_string: Mapped[str] = mapped_column(String(30), nullable=False)
    changelog: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    download_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    target_device_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # empty = all devices
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    flag_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled_globally: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled_for_plans: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # e.g. ["standard","pro"]
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class UserFeatureOverride(Base):
    __tablename__ = "user_feature_overrides"
    __table_args__ = (UniqueConstraint("user_id", "flag_key", name="uq_user_feature_overrides_user_flag"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    flag_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    override_value: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class UserMemoryEntry(Base):
    """One conversational turn stored for long-term memory continuity."""
    __tablename__ = "user_memory_entries"
    __table_args__ = (Index("idx_memory_entries_user_ts", "user_id", "ts"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    user_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assistant_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    emotion: Mapped[str] = mapped_column(String(40), nullable=False, default="neutral")
    personality: Mapped[str] = mapped_column(String(40), nullable=False, default="guide")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class UserDailyEvent(Base):
    """External daily-life events injected into Dana's memory context."""
    __tablename__ = "user_daily_events"
    __table_args__ = (Index("idx_daily_events_user_ts", "user_id", "ts"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    summary: Mapped[str] = mapped_column(String(220), nullable=False, default="")
    stress_level: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class UserPushToken(Base):
    """Expo push notification tokens — one active token per user."""
    __tablename__ = "user_push_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), unique=True, nullable=False, index=True)
    expo_token: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="android")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SubscriptionRecord(Base):
    """DB mirror of the subscription store — written on every subscription change."""
    __tablename__ = "subscription_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(191), unique=True, nullable=False, index=True)
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
]
