"""add alarms table and fix nightly_summary timestamp type

Revision ID: a1b2c3d4e5f6
Revises: d7f43a4871f4
Create Date: 2026-05-08 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "d7f43a4871f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # B-03: create alarms table
    op.create_table(
        "alarms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(191), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False, server_default=""),
        sa.Column("time", sa.String(5), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("days_of_week", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("wake_style", sa.String(30), nullable=False, server_default="gentle_light"),
        sa.Column("smart_window_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_alarms_user_id", "alarms", ["user_id"])

    # B-05: migrate last_summary_generated_at_utc from varchar(40) to timestamptz
    op.execute(
        """
        ALTER TABLE nightly_summary_feedback_progress
        ALTER COLUMN last_summary_generated_at_utc
        TYPE TIMESTAMPTZ
        USING CASE
            WHEN last_summary_generated_at_utc IS NULL THEN NULL
            ELSE last_summary_generated_at_utc::TIMESTAMPTZ
        END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE nightly_summary_feedback_progress
        ALTER COLUMN last_summary_generated_at_utc
        TYPE VARCHAR(40)
        USING CASE
            WHEN last_summary_generated_at_utc IS NULL THEN NULL
            ELSE last_summary_generated_at_utc::TEXT
        END
        """
    )
    op.drop_index("idx_alarms_user_id", table_name="alarms")
    op.drop_table("alarms")
