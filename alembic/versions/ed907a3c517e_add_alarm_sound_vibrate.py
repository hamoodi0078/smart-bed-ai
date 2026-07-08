"""add alarm sound vibrate

Revision ID: ed907a3c517e
Revises: 084855be2828
Create Date: 2026-07-09 02:15:59.160109
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed907a3c517e'
down_revision: Union[str, None] = '084855be2828'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alarms",
        sa.Column("sound", sa.String(64), nullable=False, server_default="default"),
    )
    op.add_column(
        "alarms",
        sa.Column("vibrate", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("alarms", "vibrate")
    op.drop_column("alarms", "sound")
