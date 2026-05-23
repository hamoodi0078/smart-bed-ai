"""add otp_requests and spotify_tokens tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-09

Replaces profile JSON sections:
  - mobile_phone_otp_requests → otp_requests (short-lived, indexed by request_id)
  - spotify_tokens            → spotify_tokens (persistent per user_key)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "otp_requests",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("otp_digest", sa.String(128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("delivery_provider", sa.String(32), nullable=False, server_default=""),
        sa.Column("delivery_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("delivery_message_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_otp_requests_phone", "otp_requests", ["phone_number"])

    op.create_table(
        "spotify_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_key", sa.String(256), nullable=False, unique=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope", sa.Text(), nullable=False, server_default=""),
        sa.Column("spotify_user_id", sa.String(256), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("spotify_email", sa.String(254), nullable=False, server_default=""),
        sa.Column("expires_at", sa.String(40), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_spotify_tokens_user_key", "spotify_tokens", ["user_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_spotify_tokens_user_key", table_name="spotify_tokens")
    op.drop_table("spotify_tokens")
    op.drop_index("idx_otp_requests_phone", table_name="otp_requests")
    op.drop_table("otp_requests")
