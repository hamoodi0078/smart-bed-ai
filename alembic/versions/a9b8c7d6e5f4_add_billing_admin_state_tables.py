"""add billing admin state tables

Revision ID: a9b8c7d6e5f4
Revises: ed907a3c517e
Create Date: 2026-07-19 04:30:00.000000

Plan 8 (campaign Phase 2): checkout sessions, payment events, webhook
receipts and admin sessions move from the process-local JSON store into
Postgres so billing state survives container restarts.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'ed907a3c517e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "checkout_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("interval", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("payment_provider", sa.String(40), nullable=False, server_default="paypal"),
        sa.Column("price_kwd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="created"),
        sa.Column("approve_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("return_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("cancel_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("provider_order_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_subscription_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_plan_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_capture_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_environment", sa.String(60), nullable=False, server_default=""),
        sa.Column("provider_currency", sa.String(60), nullable=False, server_default=""),
        sa.Column("provider_status", sa.String(60), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False, server_default=""),
        sa.Column("captured_at", sa.String(40), nullable=False, server_default=""),
        sa.Column("cancelled_at", sa.String(40), nullable=False, server_default=""),
    )
    op.create_index("ix_checkout_sessions_session_id", "checkout_sessions", ["session_id"], unique=True)
    op.create_index("ix_checkout_sessions_user_id", "checkout_sessions", ["user_id"])
    op.create_index("ix_checkout_sessions_provider_order_id", "checkout_sessions", ["provider_order_id"])
    op.create_index(
        "ix_checkout_sessions_provider_subscription_id",
        "checkout_sessions",
        ["provider_subscription_id"],
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False, server_default=""),
        sa.Column("tier", sa.String(20), nullable=False, server_default=""),
        sa.Column("interval", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("payment_provider", sa.String(40), nullable=False, server_default="paypal"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(60), nullable=False, server_default=""),
        sa.Column("amount_value", sa.String(40), nullable=False, server_default=""),
        sa.Column("currency", sa.String(10), nullable=False, server_default=""),
        sa.Column("provider_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_subscription_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_plan_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False, server_default=""),
    )
    op.create_index("ix_payment_events_event_id", "payment_events", ["event_id"], unique=True)
    op.create_index("ix_payment_events_user_id", "payment_events", ["user_id"])
    op.create_index("ix_payment_events_created_at", "payment_events", ["created_at"])

    op.create_table(
        "billing_webhook_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("receipt_key", sa.String(255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.String(40), nullable=False, server_default=""),
        sa.UniqueConstraint("kind", "receipt_key", name="uq_billing_receipt_kind_key"),
    )
    op.create_index("ix_billing_webhook_receipts_receipt_key", "billing_webhook_receipts", ["receipt_key"])
    op.create_index("ix_billing_webhook_receipts_processed_at", "billing_webhook_receipts", ["processed_at"])

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token", sa.String(80), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("expires_at", sa.String(40), nullable=False, server_default=""),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_admin_sessions_token", "admin_sessions", ["token"], unique=True)
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("admin_sessions")
    op.drop_table("billing_webhook_receipts")
    op.drop_table("payment_events")
    op.drop_table("checkout_sessions")
