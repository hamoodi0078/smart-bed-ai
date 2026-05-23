"""add indexes on beds.primary_user_id and beds.partner_user_id

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-05-22 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_beds_primary_user", "beds", ["primary_user_id"])
    op.create_index("idx_beds_partner_user", "beds", ["partner_user_id"])


def downgrade() -> None:
    op.drop_index("idx_beds_partner_user", table_name="beds")
    op.drop_index("idx_beds_primary_user", table_name="beds")
