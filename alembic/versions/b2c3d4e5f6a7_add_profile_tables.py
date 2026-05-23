"""add profile tables (user_routines, user_profile_prefs, user_social_identities, user_phone_auth)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09

Replaces the shared profile JSON file with four normalised tables so the
backend can scale horizontally without filesystem coordination.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_routines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("bedtime", sa.String(5), nullable=False, server_default="22:00"),
        sa.Column("wake", sa.String(5), nullable=False, server_default="06:00"),
        sa.Column("weekends_different", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("weekend_bedtime", sa.String(5), nullable=True),
        sa.Column("weekend_wake", sa.String(5), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_user_routines_user_id", "user_routines", ["user_id"])

    op.create_table(
        "user_profile_prefs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Asia/Kuwait"),
        sa.Column("push_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("email_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("location_mode", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("country_code", sa.String(5), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("theme_mode", sa.String(10), nullable=False, server_default="dark"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_user_profile_prefs_user_id", "user_profile_prefs", ["user_id"])

    op.create_table(
        "user_social_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("verification_method", sa.String(30), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_social_provider_uid"),
    )
    op.create_index("ix_user_social_identities_user_id", "user_social_identities", ["user_id"])

    op.create_table(
        "user_phone_auth",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("phone_number", sa.String(20), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_user_phone_auth_phone_number", "user_phone_auth", ["phone_number"])
    op.create_index("ix_user_phone_auth_user_id", "user_phone_auth", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_phone_auth")
    op.drop_table("user_social_identities")
    op.drop_table("user_profile_prefs")
    op.drop_table("user_routines")
