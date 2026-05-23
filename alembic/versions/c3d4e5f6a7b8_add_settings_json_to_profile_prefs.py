"""add settings_json column to user_profile_prefs

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-09

Stores bed-behaviour settings (response_style, engagement_level, wind_down_minutes,
partner_mode_enabled, etc.) alongside the profile-prefs row so both can be
read/written in one query without a second table.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profile_prefs",
        sa.Column("settings_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profile_prefs", "settings_json")
